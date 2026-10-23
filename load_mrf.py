#!/usr/bin/env python
"""
load_mrf.py: load one hospital price transparency file (CMS tall CSV, template v2.x/v3.x)
into Parquet with the 5 MeshKor lineage columns, and write a manifest.

Usage (from D:\\meshkor-data):
    python load_mrf.py --ccn 360085 --period 2026-10 ^
        --raw "E:\\Hansavahini\\Datasetof CMS\\MRF\\2026-10\\360085" ^
        --page https://wexnermedical.osu.edu/patient-and-visitor-guide/patient-pricing-lists

Output:
    data\\ref\\ref_hospital_mrf\\ccn=360085\\period=2026-10\\part-000.parquet
    data\\ref\\_manifest\\ref_hospital_mrf\\360085_2026-10.json

The raw folder is never changed. Re-running replaces that ccn/period partition only.
"""
import argparse, csv, hashlib, io, json, os, sys, time
from datetime import date, datetime
from pathlib import Path

import duckdb

TABLE = "ref_hospital_mrf"

# CMS header -> our column. Both v2.x and v3.x tall layouts are covered.
COLMAP = {
    "description": "description",
    "code|1": "code_1", "code|1|type": "code_1_type",
    "code|2": "code_2", "code|2|type": "code_2_type",
    "code|3": "code_3", "code|3|type": "code_3_type",
    "code|4": "code_4", "code|4|type": "code_4_type",
    "modifiers": "modifiers",
    "setting": "setting",
    "drug_unit_of_measurement": "drug_unit",
    "drug_type_of_measurement": "drug_type",
    "standard_charge|gross": "gross_charge",
    "standard_charge|discounted_cash": "discounted_cash",
    "payer_name": "payer_name",
    "plan_name": "plan_name",
    "standard_charge|negotiated_dollar": "negotiated_dollar",
    "standard_charge|negotiated_percentage": "negotiated_percentage",
    "standard_charge|negotiated_algorithm": "negotiated_algorithm",
    "estimated_amount": "estimated_amount",
    "median_amount": "median_amount",
    "10th_percentile": "pct_10",
    "90th_percentile": "pct_90",
    "count": "rate_count",
    "standard_charge|methodology": "methodology",
    "standard_charge|min": "charge_min",
    "standard_charge|max": "charge_max",
    "additional_generic_notes": "notes",
}
MONEY = {"gross_charge", "discounted_cash", "negotiated_dollar", "negotiated_percentage",
         "estimated_amount", "median_amount", "pct_10", "pct_90", "charge_min", "charge_max"}
