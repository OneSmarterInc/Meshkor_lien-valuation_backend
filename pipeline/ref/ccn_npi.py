"""Table 8 — ref_ccn_npi: hospital CCN to NPI pairs (Spec §6).

Sources, in order of trust:
  1. Hospital Enrollments (data.cms.gov, monthly): one row per enrollment,
     with CCN and the main NPI.
  2. Hospital Additional NPIs (same release): more NPIs per enrollment.
  3. NPPES "Other Provider Identifier" type 05/06 (Medicare OSCAR/CCN), read
     from the ref_provider output. CMS stopped adding these in 2018, so they
     only fill gaps (match_source = 'nppes_other_id').
  4. NPPES hospital NPIs (taxonomy 28*) that are still unmatched, joined to an
     enrollment on the same 5-digit zip and the same street address
     ('address_zip'), the same legal / DBA name ('name_zip'), or the same
     name in the same city ('name_city', for a wrong zip). A hospital
     often has extra NPIs (departments, old NPIs) at its main address that it
     never listed on its Medicare enrollment.

One hospital can have several NPIs, and an NPI can show up under more than one
CCN (a unit with its own CCN). All pairs are kept.
"""
from __future__ import annotations

import io
import json

import polars as pl

from ..common.config import OPEN_END
from ..common.lineage import add_lineage, as_date
from ..runner import Context, ReleaseOutput

SORT_BY = ["ccn", "npi", "match_source"]

KEEP = {
    "ENROLLMENT ID": "enrollment_id", "ENROLLMENT STATE": "enrollment_state",
    "PROVIDER TYPE CODE": "provider_type_code", "PROVIDER TYPE TEXT": "provider_type_text",
    "NPI": "npi", "MULTIPLE NPI FLAG": "multiple_npi_flag", "CCN": "ccn",
    "ORGANIZATION NAME": "organization_name", "DOING BUSINESS AS NAME": "dba_name",
    "PROPRIETARY NONPROFIT": "proprietary_nonprofit", "ADDRESS LINE 1": "address_1", "CITY": "city", "STATE": "state",
    "ZIP CODE": "zip_code", "PRACTICE LOCATION TYPE": "practice_location_type",
    "SUBGROUP - ACUTE CARE": "subgroup_acute_care", "SUBGROUP - GENERAL": "subgroup_general",
    "SUBGROUP - CHILDRENS": "subgroup_childrens", "SUBGROUP - LONG-TERM": "subgroup_long_term",
    "SUBGROUP - PSYCHIATRIC": "subgroup_psychiatric", "SUBGROUP - REHABILITATION": "subgroup_rehabilitation",
    "SUBGROUP - SHORT-TERM": "subgroup_short_term", "CAH OR HOSPITAL CCN": "cah_or_hospital_ccn",
}
FLAGS = [v for k, v in KEEP.items() if k.startswith("SUBGROUP")]


def _config_file(name: str):
    import os
    from pathlib import Path
    from ..common.config import PROJECT_ROOT
    return Path(os.environ.get("MESHKOR_CONFIG_DIR", PROJECT_ROOT / "config")) / name


