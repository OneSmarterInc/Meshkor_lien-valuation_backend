r"""One table for all hospitals: is the file in the right raw folder, registered, and is there a
Parquet? Reads only. Writes data\reports\hpt_where.csv.

  python tools\where_is_everything.py            (period 2026-10)
  python tools\where_is_everything.py --period 2026-10
Status:  OK | QUARANTINED | NO PARQUET | NOT REGISTERED | NO FILE
"""
import argparse, json, re, sys
from pathlib import Path

import duckdb
import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline.common import config  # noqa: E402

ap = argparse.ArgumentParser(); ap.add_argument("--period", default="2026-10"); a = ap.parse_args()
P = config.data_paths(); per = a.period
print("raw folder :", P.raw)
hosp = pl.read_parquet(P.ref / "hpt_hospitals.parquet").select("ccn", "hospital_name", "system").to_dicts()
hosp = [h for h in hosp if not h["ccn"].startswith("369")]
yaml_txt = Path("config/sources_local.yaml").read_text(encoding="utf-8-sig")
reg = set(re.findall(r'period:\s*"%s"\s*\n\s*ccn:\s*"(\d{6})"' % re.escape(per), yaml_txt))
con = duckdb.connect()
rows = []
for h in hosp:
    c = h["ccn"]
    d = P.raw / "MRF" / per / c
    files = [f for f in d.iterdir() if f.is_file() and f.name != "SHA256SUMS.txt"
             and f.suffix.lower() not in (".part", ".crdownload")] if d.exists() else []
    big = max(files, key=lambda f: f.stat().st_size) if files else None
    pq = P.ref / "ref_hospital_mrf" / f"{c}_{per}" / "part-000.parquet"
    n = con.execute(f"SELECT count(*) FROM read_parquet('{pq.as_posix()}')").fetchall()[0][0] if pq.exists() else 0
    qf = P.manifests / "ref_hospital_mrf" / f"{c}_{per}.quarantine.json"
    q = ""
    if qf.exists():
        try: q = (json.loads(qf.read_text(encoding="utf-8")).get("error") or "")[:70]
        except Exception: q = "quarantined"
    if qf.exists(): st = "QUARANTINED"
    elif not files: st = "NO FILE"
    elif c not in reg: st = "NOT REGISTERED"
    elif n == 0: st = "NO PARQUET"
    else: st = "OK"
    rows.append(dict(ccn=c, status=st, hospital=h["hospital_name"], system=h["system"] or "", files=len(files),
                     file_mb=round(big.stat().st_size / 1e6, 1) if big else 0, registered="yes" if c in reg else "no",
                     parquet_rows=n, note=q))
df = pl.DataFrame(rows)
out = P.ref.parent / "reports" / "hpt_where.csv"; out.parent.mkdir(parents=True, exist_ok=True); df.write_csv(out)
print("\n", df.group_by("status").len().sort("len", descending=True), sep="")
print("total hospitals:", df.height)
for st in ("QUARANTINED", "NO PARQUET", "NOT REGISTERED", "NO FILE"):
    sub = df.filter(pl.col("status") == st)
    if sub.height:
        print(f"\n{st} ({sub.height})")
        for r in sub.iter_rows(named=True):
            print(f"  {r['ccn']}  {r['hospital'][:42]:42} {r['system'][:18]:18} {r['file_mb']:>8} MB  {r['note']}")
print("\nfull table:", out)