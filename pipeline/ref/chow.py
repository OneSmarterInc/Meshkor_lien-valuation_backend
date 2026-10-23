"""Table 20 — ref_chow: hospital changes of ownership (buyer, seller, type,
date). One row per CHOW event. Columns follow the CMS file in snake_case
("NPI - BUYER" -> npi_buyer, "CCN - SELLER" -> ccn_seller)."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import read_csv_fast
from ..runner import Context, ReleaseOutput
from .ownership import tidy

SORT_BY = ["chow_effective_date", "enrollment_id_buyer"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["chow"])
    df = tidy(read_csv_fast(mem), {"effective_date": "chow_effective_date"})
    df = df.with_columns(
        pl.col("chow_effective_date").str.strptime(pl.Date, "%m/%d/%Y", strict=False),
        pl.col("npi_buyer").cast(pl.Int64, strict=False), pl.col("npi_seller").cast(pl.Int64, strict=False),
        pl.col("ccn_buyer").str.zfill(6), pl.col("ccn_seller").str.zfill(6))
    df = add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