def add_manual_pairs(df: pl.DataFrame, path, start, period: str, ctx: Context) -> pl.DataFrame:
    """Reviewed pairs from config/ccn_npi_manual.csv (columns npi, ccn, approved, note).
    Only rows with approved = Y are used (match_source = 'manual'). Fill it from the
    suggestions file that verify writes (data/reports/ccn_npi_ohio_suggestions.csv)."""
    if not path.exists():
        return df
    import hashlib
    raw = path.read_bytes()
    m = pl.read_csv(raw, infer_schema=False)
    m = m.rename({c: c.strip().lower() for c in m.columns})
    if not {"npi", "ccn"} <= set(m.columns):
        ctx.warn(f"{path.name}: needs columns npi, ccn (and approved = Y); ignored")
        return df
    if "approved" in m.columns:
        m = m.filter(pl.col("approved").str.strip_chars().str.to_uppercase() == "Y")
    m = m.select(pl.col("npi").str.strip_chars().cast(pl.Int64, strict=False).alias("npi"),
                 _ccn(pl.col("ccn")).alias("ccn")).drop_nulls()
    if not m.height:
        return df
    info_cols = [c for c in ("ccn", "organization_name", "dba_name", "state", "provider_type_text",
                             "enrollment_state", "subgroup_acute_care") if c in df.columns]
    info = df.filter(pl.col("match_source") == "enrollment").select(info_cols).unique("ccn", keep="first")
    unknown = m.join(info, on="ccn", how="anti").height
    if unknown:
        ctx.warn(f"{path.name}: {unknown} approved rows have a CCN that is not in Hospital Enrollments (kept)")
    m = m.join(info, on="ccn", how="left").with_columns(
        pl.lit("manual").alias("match_source"),
        pl.lit(f"config/{path.name}").alias("source_file"),
        pl.lit(hashlib.sha256(raw).hexdigest()).alias("source_sha256"),
        pl.lit(start, dtype=pl.Date).alias("effective_start"),
        pl.lit(OPEN_END, dtype=pl.Date).alias("effective_end"),
        pl.lit(period).alias("period"))
    ctx.warn(f"{m.height:,} reviewed pairs added from config/{path.name}")
    return pl.concat([df, m], how="diagonal_relaxed")


def _read(member) -> pl.DataFrame:
    df = pl.read_csv(io.BytesIO(member.read_bytes()), infer_schema=False, encoding="utf8-lossy")
    return df.rename({c: c.strip().upper() for c in df.columns})


def _ccn(e: pl.Expr) -> pl.Expr:
    e = e.str.strip_chars().str.to_uppercase().replace("", None)
    # Excel can drop the leading zero of a 6-character CCN (050001 -> 50001).
    return pl.when(e.str.contains(r"^\d{5}$")).then(e.str.zfill(6)).otherwise(e)


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m_main = raw.member(rel["members"]["enrollments"])
    m_add = raw.members(rel["members"].get("additional_npis", "__none__"))
    start = as_date(rel["snapshot_date"])

    e = _read(m_main)
    missing = [k for k in ("ENROLLMENT ID", "NPI", "CCN") if k not in e.columns]
    if missing:
        raise ValueError(f"{m_main.lineage_name}: columns not found: {missing}")
    e = e.select([pl.col(k).alias(v) for k, v in KEEP.items() if k in e.columns])
    e = e.with_columns(
        _ccn(pl.col("ccn")).alias("ccn"),
        pl.col("npi").str.strip_chars().cast(pl.Int64, strict=False).alias("npi"),
        pl.col("zip_code").str.strip_chars().str.slice(0, 5).str.zfill(5).alias("zip5"),
        *[(pl.col(f).str.strip_chars() == "Y").alias(f) for f in FLAGS if f in e.columns],
    ).drop("zip_code")
    bad = e.filter(pl.col("ccn").is_null() | pl.col("npi").is_null()).height
    if bad:
        ctx.warn(f"{bad} enrollment rows without a CCN or NPI (kept out)")
    e = e.filter(pl.col("ccn").is_not_null() & pl.col("npi").is_not_null())
    parts = [add_lineage(e.with_columns(pl.lit("enrollment").alias("match_source")), m_main,
                         effective_start=start, effective_end=OPEN_END, period=str(rel["period"]))]
    members = [m_main]

    if m_add:
        a = _read(m_add[0])
        a = a.select(pl.col("ENROLLMENT ID").alias("enrollment_id"),
                     pl.col("NPI").str.strip_chars().cast(pl.Int64, strict=False).alias("npi"))
        info = e.drop("npi")
        a = a.join(info, on="enrollment_id", how="inner")
        lost = _read(m_add[0]).height - a.height
        if lost:
            ctx.warn(f"{lost} additional-NPI rows have an enrollment ID that is not in the main file "
                     "(use both files from the same month)")
        parts.append(add_lineage(a.with_columns(pl.lit("enrollment_additional").alias("match_source")),
                                 m_add[0], effective_start=start, effective_end=OPEN_END,
                                 period=str(rel["period"])))
        members.append(m_add[0])
    else:
        ctx.warn("Hospital_Additional_NPIs file not found; only the main NPI per enrollment is loaded")

    df = pl.concat(parts, how="diagonal_relaxed")
    if rel.get("nppes_fallback", True):
        df = _add_nppes(df, ctx, start, str(rel["period"]))
    df = add_manual_pairs(df, _config_file(rel.get("manual_pairs", "ccn_npi_manual.csv")), start,
                          str(rel["period"]), ctx)
    df = df.unique(subset=["ccn", "npi", "match_source", "enrollment_id"], keep="first", maintain_order=True)
    return ReleaseOutput(df=df, members=members, raw_files=[raw])


