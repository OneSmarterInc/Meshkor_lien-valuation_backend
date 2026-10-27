"""Guide 2.1: the hospital list.

Ohio Type 2 NPIs with a hospital taxonomy (config/hospital_taxonomies.yaml), joined to
ref_ccn_npi for the CCN, minus the NPIs in config/ccn_npi_reclass.csv (closed, federal,
not acute), plus the website from config/hospital_sites.csv.

Output: data/ref/hpt_hospitals.parquet and data/reports/hpt_hospitals.csv, one row per CCN.
Run after ref_provider and ref_ccn_npi are loaded:  python -m pipeline.hpt.hospitals
"""
from __future__ import annotations

import argparse
import re
import csv
from pathlib import Path

import duckdb
import polars as pl

from ..common import config


def build(data_root: str | None = None) -> Path:
    paths = config.data_paths(data_root)
    tax = config.load_yaml("hospital_taxonomies.yaml")
    sites = pl.read_csv(config.PROJECT_ROOT / "config" / "hospital_sites.csv", infer_schema_length=0)
    con = duckdb.connect()
    prov = paths.ref / "ref_provider"
    prov_src = (f"read_parquet('{prov.as_posix()}/**/*.parquet', hive_partitioning=true, union_by_name=true)"
                if prov.is_dir() else f"read_parquet('{(paths.ref / 'ref_provider.parquet').as_posix()}')")
    ccn_src = f"read_parquet('{(paths.ref / 'ref_ccn_npi.parquet').as_posix()}')"
    reclass = config.PROJECT_ROOT / "config" / "ccn_npi_reclass.csv"
    codes = ", ".join(f"'{c}'" for c in tax["acute"])
    prefix = " OR ".join(f"c.ccn LIKE '{p}%'" for p in tax["ccn_prefix"])
    slot = ("list_has_any(p.all_taxonomies, [" + codes + "])" if tax.get("any_slot", True)
            else f"p.primary_taxonomy IN ({codes})")
    con.execute(f"""
        CREATE TABLE hosp AS
        WITH p AS (
          SELECT npi, provider_name, organization_name, practice_city, zip5, primary_taxonomy, all_taxonomies, is_deactivated
          FROM {prov_src} WHERE practice_state = '{tax['state']}' AND entity_type = 2
        ),
        r AS (SELECT CAST(npi AS BIGINT) AS npi, category FROM read_csv('{reclass.as_posix()}', header=true, all_varchar=true))
        SELECT c.ccn, p.npi, coalesce(c.organization_name, p.organization_name) AS hospital_name,
               c.dba_name, c.city, p.zip5, p.primary_taxonomy, c.match_source,
               bool_or(coalesce(c.subgroup_acute_care, false)) OVER (PARTITION BY c.ccn) AS any_acute_flag
        FROM {ccn_src} c
        JOIN p ON p.npi = c.npi
        LEFT JOIN r ON r.npi = c.npi
        WHERE ({prefix}) AND regexp_matches(c.ccn, '^[0-9]{{6}}$') AND {slot} AND r.npi IS NULL AND NOT coalesce(p.is_deactivated, false)
    """)
    # one row per CCN: the parent NPI = the one the enrollment file lists first (match_source = enrollment)
    df = con.sql("""
        SELECT ccn, arg_min(npi, CASE match_source WHEN 'enrollment' THEN 0 ELSE 1 END) AS npi,
               arg_min(hospital_name, CASE match_source WHEN 'enrollment' THEN 0 ELSE 1 END) AS hospital_name,
               any_value(dba_name) AS dba_name, any_value(city) AS city, any_value(zip5) AS zip5,
               count(*) AS npi_count, list_distinct(list(npi)) AS all_npis
        FROM hosp GROUP BY ccn ORDER BY ccn
    """).pl()
    df = df.join(sites.select("ccn", pl.col("system"), pl.col("website"), pl.col("hpt_txt_url"),
                              pl.col("source_page_url"), pl.col("verified"), pl.col("history")),
                 on="ccn", how="left")
    # systems listed without a CCN in hospital_sites.csv: match by name words
    unnamed = sites.filter(pl.col("ccn").is_null() | (pl.col("ccn") == ""))
    for row in unnamed.iter_rows(named=True):
        if not row.get("website"):
            continue
        # name_match: a regex (case-insensitive) in hospital_sites.csv; default = first word of the system name
        pat = (row.get("name_match") or "").strip() or r"\b" + re.escape(row["system"].split()[0]) + r"\b"
        names = pl.concat_str([pl.col("hospital_name").fill_null(""), pl.lit(" | "), pl.col("dba_name").fill_null("")])
        hit = names.str.contains("(?i)" + pat) & pl.col("website").is_null()
        df = df.with_columns(
            pl.when(hit).then(pl.lit(row["system"])).otherwise(pl.col("system")).alias("system"),
            pl.when(hit).then(pl.lit(row["website"])).otherwise(pl.col("website")).alias("website"))
    out = paths.ref / "hpt_hospitals.parquet"
    df.write_parquet(out, compression="zstd")
    rep = paths.root / "reports" / "hpt_hospitals.csv"
    rep.parent.mkdir(parents=True, exist_ok=True)
    df.with_columns(pl.col("all_npis").cast(pl.List(pl.Utf8)).list.join("|")).write_csv(rep)
    n_site = df.filter(pl.col("website").is_not_null()).height
    print(f"{df.height} hospitals (CCNs), {n_site} with a website -> {out}\n"
          f"fill the rest in config/hospital_sites.csv: {rep}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    build(a.data_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