INTS = {"rate_count"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_prefix(csv_path: Path):
    """Return (hospital_header, hospital_values, column_header, lines_to_skip).

    Rows 1-2 are the hospital block, row 3 is the column header. A quoted field may
    contain a newline, so records are cut where the quote count is even.
    """
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        text = f.read(300_000)
    rows, lines_per_row, buf, n = [], [], "", 0
    for line in io.StringIO(text):
        buf += line; n += 1
        if buf.count('"') % 2 == 0:
            rows.append(next(csv.reader(io.StringIO(buf))))
            lines_per_row.append(n); buf, n = "", 0
            if len(rows) == 3:
                break
    if len(rows) < 3:
        sys.exit("could not find the 3 header rows (hospital header, hospital values, column header)")
    h1, h2, h3 = rows
    skip = lines_per_row[0] + lines_per_row[1]   # lines before the column header
    return h1, h2, [c.strip() for c in h3], skip


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ccn", required=True)
    ap.add_argument("--period", required=True, help="download snapshot, e.g. 2026-10")
    ap.add_argument("--raw", required=True, help="raw folder of this hospital/period")
    ap.add_argument("--page", default="", help="hospital price page URL")
    ap.add_argument("--data", default="data", help="data root (default: data)")
    ap.add_argument("--effective-end", default="9999-12-31")
    a = ap.parse_args()

    raw = Path(a.raw)
    csvs = sorted(raw.glob("*standardcharges*.csv"))
    if len(csvs) != 1:
        sys.exit(f"expected exactly 1 *standardcharges*.csv in {raw}, found {len(csvs)}")
    src = csvs[0]
    zips = sorted(raw.glob("*.zip"))
    t0 = time.time()

    print(f"hashing {src.name} ...")
    sha = sha256_file(src)
    h1, h2, h3, skip = read_prefix(src)
    meta = dict(zip(h1, h2))
    hospital_name = meta.get("hospital_name", "")
    last_updated = meta.get("last_updated_on", "")
    version = meta.get("version", "")
    npis = meta.get("type_2_npi", "")
    ein = src.name.split("_")[0]
    try:
        m, d, y = last_updated.split("/")
        eff_start = date(int(y), int(m), int(d)).isoformat()
    except Exception:
        eff_start = f"{a.period}-01"

    unknown = [c for c in h3 if c not in COLMAP]
    if unknown:
        sys.exit(f"unmapped columns in {src.name}: {unknown}\nAdd them to COLMAP.")

    out_dir = Path(a.data) / "ref" / TABLE / f"ccn={a.ccn}" / f"period={a.period}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "part-000.parquet"
    tmp = out_dir / "part-000.parquet.tmp"
    man_dir = Path(a.data) / "ref" / "_manifest" / TABLE
    man_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute("SET preserve_insertion_order=false")
    sel = []
    for cms, ours in COLMAP.items():
        if cms not in h3:
            sel.append(f"NULL::{'DOUBLE' if ours in MONEY else 'INTEGER' if ours in INTS else 'VARCHAR'} AS {ours}")
            continue
        col = f'"{cms}"'
        if ours in MONEY:
            sel.append(f"TRY_CAST(NULLIF(REPLACE(REPLACE(TRIM({col}),'$',''),',',''),'') AS DOUBLE) AS {ours}")
        elif ours in INTS:
            sel.append(f"TRY_CAST(NULLIF(TRIM({col}),'') AS INTEGER) AS {ours}")
        else:
            sel.append(f"NULLIF(TRIM({col}),'') AS {ours}")
    select_sql = ",\n  ".join(sel)

    q_tpl = f"""
    COPY (
      WITH r AS (
        SELECT {select_sql}
        FROM read_csv('{src.as_posix()}', skip={skip}, header=true, all_varchar=true,
                      quote='"', escape='"', delim=',', strict_mode=false, ignore_errors=false,
                      encoding='__ENC__')
      )
      SELECT
        '{a.ccn}' AS ccn,
        '{hospital_name.replace("'", "''")}' AS hospital_name,
        '{ein}' AS ein,
        '{npis}' AS type2_npis,
        '{version}' AS mrf_version,
        DATE '{eff_start}' AS last_updated_on,
        r.*,
        -- derived join keys
        COALESCE(
          CASE WHEN upper(code_1_type) IN ('HCPCS','CPT') THEN code_1 END,
          CASE WHEN upper(code_2_type) IN ('HCPCS','CPT') THEN code_2 END,
          CASE WHEN upper(code_3_type) IN ('HCPCS','CPT') THEN code_3 END,
          CASE WHEN upper(code_4_type) IN ('HCPCS','CPT') THEN code_4 END) AS hcpcs,
        COALESCE(
          CASE WHEN upper(code_1_type)='MS-DRG' THEN code_1 END,
          CASE WHEN upper(code_2_type)='MS-DRG' THEN code_2 END,
          CASE WHEN upper(code_3_type)='MS-DRG' THEN code_3 END,
          CASE WHEN upper(code_4_type)='MS-DRG' THEN code_4 END) AS ms_drg,
        COALESCE(
          CASE WHEN upper(code_1_type)='APR-DRG' THEN code_1 END,
          CASE WHEN upper(code_2_type)='APR-DRG' THEN code_2 END,
          CASE WHEN upper(code_3_type)='APR-DRG' THEN code_3 END,
          CASE WHEN upper(code_4_type)='APR-DRG' THEN code_4 END) AS apr_drg,
        COALESCE(
          CASE WHEN upper(code_1_type)='RC' THEN code_1 END,
          CASE WHEN upper(code_2_type)='RC' THEN code_2 END,
          CASE WHEN upper(code_3_type)='RC' THEN code_3 END,
          CASE WHEN upper(code_4_type)='RC' THEN code_4 END) AS rc,
        COALESCE(
          CASE WHEN upper(code_1_type)='NDC' THEN code_1 END,
          CASE WHEN upper(code_2_type)='NDC' THEN code_2 END,
          CASE WHEN upper(code_3_type)='NDC' THEN code_3 END,
          CASE WHEN upper(code_4_type)='NDC' THEN code_4 END) AS ndc,
        COALESCE(
          CASE WHEN upper(code_1_type) IN ('CDM','LOCAL') THEN code_1 END,
          CASE WHEN upper(code_2_type) IN ('CDM','LOCAL') THEN code_2 END,
          CASE WHEN upper(code_3_type) IN ('CDM','LOCAL') THEN code_3 END,
          CASE WHEN upper(code_4_type) IN ('CDM','LOCAL') THEN code_4 END) AS cdm,
        -- lineage
        DATE '{eff_start}' AS effective_start,
        DATE '{a.effective_end}' AS effective_end,
        '{src.name}' AS source_file,
        '{sha}' AS source_sha256,
        '{a.period}' AS period
      FROM r
    ) TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)
    """
    print(f"loading {src.name} (skip {skip} header lines) ...")
    encoding_used, warnings = "utf-8", []
    try:
        con.execute(q_tpl.replace("__ENC__", "utf-8"))
    except duckdb.InvalidInputException as e:
        if "not utf-8" not in str(e) and "Invalid unicode" not in str(e):
            raise
        # A few descriptions hold stray Windows-1252 bytes. Make a UTF-8-clean copy in
        # data\work (the raw file is never touched), load that, and record it.
        work = Path(a.data) / "work"; work.mkdir(parents=True, exist_ok=True)
        clean = work / (src.stem + ".utf8.csv")
        print(f"  not valid UTF-8, writing cleaned copy {clean} ...")
        bad = 0
        with open(src, "rb") as fi, open(clean, "w", encoding="utf-8", newline="") as fo:
            for line in fi:
                try:
                    fo.write(line.decode("utf-8"))
                except UnicodeDecodeError:
                    bad += 1
                    fo.write(line.decode("cp1252", errors="replace"))
        warnings.append(f"{bad} lines were not valid UTF-8; decoded as cp1252 into {clean.name}. "
                        "Only description text is affected; codes and prices are unchanged.")
        encoding_used = "utf-8 (cleaned copy)"
        con.execute(q_tpl.replace("__ENC__", "utf-8").replace(src.as_posix(), clean.as_posix()))
    if out.exists():
        out.unlink()
    tmp.rename(out)

    rows = con.execute(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()[0]
    payers = con.execute(f"SELECT count(DISTINCT payer_name) FROM '{out.as_posix()}'").fetchone()[0]
    manifest = {
        "table": TABLE, "ccn": a.ccn, "period": a.period,
        "hospital_name": hospital_name, "ein": ein, "type2_npis": npis,
        "mrf_version": version, "last_updated_on": eff_start,
        "effective_start": eff_start, "effective_end": a.effective_end,
        "page_url": a.page,
        "raw_folder": str(raw),
        "sources": [{"file": src.name, "sha256": sha, "bytes": src.stat().st_size}]
                   + [{"file": z.name, "sha256": sha256_file(z), "bytes": z.stat().st_size} for z in zips],
        "columns_in_file": h3, "header_lines_skipped": skip,
        "encoding": encoding_used, "warnings": warnings,
        "read_path": str(clean) if encoding_used != "utf-8" else str(src),
        "rows": rows, "distinct_payers": payers,
        "output": str(out), "output_bytes": out.stat().st_size,
        "loaded_at": datetime.now().isoformat(timespec="seconds"),
        "seconds": round(time.time() - t0, 1),
    }
    mp = man_dir / f"{a.ccn}_{a.period}.json"
    mp.write_text(json.dumps(manifest, indent=2))
    print(f"OK  rows={rows:,}  payers={payers}  parquet={out}  ({out.stat().st_size/1e6:.1f} MB)")
    print(f"manifest: {mp}")


if __name__ == "__main__":
    main()
