"""Verify ref_hospital_mrf, one hospital × period at a time, against the raw file and its manifest.

Checks per release (data/ref/_manifest/ref_hospital_mrf/<ccn>_<period>.json):
  manifest exists · raw folder hash unchanged · parquet has rows · rows parquet = rows csv (tall)
  · lineage filled · one source hash · no negative prices · rows without a code <= 2 %
  · code types unmapped <= 2 % · payer_group set · one hospital name · CCN in the data = release CCN
Writes data/reports/verify_hpt.md. Exit 1 on any FAIL.

--quarantine : a release that fails is moved out of the table (data/ref/_quarantine/ref_hospital_mrf/)
               with a .quarantine.json beside its manifest, so the database never holds unverified data.
Run:  python -m pipeline.hpt.verify [--ccn 360085] [--period 2026-11] [--quarantine]
"""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ..common import config
from ..ref.hospital_mrf import layout_of, read_prefix

SOFT_PCT = 2.0   # rows without a code / with an unmapped code type: FAIL above this share


def release_manifests(paths) -> dict[str, dict]:
    d = paths.manifests / "ref_hospital_mrf"
    out = {}
    if d.exists():
        for p in sorted(d.glob("*.json")):
            if p.name.endswith(".quarantine.json"):
                continue
            m = json.loads(p.read_text(encoding="utf-8"))
            out[f"{m['ccn']}_{m['period']}"] = m
    return out


