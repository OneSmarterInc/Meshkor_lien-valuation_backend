"""Table 19 — ref_quality_hospital: Care Compare "Hospital General Information",
one row per hospital (CCN): type, ownership, emergency services and the overall
star rating (1–5; null = "Not Available")."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import find_col_exact, read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["ccn"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["general"])
    df = read_csv_fast(mem)
    c = lambda *n: find_col_exact(df, *n)
    t = lambda name: pl.col(c(name)).str.strip_chars().replace("", None)
    df = df.select(
        t("Facility ID").str.zfill(6).alias("ccn"),
        t("Facility Name").alias("hospital_name"),
        t("Address").alias("address"), t("City/Town").alias("city"), t("State").alias("state"),
        t("ZIP Code").str.zfill(5).alias("zip5"), t("County/Parish").alias("county"),
        t("Hospital Type").alias("hospital_type"), t("Hospital Ownership").alias("hospital_ownership"),
        (t("Emergency Services") == "Yes").alias("emergency_services"),
        (t("Meets criteria for birthing friendly designation") == "Y").alias("birthing_friendly"),
        t("Hospital overall rating").cast(pl.Int8, strict=False).alias("overall_star_rating"),
        t("Hospital overall rating footnote").alias("overall_rating_footnote"),
    )
    df = add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