def _add_nppes(df: pl.DataFrame, ctx: Context, start, period: str) -> pl.DataFrame:
    src = ctx.paths.ref / "ref_provider"
    if not src.exists():
        ctx.warn("ref_provider not built yet; NPPES fallback pairs skipped (run load_ref ref_provider first)")
        return df
    man = ctx.paths.manifests / "ref_provider.json"
    sha = "unknown"
    if man.exists():
        srcs = json.loads(man.read_text(encoding="utf-8")).get("sources") or [{}]
        sha = srcs[0].get("sha256", "unknown")
    n = (pl.scan_parquet(str(src / "**" / "*.parquet"), hive_partitioning=True)
         .filter(pl.col("entity_type") == 2)
         .select("npi", "provider_name", "practice_state", "zip5", "medicare_oscar_ids")
         .explode("medicare_oscar_ids")
         .filter(pl.col("medicare_oscar_ids").is_not_null())
         .with_columns(_ccn(pl.col("medicare_oscar_ids")).alias("ccn"))
         .filter(pl.col("ccn").str.contains(r"^[0-9]{2}[0-9A-Z][0-9]{3}$"))
         .collect())
    have = df.select("ccn", "npi").unique()
    n = n.join(have, on=["ccn", "npi"], how="anti")
    n = n.select(
        "ccn", "npi",
        pl.col("provider_name").alias("organization_name"),
        pl.col("practice_state").alias("state"), "zip5",
        pl.lit("nppes_other_id").alias("match_source"),
        pl.lit("ref_provider (NPPES other provider identifiers)").alias("source_file"),
        pl.lit(sha).alias("source_sha256"),
        pl.lit(start, dtype=pl.Date).alias("effective_start"),
        pl.lit(OPEN_END, dtype=pl.Date).alias("effective_end"),
        pl.lit(period).alias("period"),
    )
    ctx.warn(f"{n.height:,} extra CCN–NPI pairs from NPPES other identifiers (not in Hospital Enrollments)")
    df = pl.concat([df, n], how="diagonal_relaxed")
    return _add_address_matches(df, src, sha, start, period, ctx)


_ADDR = [(r"\bSTREET\b", "ST"), (r"\bAVENUE\b", "AVE"), (r"\bROAD\b", "RD"), (r"\bDRIVE\b", "DR"),
         (r"\bBOULEVARD\b", "BLVD"), (r"\bPARKWAY\b", "PKWY"), (r"\bHIGHWAY\b", "HWY"),
         (r"\bLANE\b", "LN"), (r"\bCOURT\b", "CT"), (r"\bPLACE\b", "PL"), (r"\bNORTH\b", "N"),
         (r"\bSOUTH\b", "S"), (r"\bEAST\b", "E"), (r"\bWEST\b", "W"),
         (r"\b(SUITE|STE|UNIT|FLOOR|FL|BLDG|BUILDING|ROOM|RM)\b.*$", "")]
_NAME_DROP = r"\b(THE|INC|INCORPORATED|LLC|L L C|CORP|CORPORATION|CO|COMPANY|LTD|LP|PC)\b"


def _norm_addr(e: pl.Expr) -> pl.Expr:
    e = e.str.to_uppercase().str.replace_all(r"[^A-Z0-9 ]", " ")
    for a, b in _ADDR:
        e = e.str.replace_all(a, b)
    e = e.str.replace_all(r"\s+", " ").str.strip_chars()
    return pl.when(e.str.len_chars() >= 4).then(e).otherwise(None)


