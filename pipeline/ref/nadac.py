"""Table 21 — ref_nadac: National Average Drug Acquisition Cost per NDC
(Medicaid survey of pharmacy invoice prices). The yearly files repeat each
price every week ("As of Date"); we keep one row per NDC x price start date.
effective_start = the NADAC "Effective Date"; effective_end = the day before
the next price of the same NDC (9999-12-31 for the latest price)."""
from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from ..common.config import OPEN_END
from ..common.lineage import add_lineage
from ..common.tabular import find_col_exact, read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["ndc", "effective_start"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["nadac"])
    df = read_csv_fast(mem)
    c = lambda n: find_col_exact(df, n)
    d = lambda n: pl.col(c(n)).str.strptime(pl.Date, "%m/%d/%Y", strict=False)
    df = df.select(
        pl.col(c("NDC")).str.strip_chars().str.zfill(11).alias("ndc"),
        pl.col(c("NDC Description")).str.strip_chars().alias("ndc_description"),
        pl.col(c("NADAC Per Unit")).cast(pl.Float64, strict=False).alias("nadac_per_unit"),
        d("Effective Date").alias("price_effective_date"),
        pl.col(c("Pricing Unit")).str.strip_chars().alias("pricing_unit"),
        pl.col(c("Pharmacy Type Indicator")).str.strip_chars().alias("pharmacy_type"),
        (pl.col(c("OTC")).str.strip_chars() == "Y").alias("otc"),
        pl.col(c("Explanation Code")).str.strip_chars().alias("explanation_code"),
        pl.col(c("Classification for Rate Setting")).str.strip_chars().alias("classification"),
        pl.col(c("Corresponding Generic Drug NADAC Per Unit")).cast(pl.Float64, strict=False).alias("generic_nadac_per_unit"),
        d("As of Date").alias("as_of_date"),
    ).filter(pl.col("price_effective_date").is_not_null())
    # each weekly file repeats the price: keep the latest copy now, to save memory
    df = df.sort("as_of_date", descending=True).unique(subset=["ndc", "price_effective_date"], keep="first")
    df = add_lineage(df, mem, period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])


def finalize(frames: list[pl.DataFrame], ctx: Context) -> pl.DataFrame:
    """One row per NDC x price start, latest weekly copy wins; then chain dates."""
    df = (pl.concat(frames, how="diagonal_relaxed")
          .sort("as_of_date", descending=True)
          .unique(subset=["ndc", "price_effective_date"], keep="first")
          .sort(["ndc", "price_effective_date"]))
    nxt = pl.col("price_effective_date").shift(-1).over("ndc")
    return df.with_columns(
        pl.col("price_effective_date").alias("effective_start"),
        pl.when(nxt.is_not_null()).then(nxt - pl.duration(days=1))
          .otherwise(pl.lit(OPEN_END, dtype=pl.Date)).alias("effective_end"))
