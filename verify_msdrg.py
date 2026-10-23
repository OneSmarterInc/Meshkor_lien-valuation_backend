#!/usr/bin/env python
"""
verify_msdrg.py: prove the loaded MS-DRG tables match the raw definitions manual text.

Usage (from D:\\meshkor-data):
    python verify_msdrg.py                 # every version with a manifest
    python verify_msdrg.py --version V44

Writes data\\reports\\verify_msdrg.md and exits 1 if any check fails.
"""
import argparse, hashlib, json, re, sys
from datetime import datetime
from pathlib import Path

import duckdb

GOLDEN = {  # DRG -> words that must appear in its title (stable across versions)
    "470": ["Major Hip", "Joint Replacement", "without MCC"],
    "291": ["Heart Failure", "with MCC"],
    "871": ["Sepsis", "with MCC"],
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="")
    ap.add_argument("--data", default="data")
    a = ap.parse_args()
    man_dir = Path(a.data) / "ref" / "_manifest" / "ref_msdrg"
    mans = [man_dir / f"{a.version}.json"] if a.version else sorted(man_dir.glob("V*.json"))
    if not mans or not mans[0].exists():
        sys.exit(f"no manifests in {man_dir} (run load_msdrg.py first)")
    con = duckdb.connect()
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, "PASS" if ok else "FAIL", detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    ipps = Path(a.data) / "ref" / "ref_ipps_drg.parquet"
    for mp in mans:
        m = json.loads(mp.read_text()); v = m["version"]; raw = Path(m["raw_folder"])
        print(f"== {v}")
        for s in m["sources"]:
            p = raw / s["file"]
            if p.exists():
                check(f"{v}: raw unchanged {s['file']}", sha256_file(p) == s["sha256"])
            else:
                check(f"{v}: raw present {s['file']}", False, "missing")
        # independent recounts from the text files
        n_a = sum(1 for ln in (raw / "appendix_A.txt").read_text(encoding="utf-8", errors="replace").splitlines()
                  if re.match(r"^\d{3} ", ln))
        n_b_codes = sum(1 for ln in (raw / "appendix_B.txt").read_text(encoding="utf-8", errors="replace").splitlines()
                        if re.match(r"^ [A-Z]\w+\s+\d{2}\s", ln))
        n_c = sum(1 for ln in (raw / "appendix_C.txt").read_text(encoding="utf-8", errors="replace").splitlines()
                  if re.match(r"^ [A-Z]\w+\s+(CC|MCC)\s", ln))
        T = {t: f"'{Path(i['output']).as_posix()}'" for t, i in m["tables"].items()}
        for t in T:
            check(f"{v}: {t} parquet exists", Path(m["tables"][t]["output"]).exists())
        n_drg = con.execute(f"SELECT count(*) FROM {T['ref_msdrg']}").fetchone()[0]
        check(f"{v}: ref_msdrg rows = DRG lines in appendix A", n_drg == n_a, f"{n_drg} = {n_a}")
        n_dxc = con.execute(f"SELECT count(DISTINCT icd10) FROM {T['ref_msdrg_dx']}").fetchone()[0]
        check(f"{v}: ref_msdrg_dx distinct codes = code lines in appendix B", n_dxc == n_b_codes, f"{n_dxc:,} = {n_b_codes:,}")
        n_cc = con.execute(f"SELECT count(*) FROM {T['ref_msdrg_cc']}").fetchone()[0]
        check(f"{v}: ref_msdrg_cc rows = CC/MCC lines in appendix C part 1", n_cc == n_c, f"{n_cc:,} = {n_c:,}")
        dup = con.execute(f"SELECT count(*) - count(DISTINCT ms_drg) FROM {T['ref_msdrg']}").fetchone()[0]
        check(f"{v}: ref_msdrg has no duplicate DRG", dup == 0, f"{dup}")
        bad = con.execute(f"SELECT count(*) FROM {T['ref_msdrg']} WHERE ms_drg NOT SIMILAR TO '[0-9]{{3}}' OR title IS NULL OR title = ''").fetchone()[0]
        check(f"{v}: every DRG is 3 digits with a title", bad == 0, f"{bad}")
        orphan = con.execute(f"""SELECT count(DISTINCT drg_from) FROM {T['ref_msdrg_dx']} d
                                 WHERE NOT EXISTS (SELECT 1 FROM {T['ref_msdrg']} r WHERE r.ms_drg = d.drg_from)""").fetchone()[0]
        check(f"{v}: every DRG in appendix B exists in appendix A", orphan == 0, f"{orphan} unknown DRGs")
        lev = con.execute(f"SELECT count(*) FROM {T['ref_msdrg_cc']} WHERE cc_level NOT IN ('CC','MCC')").fetchone()[0]
        check(f"{v}: cc_level is CC or MCC", lev == 0, f"{lev}")
        leak = con.execute(f"""SELECT count(*) FROM {T['ref_msdrg_cc']} WHERE regexp_matches(description, '^[0-9]{{2,4}}:')
                               OR description LIKE '%codes %' OR description LIKE 'No Excl%'""").fetchone()[0]
        check(f"{v}: CC descriptions hold no exclusion-group fragments", leak == 0, f"{leak}")
        n_excl = con.execute(f"SELECT count(*) FROM {T['ref_msdrg_cc_excl']}").fetchone()[0]
        check(f"{v}: cc exclusions (part 3) loaded or absent in this version (info)", True, f"{n_excl:,} rows")
        for drg, words in GOLDEN.items():
            t = con.execute(f"SELECT title FROM {T['ref_msdrg']} WHERE ms_drg = '{drg}'").fetchone()
            ok = t is not None and all(w.lower() in t[0].lower() for w in words)
            check(f"{v}: DRG {drg} title", ok, (t[0][:60] if t else "missing"))
        lin = con.execute(f"SELECT count(*) FROM {T['ref_msdrg']} WHERE period IS NULL OR source_sha256 IS NULL OR effective_start IS NULL").fetchone()[0]
        check(f"{v}: lineage filled", lin == 0)
        if ipps.exists() and not v.endswith(".1"):
            fy = m["fiscal_year"]
            n_ipps = con.execute(f"SELECT count(*) FROM '{ipps.as_posix()}' WHERE period = '{fy}'").fetchone()[0]
            if n_ipps:
                check(f"{v}: DRG count = ref_ipps_drg {fy} (Table 5)", n_drg == n_ipps, f"{n_drg} = {n_ipps}")

    failed = sum(1 for c in checks if c[1] == "FAIL")
    rep = Path(a.data) / "reports"; rep.mkdir(parents=True, exist_ok=True)
    out = rep / "verify_msdrg.md"
    lines = ["# verify ref_msdrg", "", f"Run: {datetime.now().isoformat(timespec='seconds')}  Result: **{len(checks)-failed} pass, {failed} fail**", "",
             "| Check | Result | Detail |", "|---|---|---|"] + [f"| {n} | {r} | {d} |" for n, r, d in checks]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(checks)-failed} pass, {failed} fail  →  {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
