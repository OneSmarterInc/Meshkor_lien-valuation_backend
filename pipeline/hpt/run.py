"""One command for the whole hospital-price loop, hospital by hospital, with a ledger.

  python -m pipeline.hpt.run --tier 1                 # every tier-1 hospital, this month
  python -m pipeline.hpt.run --ccn 360051,360180
  python -m pipeline.hpt.run --all                    # every hospital with a website
  python -m pipeline.hpt.run --tier 2 --retry-parked  # try again the ones a person has fixed

Rules (software-engineering version, Oct 23, 2026):
  * one hospital's failure never stops the run: it is recorded in the ledger with a reason code
    (AUTH, BLOCKED, NOT_FOUND, TIMEOUT, HTML, INVALID, PARSE_ERROR, VERIFY_FAIL ...) and a next action
  * every file is validated BEFORE it is registered for loading
  * a file the loader cannot parse, or that fails verification, is quarantined (not in the database)
  * rerunning only does what is still open; finished and unchanged hospitals are skipped
  * everything ends in data/reports/hpt_ledger.xlsx (+ .csv) and hpt_run_<date>.md

Steps: hospitals -> cms-hpt.txt per site -> download -> validate -> register (yaml) -> load_ref
       -> build_duckdb -> verify (quarantine) -> quality -> progress -> ledger + summary.
--via chrome : all fetches and downloads through your own Chrome (tools/chrome_hpt.ps1), so a
               browser-only VPN applies.   --via auto (default): Python first, Chrome on refusal.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from ..common import config
from . import discover, download, hospitals, intake, progress, quality, validate, verify
from .ledger import Ledger

MANAGE = config.PROJECT_ROOT / "backend" / "manage.py"
_py_fetch, _py_stream = discover.fetch, download.stream_download


# ----------------------------------------------------------------------------- fetch modes
def install_via(mode: str) -> None:
    from . import chrome

    def fetch_auto(url, timeout):
        st, text = _py_fetch(url, timeout)
        if st == 200:
            return st, text
        print(f"   python got {st or 'no connection'} -> retry through Chrome")
        return chrome.fetch(url, timeout)

    def stream_auto(url, dest, timeout):
        try:
            sha, n, st = _py_stream(url, dest, timeout)
        except Exception as e:  # noqa: BLE001
            sha, n, st = "", 0, 0
            print(f"   python error {str(e)[:60]}")
        if st == 200:
            return sha, n, st
        print(f"   python got {st or 'no connection'} -> retry through Chrome")
        return chrome.stream_download(url, dest, max(timeout, 3600))

    if mode == "chrome":
        chrome._connect()
        discover.fetch, download.stream_download = chrome.fetch, chrome.stream_download
    elif mode == "auto":
        discover.fetch, download.stream_download = fetch_auto, stream_auto
    else:
        discover.fetch, download.stream_download = _py_fetch, _py_stream


def public_country() -> str:
    import requests
    for url, key in (("https://ipinfo.io/json", "country"), ("https://api.country.is", "country")):
        try:
            return requests.get(url, timeout=15).json().get(key, "")
        except Exception:  # noqa: BLE001
            continue
    return ""


# ----------------------------------------------------------------------------- scope
def sites_rows() -> list[dict]:
    with open(config.PROJECT_ROOT / "config" / "hospital_sites.csv", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def tiers_map() -> dict[str, str]:
    p = config.PROJECT_ROOT / "config" / "hpt_tiers.csv"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8-sig", newline="") as f:
        return {r["system"].strip().lower(): str(r["tier"]).strip() for r in csv.DictReader(f) if r.get("system")}


def hospital_table(paths) -> dict[str, dict]:
    """ccn -> {hospital_name, system, website, tier} from hpt_hospitals.parquet (+ hospital_sites.csv)."""
    tiers = tiers_map()
    out: dict[str, dict] = {}
    hp = paths.ref / "hpt_hospitals.parquet"
    if hp.exists():
        import polars as pl
        for r in pl.read_parquet(hp).iter_rows(named=True):
            sysname = r.get("system") or ""
            out[str(r["ccn"])] = {"hospital_name": r.get("hospital_name") or "", "system": sysname,
                                  "website": r.get("website") or "", "tier": tiers.get(sysname.strip().lower(), "")}
    for r in sites_rows():
        if r.get("ccn"):
            sysname = r.get("system", "")
            out.setdefault(r["ccn"], {"hospital_name": r.get("hospital_name", ""), "system": sysname, "website": r.get("website", ""),
                                      "tier": tiers.get(sysname.strip().lower(), "")})
    return out


def in_scope(a, table: dict[str, dict]) -> list[str]:
    if a.ccn:
        return [c.strip() for c in a.ccn.split(",") if c.strip()]
    if a.tier:
        return sorted(c for c, h in table.items() if h["tier"] == a.tier and h["website"])
    return sorted(c for c, h in table.items() if h["website"])


# ----------------------------------------------------------------------------- helpers
def manage(*args: str) -> int:
    cmd = [sys.executable, str(MANAGE), *args]
    print("$", " ".join(cmd[1:]))
    return subprocess.run(cmd, cwd=config.PROJECT_ROOT).returncode


def build_duckdb_fast() -> int:
    if not config.data_paths().duckdb.exists():
        print("no meshkor.duckdb yet: full build")
        return manage("build_duckdb")
    helptxt = subprocess.run([sys.executable, str(MANAGE), "build_duckdb", "--help"], cwd=config.PROJECT_ROOT,
                             capture_output=True, text=True).stdout
    if "--only" in helptxt:
        return manage("build_duckdb", "--only", "ref_hospital_mrf")
    print("build_duckdb --only not installed (meshkor-duckdb-refresh.zip); full rebuild")
    return manage("build_duckdb")


def catalog_rows(paths, ccns: list[str]) -> dict[str, list[dict]]:
    import polars as pl
    p = paths.ref / "hpt_catalog.parquet"
    out: dict[str, list[dict]] = {}
    if not p.exists():
        return out
    for r in pl.read_parquet(p).filter(pl.col("ccn").is_in(ccns)).iter_rows(named=True):
        out.setdefault(str(r["ccn"]), []).append(r)
    return out


def quarantine_records(paths) -> dict[str, dict]:
    d = paths.manifests / "ref_hospital_mrf"
    out = {}
    if d.exists():
        for p in d.glob("*.quarantine.json"):
            rec = json.loads(p.read_text(encoding="utf-8"))
            out[f"{rec['ccn']}_{rec['period']}"] = rec
    return out


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", default=date.today().strftime("%Y-%m"), help="download month, default = this month")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tier"); g.add_argument("--ccn"); g.add_argument("--all", action="store_true")
    ap.add_argument("--via", choices=["auto", "chrome", "requests"], default="auto")
    ap.add_argument("--retry-parked", action="store_true", help="try again hospitals parked in the ledger")
    ap.add_argument("--skip-discover", action="store_true", help="reuse hpt_catalog.parquet")
    ap.add_argument("--skip-load", action="store_true", help="download + validate + register only")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-ip-check", action="store_true", help="--via requests on a US machine without ipinfo access")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}", a.period):
        ap.error("--period must be yyyy-mm")
    paths = config.data_paths(a.data_root)
    period = a.period
    t0 = datetime.now(timezone.utc)

    if a.via == "requests" and not a.skip_ip_check:
        c = public_country()
        print(f"public IP country: {c or 'unknown'}")
        if c != "US":
            raise SystemExit("not a US address: use --via chrome / auto with tools/chrome_hpt.ps1, or a system-wide VPN")
    if a.via in ("auto", "chrome") and not a.dry_run:
        # preflight: Chrome must be up BEFORE anything is tried, or every hospital would be blamed for it
        from . import chrome
        try:
            chrome._connect()
        except RuntimeError as e:
            raise SystemExit(f"STOP: {e}\nStart it, check the VPN icon says a US city, then run this command again.")
    install_via(a.via)
    print(f"fetch mode: {a.via}   period: {period}")

    print("== 1 hospitals")
    try:
        hospitals.build(a.data_root)
    except Exception as e:  # noqa: BLE001
        print(f"hospital list not rebuilt ({str(e).splitlines()[0][:90]}); using what exists")
    table = hospital_table(paths)
    ccns = in_scope(a, table)
    led = Ledger(a.data_root)
    for c in table:                      # every known hospital gets a ledger row for this period
        r = led.get(c, period)
        r.update(hospital_name=table[c]["hospital_name"], system=table[c]["system"], tier=table[c]["tier"])
        if r["state"] == "listed" and table[c]["website"]:
            r["state"] = "website"
        if r["state"] == "listed" and not table[c]["website"]:
            led.fail(c, period, "NO_WEBSITE", "no website in config/hospital_sites.csv")
    todo, skipped = [], {}
    man_dir = paths.manifests / "ref_hospital_mrf"
    for c in ccns:
        if a.retry_parked:
            led.unpark(c, period)
        if (man_dir / f"{c}_{period}.json").exists() and led.get(c, period)["state"] not in ("loaded", "verified"):
            m = json.loads((man_dir / f"{c}_{period}.json").read_text(encoding="utf-8"))
            led.set_state(c, period, "loaded", rows=m.get("rows"), file=m.get("member"), sha256=m.get("source_sha256"),
                          file_dated=m.get("last_updated_on"), detail="loaded earlier (manifest present)")
        why = led.skip(c, period, a.retry_parked)
        (skipped.__setitem__(c, why) if why else todo.append(c))
    print(f"in scope {len(ccns)}; to do {len(todo)}; skipped {len(skipped)} " +
          (f"({', '.join(f'{c}:{w}' for c, w in list(skipped.items())[:8])}{' …' if len(skipped) > 8 else ''})" if skipped else ""))
    if a.dry_run or not todo:
        led.save()
        return 0

    # ---- 2 discover (per site; its own failures are per hospital)
    if not a.skip_discover:
        print("== 2 discover")
        try:
            discover.run(a.data_root, only=todo)
        except Exception as e:  # noqa: BLE001
            led.save()
            raise SystemExit(f"STOP: discover failed as a whole ({str(e)[:160]}). No hospital was blamed; fix the cause and rerun.")
    cat = catalog_rows(paths, todo)
    import polars as pl
    catp = paths.ref / "hpt_catalog.parquet"
    allcat = {str(r["ccn"]): r for r in pl.read_parquet(catp).iter_rows(named=True)} if catp.exists() else {}
    for c in todo:
        rows = sorted([r for r in cat.get(c, []) if r.get("mrf_url")], key=lambda r: -(r.get("match_score") or 0))
        cat[c] = rows
        if rows:
            led.set_state(c, period, "url_found", file=rows[0]["mrf_url"])
            continue
        r = allcat.get(c, {})
        method = r.get("method", "none")
        if method == "cms-hpt-unmatched":
            led.fail(c, period, "UNMATCHED", r.get("note", ""))
        elif method == "blocked":
            led.fail(c, period, "BLOCKED", r.get("note", ""))
        else:
            led.fail(c, period, "NO_HPT_TXT", r.get("note", "no cms-hpt.txt"))
    todo = [c for c in todo if led.rows[(c, period)]["state"] == "url_found"]

    # ---- 3 download + 4 validate + 5 register, one hospital at a time
    print(f"== 3 download / validate / register ({len(todo)} hospitals)")
    log_path = paths.root / "reports" / "hpt_downloads.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    registered: list[str] = []
    sources_path = config.PROJECT_ROOT / "config" / "sources_local.yaml"
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["downloaded_at", "period", "ccn", "hospital_name", "mrf_url", "file", "bytes", "sha256", "result", "note"])
        for i, c in enumerate(todo, 1):
            row = cat[c][0]
            name = table.get(c, {}).get("hospital_name", "")
            print(f"[{i}/{len(todo)}] {c} {name}")
            try:
                o = download.download_one(row, period, paths, a.timeout, w)
            except Exception as e:  # noqa: BLE001
                led.fail(c, period, "CONN", f"{type(e).__name__}: {str(e)[:150]}")
                print(f"   ERROR {e}")
                continue
            if o["result"] == "error":
                led.fail(c, period, o["code"] or "BLOCKED", o["note"], file=row["mrf_url"])
                print(f"   {o['code']} {o['note']}")
                continue
            if o["result"] == "unchanged":
                led.set_state(c, period, "unchanged", detail=o["note"], sha256=o["sha256"])
                print(f"   unchanged ({o['note']})")
                continue
            led.set_state(c, period, "downloaded", file=o["member"], sha256=o["sha256"])
            print(f"   {o['result']} {o['bytes']/1e6:.1f} MB {o['member']}")
            data_path = o["dest"].parent / o["member"]
            ok, code, detail, info = validate.validate(data_path, paths.work / "hpt" / "validate")
            if not ok:
                led.fail(c, period, code, detail, file=o["member"])
                print(f"   INVALID: {code} {detail}")
                continue
            led.set_state(c, period, "validated", file=o["member"], sha256=o["sha256"], detail=detail,
                          file_dated=info.get("last_updated_on", ""))
            print(f"   valid: {detail}")
            msg = intake.write_yaml(intake.yaml_block(period, c, row.get("source_page_url") or row["mrf_url"], o["member"]),
                                    period, c, sources_path)
            led.set_state(c, period, "registered", file=o["member"], sha256=o["sha256"], file_dated=info.get("last_updated_on", ""))
            registered.append(c)
            print(f"   {msg}")
    led.save()

    # ---- 6 load, 7 build, 8 verify (quarantine), 9 quality
    if registered and not a.skip_load:
        print(f"== 6 load_ref ref_hospital_mrf --period {period}  ({len(registered)} new)")
        rc = manage("load_ref", "ref_hospital_mrf", "--period", period)
        qs = quarantine_records(paths)
        for c in registered:
            key = f"{c}_{period}"
            if key in qs and qs[key].get("stage") == "load":
                led.fail(c, period, "PARSE_ERROR", qs[key].get("error", ""))
                intake.remove_release(period, c, sources_path)
                print(f"   QUARANTINED {c}: {qs[key].get('error', '')[:120]}")
            elif (paths.manifests / "ref_hospital_mrf" / f"{key}.json").exists():
                m = json.loads((paths.manifests / "ref_hospital_mrf" / f"{key}.json").read_text(encoding="utf-8"))
                led.set_state(c, period, "loaded", rows=m.get("rows"), file_dated=m.get("last_updated_on"), file=m.get("member"), sha256=m.get("source_sha256"))
            else:
                led.fail(c, period, "PARSE_ERROR", f"load_ref exit {rc}; no manifest written")
        loaded = [c for c in registered if led.rows[(c, period)]["state"] == "loaded"]
        led.save()
        if loaded:
            print("== 7 build_duckdb")
            if build_duckdb_fast():
                print("   build_duckdb failed; the Parquet is loaded, rerun build_duckdb by hand")
            print("== 8 verify")
            res = verify.run(period=period, data_root=a.data_root, do_quarantine=True, only=set(loaded))
            for c in loaded:
                r = res.get(f"{c}_{period}")
                if r is None:
                    continue
                if r["fail"]:
                    led.fail(c, period, "VERIFY_FAIL", "; ".join(r["failures"]), verify=f"{r['fail']} fail")
                    intake.remove_release(period, c, sources_path)
                else:
                    led.set_state(c, period, "verified", rows=r.get("rows"), verify="pass",
                                  file=led.rows[(c, period)]["file"], sha256=led.rows[(c, period)]["sha256"],
                                  file_dated=led.rows[(c, period)]["file_dated"])
            if any(res[f"{c}_{period}"]["quarantined"] for c in loaded if f"{c}_{period}" in res):
                build_duckdb_fast()          # drop the quarantined rows from the database
            print("== 9 quality")
            led.save()
            for c in loaded:
                if led.rows[(c, period)]["state"] == "verified":
                    try:
                        quality.main(["--ccn", c, "--period", period])
                    except Exception as e:  # noqa: BLE001  (a report problem never stops the run)
                        print(f"   quality report for {c} failed: {str(e)[:120]}")
    elif registered:
        print("== load skipped (--skip-load); registered in sources_local.yaml, run load_ref later")

    # ---- 10 progress + ledger + summary
    progress.main([])
    csv_p, xlsx_p = led.save()
    s = led.summary()
    counts = {k: v for k, v in s.items() if k != "codes" and v}
    lines = [f"# Hospital price run {t0:%Y-%m-%d %H:%M} UTC, period {period}", "",
             f"Scope: {len(ccns)} hospitals · tried {len(todo)} · registered {len(registered)} · "
             f"took {(datetime.now(timezone.utc) - t0).seconds // 60} min", "",
             "| State | Hospitals |", "|---|---|"] + [f"| {k} | {v} |" for k, v in counts.items()]
    if s["codes"]:
        lines += ["", "## Needs a person", "", "| Reason | Hospitals | Next action |", "|---|---|---|"]
        from .ledger import CODES
        for code, names in s["codes"].items():
            lines.append(f"| {code} | {', '.join(names[:10])}{' …' if len(names) > 10 else ''} | {CODES.get(code, (0, ''))[1]} |")
    lines += ["", f"Ledger: `{csv_p}`" + (f", `{xlsx_p}`" if xlsx_p else "")]
    rep = paths.root / "reports" / f"hpt_run_{t0:%Y%m%d_%H%M}.md"
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"-> {rep}")
    from . import chrome
    chrome.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
