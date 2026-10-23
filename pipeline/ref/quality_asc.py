"""Table 19 — ref_quality_asc: Care Compare "ASC Facility" quality rates,
unpivoted to one row per ASC x measure (ASC-1 … ASC-20). The file is wide:
one "Rate*" (or "RSHV Rate") and one "Footnote" column per measure."""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import find_col_exact, read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["facility_id", "measure_id"]
RATE_RX = re.compile(r"^(ASC-\d+)\s+(Rate\*?|RSHV Rate)$", re.I)


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["asc"])
    df = read_csv_fast(mem)
    c = lambda *n: find_col_exact(df, *n)
    ids = {"facility_id": c("Facility ID"), "npi": c("NPI"), "facility_name": c("Facility Name"),
           "city": c("City/Town"), "state": c("State"), "zip5": c("ZIP Code"), "data_year": c("Year")}
    parts = []
    for col in df.columns:
        m = RATE_RX.match(col.strip())
        if not m:
            continue
        mid = m.group(1).upper()
        foot = next((x for x in df.columns if x.strip().upper() == f"{mid} FOOTNOTE"), None)
        perf = next((x for x in df.columns if x.strip().upper() == f"{mid} PERFORMANCE CATEGORY"), None)
        parts.append(df.select(
            *[pl.col(v).str.strip_chars().alias(k) for k, v in ids.items() if v],
            pl.lit(mid).alias("measure_id"),
            pl.col(col).str.strip_chars().alias("score"),
            pl.col(col).str.strip_chars().cast(pl.Float64, strict=False).alias("score_value"),
            (pl.col(perf).str.strip_chars() if perf else pl.lit(None, dtype=pl.Utf8)).alias("performance_category"),
            (pl.col(foot).str.strip_chars().replace("", None) if foot else pl.lit(None, dtype=pl.Utf8)).alias("footnote"),
        ))
    if not parts:
        raise ValueError(f"{mem.lineage_name}: no 'ASC-n Rate' columns in {df.columns[:12]} …")
    out = pl.concat(parts, how="diagonal_relaxed").with_columns(
        pl.col("npi").cast(pl.Int64, strict=False), pl.col("zip5").str.zfill(5),
        pl.col("data_year").cast(pl.Int32, strict=False))
    out = add_lineage(out, mem, effective_start=as_date(rel["effective_start"]),
                      effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=out, members=[mem], raw_files=[raw])
