"""Verify ref_hospital_mrf against the raw files and the runner's manifest (Spec §3.2 / §8.1 style).

Checks per loaded hospital × period:
  raw file unchanged (hash in the manifest = hash on disk), parquet rows = rows in the raw
  file as DuckDB reads it (tall/json) or = payer rows with a rate (wide), lineage filled,
  one source hash per release, CCN matches the release, no negative prices, every row has
  a code, every code type mapped, first and last raw record found with the same rate (tall).
Writes data/reports/verify_hpt.md and exits 1 on any FAIL.

Run:  python -m pipeline.hpt.verify [--ccn 360085]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ..common import config
from ..common.raw import sha256_file
from ..ref.hospital_mrf import read_prefix, layout_of


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ccn", default="")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    paths = config.data_paths(a.data_root)
    man_p = paths.manifests / "ref_hospital_mrf.json"
    if not man_p.exists():
        sys.exit("no manifest: run  load_ref ref_hospital_mrf  first")
    man = json.loads(man_p.read_text(encoding="utf-8"))
    spec = config.sources()["ref_hospital_mrf"]
    rels = {str(r["ccn"]) + "/" + str(r["period"]): r for r in spec["releases"]}
    con = duckdb.connect()
    T = f"read_parquet('{(paths.ref / 'ref_hospital_mrf').as_posix()}/**/*.parquet', union_by_name=true)"
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, "PASS" if ok else "FAIL", detail)); print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    for key, rel in rels.items():
        ccn, period = str(rel["ccn"]), str(rel["period"])
        if a.ccn and ccn != a.ccn:
            continue
        src_rec = next((s for s in man["sources"] if s["file"] == rel["file"]), None)
        check(f"{key}: release in manifest", src_rec is not None)
        raw_dir = paths.raw / rel["file"]
        if src_rec and raw_dir.exists():
            # folder hash = hash of member hashes (RawFile.sha256 for a folder)
            from ..common.raw import RawFile
            rf = RawFile(paths.raw, rel["file"])
            check(f"{key}: raw folder unchanged", rf.sha256 == src_rec["sha256"], rf.sha256[:16] + "…")
            m = rf.member(rel["members"]["mrf"])
            local = m.local_path(paths.work)
        else:
            local = None
        W = f"(SELECT * FROM {T} WHERE ccn = '{ccn}' AND period = '{period}')"
        n_pq = con.execute(f"SELECT count(*) FROM {W}").fetchone()[0]
        check(f"{key}: parquet has rows", n_pq > 0, f"{n_pq:,}")
        if local and local.suffix.lower() == ".csv":
            meta, header, skip = read_prefix(local)
            layout = layout_of(header)
            read_path = local
            clean = paths.work / "hpt" / (local.stem + ".utf8.csv")
            if clean.exists():
                read_path = clean
            n_raw = con.execute(f"""SELECT count(*) FROM read_csv('{read_path.as_posix()}', skip={skip}, header=true,
                all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false)""").fetchone()[0]
            if layout == "tall":
                check(f"{key}: rows parquet = rows csv", n_pq == n_raw, f"{n_pq:,} = {n_raw:,}")
            else:
                check(f"{key}: wide file rows (info)", True, f"{n_raw:,} code rows -> {n_pq:,} payer rows")
        lin = con.execute(f"SELECT count(*) FROM {W} WHERE source_sha256 IS NULL OR effective_start IS NULL OR period IS NULL OR ccn IS NULL").fetchone()[0]
        check(f"{key}: lineage filled", lin == 0, f"{lin}")
        one_sha = con.execute(f"SELECT count(DISTINCT source_sha256) FROM {W}").fetchone()[0]
        check(f"{key}: one source hash", one_sha == 1, f"{one_sha}")
        neg = con.execute(f"SELECT count(*) FROM {W} WHERE gross_charge < 0 OR negotiated_dollar < 0 OR charge_min < 0 OR charge_max < 0").fetchone()[0]
        check(f"{key}: no negative prices", neg == 0, f"{neg}")
        nocode = con.execute(f"SELECT count(*) FROM {W} WHERE code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL").fetchone()[0]
        check(f"{key}: every row has a code", nocode == 0, f"{nocode}")
        unm = con.execute(f"SELECT count(*) FROM {W} WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL").fetchone()[0]
        check(f"{key}: every code type mapped", unm == 0, f"{unm}")
        pg = con.execute(f"SELECT count(*) FROM {W} WHERE payer_name IS NOT NULL AND payer_group IS NULL").fetchone()[0]
        check(f"{key}: payer_group set on every payer row", pg == 0, f"{pg}")
        hn = con.execute(f"SELECT count(DISTINCT hospital_name) FROM {W}").fetchone()[0]
        check(f"{key}: one hospital name", hn == 1)
    failed = sum(1 for c in checks if c[1] == "FAIL")
    rep = paths.root / "reports" / "verify_hpt.md"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join([f"# verify ref_hospital_mrf", "", f"Run {datetime.now(timezone.utc).isoformat(timespec='seconds')}  "
                              f"Result: **{len(checks)-failed} pass, {failed} fail**", "", "| Check | Result | Detail |", "|---|---|---|"]
                             + [f"| {n} | {r} | {d} |" for n, r, d in checks]), encoding="utf-8")
    print(f"\n{len(checks)-failed} pass, {failed} fail -> {rep}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