def _norm_name(e: pl.Expr) -> pl.Expr:
    e = (e.str.to_uppercase().str.replace_all("&", " AND ").str.replace_all(r"[^A-Z0-9 ]", " ")
         .str.replace_all(_NAME_DROP, " ").str.replace_all(r"\s+", " ").str.strip_chars())
    return pl.when(e.str.len_chars() >= 4).then(e).otherwise(None)


def _add_address_matches(df: pl.DataFrame, src, sha: str, start, period: str, ctx: Context) -> pl.DataFrame:
    if "address_1" not in df.columns:
        return df
    hosp = (pl.scan_parquet(str(src / "**" / "*.parquet"), hive_partitioning=True)
            .filter((pl.col("entity_type") == 2) & pl.col("primary_taxonomy").str.starts_with("28")
                    & ~pl.col("is_deactivated"))
            .select("npi", "provider_name", "practice_address_1", "practice_city", "zip5", "practice_state")
            .collect())
    hosp = hosp.join(df.select("npi").unique(), on="npi", how="anti").with_columns(
        _norm_addr(pl.col("practice_address_1")).alias("k_addr"),
        _norm_name(pl.col("provider_name")).alias("k_name"),
        pl.col("practice_city").str.to_uppercase().str.replace_all(r"[^A-Z ]", "").str.strip_chars().alias("k_city"))
    enr = df.filter(pl.col("match_source") == "enrollment")
    keys = ["ccn", "enrollment_id", "organization_name", "dba_name", "provider_type_text",
            "enrollment_state", "subgroup_acute_care"]
    keys = [k for k in keys if k in enr.columns]
    ea = enr.select(*keys, "zip5", _norm_addr(pl.col("address_1")).alias("k_addr"))
    en = pl.concat([enr.select(*keys, "zip5", _norm_name(pl.col(c)).alias("k_name"))
                    for c in ("organization_name", "dba_name") if c in enr.columns])
    by_addr = hosp.drop_nulls("k_addr").join(ea.drop_nulls("k_addr"), on=["zip5", "k_addr"], how="inner") \
        .with_columns(pl.lit("address_zip").alias("match_source"))
    by_name = hosp.drop_nulls("k_name").join(en.drop_nulls("k_name"), on=["zip5", "k_name"], how="inner") \
        .with_columns(pl.lit("name_zip").alias("match_source"))
    # Same exact name in the same city and state (catches a mistyped or changed zip)
    ec = pl.concat([enr.select(*keys, pl.col("state").alias("practice_state"),
                               pl.col("city").str.to_uppercase().str.replace_all(r"[^A-Z ]", "").str.strip_chars()
                               .alias("k_city"), _norm_name(pl.col(c)).alias("k_name"))
                    for c in ("organization_name", "dba_name") if c in enr.columns])
    by_city = hosp.drop_nulls("k_name").join(ec.drop_nulls("k_name"), on=["practice_state", "k_city", "k_name"],
                                             how="inner").with_columns(pl.lit("name_city").alias("match_source"))
    m = pl.concat([by_addr.select(*keys, "npi", "zip5", "practice_state", "match_source"),
                   by_name.select(*keys, "npi", "zip5", "practice_state", "match_source"),
                   by_city.select(*keys, "npi", "zip5", "practice_state", "match_source")])
    m = m.unique(subset=["ccn", "npi"], keep="first", maintain_order=True).rename({"practice_state": "state"})
    m = m.with_columns(
        pl.lit("ref_provider (NPPES) x Hospital Enrollments, same zip + address or name").alias("source_file"),
        pl.lit(sha).alias("source_sha256"),
        pl.lit(start, dtype=pl.Date).alias("effective_start"),
        pl.lit(OPEN_END, dtype=pl.Date).alias("effective_end"),
        pl.lit(period).alias("period"))
    multi = m.group_by("npi").agg(pl.col("ccn").n_unique().alias("n")).filter(pl.col("n") > 1).height
    ctx.warn(f"{m.height:,} extra pairs from NPPES hospital NPIs matched on zip + address/name or city + name "
             f"({multi:,} NPIs match 2+ CCNs at one address; all kept)")
    return pl.concat([df, m], how="diagonal_relaxed")