def quarantine(paths, ccn: str, period: str, reason: str, failures: list[str]) -> Path:
    """Move the release's Parquet out of the table and record why."""
    key = f"{ccn}_{period}"
    src = paths.ref / "ref_hospital_mrf" / key
    qdir = paths.ref / "_quarantine" / "ref_hospital_mrf"
    qdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    if src.exists():
        shutil.move(str(src), qdir / f"{key}_{stamp}")
    man = paths.manifests / "ref_hospital_mrf" / f"{key}.json"
    rec = {"table": "ref_hospital_mrf", "ccn": ccn, "period": period, "stage": "verify", "error": reason,
           "failures": failures, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if man.exists():
        rec["manifest"] = json.loads(man.read_text(encoding="utf-8"))
        man.unlink()
    q = paths.manifests / "ref_hospital_mrf" / f"{key}.quarantine.json"
    q.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    # keep the table-level manifest honest (build_duckdb compares its rows with the table)
    tm = paths.manifests / "ref_hospital_mrf.json"
    if tm.exists():
        try:
            t = json.loads(tm.read_text(encoding="utf-8"))
            t["rows"] = sum(int(m.get("rows") or 0) for m in release_manifests(paths).values())
            tm.write_text(json.dumps(t, indent=2, default=str), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return q


def run(ccn: str = "", period: str = "", data_root: str | None = None, do_quarantine: bool = False,
        only: set[str] | None = None) -> dict:
    """Returns {key: {"pass": n, "fail": n, "failures": [names], "quarantined": bool}}."""
    paths = config.data_paths(data_root)
    mans = release_manifests(paths)
    if not mans:
        raise SystemExit("no release manifests: run  load_ref ref_hospital_mrf  first")
    con = duckdb.connect()
    table_dir = paths.ref / "ref_hospital_mrf"
    results: dict[str, dict] = {}
    lines = []
    for key, m in mans.items():
        c, per = str(m["ccn"]), str(m["period"])
        if (ccn and c != ccn) or (period and per != period):
            continue
        checks: list[tuple[str, bool, str]] = []
        chk = lambda name, ok, detail="": checks.append((name, bool(ok), detail))
        folder = table_dir / key
        part = folder / "part-000.parquet"
        chk("parquet folder exists", part.exists(), str(folder))
        raw_dir = paths.raw / m["file"]
        local = None
        if raw_dir.exists():
            from ..common.raw import RawFile
            rf = RawFile(paths.raw, m["file"])
            chk("raw folder unchanged", rf.sha256 == m.get("raw_sha256"), rf.sha256[:16] + "…")
            try:
                local = rf.member(m["member"]).local_path(paths.work)
            except Exception as e:  # noqa: BLE001
                chk("raw member found", False, str(e)[:80])
        else:
            chk("raw folder present", False, str(raw_dir))
        if part.exists():
            W = f"(SELECT * FROM read_parquet('{part.as_posix()}'))"
            n_pq = con.execute(f"SELECT count(*) FROM {W}").fetchone()[0]
            chk("parquet has rows", n_pq > 0, f"{n_pq:,}")
            chk("rows = manifest", n_pq == int(m.get("rows") or -1), f"{n_pq:,} = {m.get('rows'):,}")
            if local and local.suffix.lower() == ".csv":
                try:
                    _, header, skip = read_prefix(local)
                    layout = layout_of(header)
                    read_path = local
                    clean = paths.work / "hpt" / (local.stem + ".utf8.csv")
                    if clean.exists():
                        read_path = clean
                    def _cnt(extra=""):
                        return con.execute(f"""SELECT count(*) FROM read_csv('{read_path.as_posix()}', skip={skip}, header=true,
                            all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false{extra})""").fetchone()[0]
                    try:
                        n_raw = _cnt()
                    except duckdb.Error:
                        n_raw = _cnt(", null_padding=true")
                    if layout == "tall":
                        chk("rows parquet = rows csv", n_pq == n_raw, f"{n_pq:,} = {n_raw:,}")
                    else:
                        chk("wide file rows (info)", True, f"{n_raw:,} code rows -> {n_pq:,} payer rows")
                except Exception as e:  # noqa: BLE001
                    chk("raw csv readable", False, str(e)[:80])
            q = lambda sql: con.execute(sql.replace("__W__", W)).fetchone()[0]
            chk("lineage filled", q("SELECT count(*) FROM __W__ WHERE source_sha256 IS NULL OR effective_start IS NULL OR period IS NULL OR ccn IS NULL") == 0)
            chk("one source hash", q("SELECT count(DISTINCT source_sha256) FROM __W__") == 1)
            chk("ccn matches release", q(f"SELECT count(*) FROM __W__ WHERE ccn <> '{c}'") == 0)
            chk("no negative prices", q("SELECT count(*) FROM __W__ WHERE gross_charge < 0 OR negotiated_dollar < 0 OR charge_min < 0 OR charge_max < 0") == 0)
            nocode = q("SELECT count(*) FROM __W__ WHERE code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL")
            chk(f"rows without a code <= {SOFT_PCT} %", 100 * nocode / n_pq <= SOFT_PCT, f"{nocode:,} ({100*nocode/n_pq:.2f} %)")
            has_other = "code_other" in [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {W}").fetchall()]
            unm = q("SELECT count(*) FROM __W__ WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL"
                    + (" AND code_other IS NULL" if has_other else "") + " AND NOT (code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL)")
            chk(f"unmapped code types <= {SOFT_PCT} %", 100 * unm / n_pq <= SOFT_PCT, f"{unm:,} ({100*unm/n_pq:.2f} %)")
            chk("payer_group set on every payer row", q("SELECT count(*) FROM __W__ WHERE payer_name IS NOT NULL AND payer_group IS NULL") == 0)
            chk("one hospital name", q("SELECT count(DISTINCT hospital_name) FROM __W__") == 1)
        fails = [n for n, ok, _ in checks if not ok]
        res = {"pass": len(checks) - len(fails), "fail": len(fails), "failures": fails, "quarantined": False,
               "hospital_name": m.get("hospital_name"), "rows": m.get("rows")}
        if fails and do_quarantine and (only is None or c in only):
            quarantine(paths, c, per, "verification failed: " + "; ".join(fails), fails)
            res["quarantined"] = True
        results[key] = res
        for n, ok, d in checks:
            lines.append(f"| {c} | {per} | {n} | {'PASS' if ok else 'FAIL'} | {d} |")
            print(f"{'PASS' if ok else 'FAIL'}  {c}/{per}: {n}  {d}")
        if res["quarantined"]:
            print(f"QUARANTINED {c}/{per}: {', '.join(fails)}")
    con.close()
    tot_pass = sum(r["pass"] for r in results.values()); tot_fail = sum(r["fail"] for r in results.values())
    rep = paths.root / "reports" / "verify_hpt.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    head = [f"# verify ref_hospital_mrf", "", f"Run {datetime.now(timezone.utc).isoformat(timespec='seconds')}  "
            f"Result: **{tot_pass} pass, {tot_fail} fail** over {len(results)} releases", "",
            "| CCN | Period | Hospital | Pass | Fail | Quarantined |", "|---|---|---|---|---|---|"]
    head += [f"| {k.split('_')[0]} | {k.split('_',1)[1]} | {r['hospital_name']} | {r['pass']} | {r['fail']} | {'yes' if r['quarantined'] else ''} |" for k, r in results.items()]
    rep.write_text("\n".join(head + ["", "| CCN | Period | Check | Result | Detail |", "|---|---|---|---|---|"] + lines) + "\n", encoding="utf-8")
    print(f"\n{tot_pass} pass, {tot_fail} fail over {len(results)} releases -> {rep}")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ccn", default=""); ap.add_argument("--period", default="")
    ap.add_argument("--quarantine", action="store_true")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    res = run(a.ccn, a.period, a.data_root, a.quarantine)
    return 1 if any(r["fail"] for r in res.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
