#!/usr/bin/env python
"""
verify_mrf.py: prove that a loaded hospital price file matches its raw download.

Usage (from D:\\meshkor-data):
    python verify_mrf.py --ccn 360085 --period 2026-10
    python verify_mrf.py --ccn 360085 --period 2026-10 --duckdb data\\meshkor.duckdb   # also check the view

Writes data\\reports\\verify_mrf_<ccn>_<period>.md and exits 1 if any check fails.
"""
import argparse, csv, hashlib, io, json, sys
from datetime import datetime
from pathlib import Path

import duckdb

TABLE = "ref_hospital_mrf"


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def count_csv_records(con, path: Path, skip: int) -> int:
    """Count data records exactly the way the loader read them (DuckDB, lenient quotes)."""
    return con.execute(f"""SELECT count(*) FROM read_csv('{path.as_posix()}', skip={skip}, header=true,
        all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8')""").fetchone()[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccn", required=True)
    ap.add_argument("--period", required=True)
    ap.add_argument("--data", default="data")
    ap.add_argument("--duckdb", default="", help="optional: path of meshkor.duckdb to check the view too")
    a = ap.parse_args()

    man = Path(a.data) / "ref" / "_manifest" / TABLE / f"{a.ccn}_{a.period}.json"
    if not man.exists():
        sys.exit(f"manifest not found: {man}  (run load_mrf.py first)")
    m = json.loads(man.read_text())
    pq = Path(m["output"])
    raw = Path(m["raw_folder"])
    src = raw / m["sources"][0]["file"]
    checks = []

    def check(name, ok, detail=""):
        checks.append((name, "PASS" if ok else "FAIL", detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

    # 1. raw file unchanged since load (Spec §3.2)
    for s in m["sources"]:
        p = raw / s["file"]
        if p.exists():
            h = sha256_file(p)
            check(f"raw unchanged: {s['file']}", h == s["sha256"], h[:16] + "…")
        else:
            check(f"raw present: {s['file']}", False, "missing")

    # 2. parquet exists and row count = CSV records
    check("parquet exists", pq.exists(), str(pq))
    con = duckdb.connect()
    n_pq = con.execute(f"SELECT count(*) FROM '{pq.as_posix()}'").fetchone()[0]
    read_path = Path(m.get("read_path", src))
    n_csv = count_csv_records(con, read_path, m["header_lines_skipped"])
    check("rows parquet = rows csv", n_pq == n_csv, f"{n_pq:,} = {n_csv:,}")
    check("rows = manifest", n_pq == m["rows"], f"{n_pq:,}")

    # 3. lineage columns present and filled (§8.1)
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{pq.as_posix()}'").fetchall()}
    need = {"effective_start", "effective_end", "source_file", "source_sha256", "period", "ccn"}
    check("lineage columns present", need <= cols, ", ".join(sorted(need - cols)) or "all 6")
    nulls = con.execute(f"""SELECT count(*) FROM '{pq.as_posix()}'
        WHERE ccn IS NULL OR period IS NULL OR source_sha256 IS NULL OR effective_start IS NULL""").fetchone()[0]
    check("lineage never null", nulls == 0, f"{nulls} bad rows")
    one_sha = con.execute(f"SELECT count(DISTINCT source_sha256) FROM '{pq.as_posix()}'").fetchone()[0]
    check("one source hash", one_sha == 1)

    # 4. content sanity
    q = lambda s: con.execute(s.replace("FROM T", f"FROM '{pq.as_posix()}'")).fetchone()[0]
    neg = q("SELECT count(*) FROM T WHERE gross_charge < 0 OR negotiated_dollar < 0 OR charge_min < 0 OR charge_max < 0")
    check("no negative prices", neg == 0, f"{neg}")
    no_code = q("SELECT count(*) FROM T WHERE code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL AND code_4 IS NULL")
    check("every row has a code", no_code == 0, f"{no_code} rows without any code")
    unmapped = q("SELECT count(*) FROM T WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL")
    check("every code type is mapped to a join column", unmapped == 0, f"{unmapped} rows with an unknown code type")
    types = con.execute(f"""SELECT t, count(*) FROM (SELECT code_1_type AS t FROM '{pq.as_posix()}' UNION ALL
        SELECT code_2_type FROM '{pq.as_posix()}' UNION ALL SELECT code_3_type FROM '{pq.as_posix()}')
        WHERE t IS NOT NULL GROUP BY 1 ORDER BY 2 DESC""").fetchall()
    print("  code types:", ", ".join(f"{t} {n:,}" for t, n in types))
    bad_set = q("SELECT count(*) FROM T WHERE setting NOT IN ('Inpatient','Outpatient','Both') OR setting IS NULL")
    check("setting is Inpatient/Outpatient/Both", bad_set == 0, f"{bad_set}")
    no_rate = q("SELECT count(*) FROM T WHERE negotiated_dollar IS NULL AND negotiated_percentage IS NULL AND negotiated_algorithm IS NULL AND estimated_amount IS NULL")
    check("rate rows carry dollar, %, algorithm or estimate (info)", True, f"{no_rate:,} rows have none")

    # 5. spot values against the raw CSV: first and last data record
    rel = con.execute(f"""SELECT * FROM read_csv('{read_path.as_posix()}', skip={m["header_lines_skipped"]},
        header=true, all_varchar=true, quote='"', escape='"', delim=',', strict_mode=false, encoding='utf-8')""")
    hdr = [c[0].strip() for c in rel.description]
    first = rel.fetchone()
    last = con.execute(f"""SELECT * FROM (SELECT *, row_number() OVER () AS rn FROM read_csv('{read_path.as_posix()}',
        skip={m["header_lines_skipped"]}, header=true, all_varchar=true, quote='"', escape='"', delim=',',
        strict_mode=false, encoding='utf-8')) ORDER BY rn DESC LIMIT 1""").fetchone()[:-1]
    ci = {c: i for i, c in enumerate(hdr)}
    def money(v):
        v = v.replace("$", "").replace(",", "").strip()
        return float(v) if v else None
    for label, row in (("first", first), ("last", last)):
        desc = row[ci["description"]].replace("'", "''")
        payer = row[ci["payer_name"]].replace("'", "''")
        plan = row[ci["plan_name"]].replace("'", "''")
        exp = money(row[ci["standard_charge|negotiated_dollar"]])
        got = con.execute(f"""SELECT negotiated_dollar FROM '{pq.as_posix()}'
            WHERE description = '{desc}' AND payer_name = '{payer}' AND plan_name = '{plan}'
              AND code_1 = '{row[ci['code|1']]}' LIMIT 1""").fetchone()
        check(f"{label} csv record found with same rate", got is not None and got[0] == exp,
              f"{row[ci['code|1']]} / {payer} / {exp}")

    # 6. summary numbers for the register
    summ = con.execute(f"""SELECT count(DISTINCT payer_name), count(DISTINCT plan_name),
        count(DISTINCT hcpcs), count(DISTINCT ms_drg) + count(DISTINCT apr_drg), count(DISTINCT ndc),
        sum(CASE WHEN setting='Inpatient' THEN 1 ELSE 0 END), sum(CASE WHEN setting='Outpatient' THEN 1 ELSE 0 END)
        FROM '{pq.as_posix()}'""").fetchone()
    print(f"\npayers={summ[0]} plans={summ[1]} hcpcs={summ[2]:,} drgs={summ[3]:,} ndcs={summ[4]:,} "
          f"inpatient={summ[5]:,} outpatient={summ[6]:,}")

    # 7. optional: the DuckDB view sees the same rows
    if a.duckdb:
        try:
            db = duckdb.connect(a.duckdb, read_only=True)
            n_db = db.execute(f"SELECT count(*) FROM {TABLE} WHERE ccn='{a.ccn}' AND period='{a.period}'").fetchone()[0]
            check("duckdb view rows = parquet rows", n_db == n_pq, f"{n_db:,}")
        except Exception as e:
            check("duckdb view present", False, str(e)[:120])

    # report
    failed = sum(1 for c in checks if c[1] == "FAIL")
    rep = Path(a.data) / "reports"; rep.mkdir(parents=True, exist_ok=True)
    out = rep / f"verify_mrf_{a.ccn}_{a.period}.md"
    lines = [f"# verify {TABLE} ccn={a.ccn} period={a.period}", "",
             f"Run: {datetime.now().isoformat(timespec='seconds')}  Result: **{len(checks)-failed} pass, {failed} fail**", "",
             f"Hospital: {m['hospital_name']}  file dated {m['last_updated_on']}  template v{m['mrf_version']}",
             f"Raw: `{src}`  SHA-256 `{m['sources'][0]['sha256']}`",
             f"Parquet: `{pq}`  rows {n_pq:,}", "",
             "| Check | Result | Detail |", "|---|---|---|"]
    lines += [f"| {n} | {r} | {d} |" for n, r, d in checks]
    lines += ["", f"Payers {summ[0]}, plans {summ[1]}, HCPCS codes {summ[2]:,}, MS-DRGs {summ[3]:,}, NDCs {summ[4]:,}, "
              f"inpatient rows {summ[5]:,}, outpatient rows {summ[6]:,}."]
    if m.get("warnings"):
        lines += ["", "Warnings:"] + [f"- {w}" for w in m["warnings"]]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(checks)-failed} pass, {failed} fail  →  {out}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
