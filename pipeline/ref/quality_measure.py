"""Table 19 — ref_quality_measure: Care Compare hospital measures in one long
table: complications & deaths, unplanned visits, healthcare-associated
infections, timely & effective care. One row per hospital x measure.
`score` is text in the file ("Not Available", numbers); `score_value` is the
number when there is one."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import find_col_exact, read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["ccn", "measure_group", "measure_id"]
GROUPS = ("complications", "unplanned", "infections", "timely")
NA = ["", "Not Available", "Not Applicable", "N/A"]


def _read(mem, group: str) -> pl.DataFrame:
    df = read_csv_fast(mem)
    c = lambda *n: find_col_exact(df, *n)

    def t(*names):
        col = c(*names)
        return pl.col(col).str.strip_chars() if col else pl.lit(None, dtype=pl.Utf8)

    def d(*names):
        return t(*names).str.strptime(pl.Date, "%m/%d/%Y", strict=False)

    score = t("Score")
    return df.select(
        t("Facility ID").str.zfill(6).alias("ccn"),
        pl.lit(group).alias("measure_group"),
        t("Measure ID").alias("measure_id"),
        t("Measure Name").alias("measure_name"),
        t("Condition").alias("condition"),
        t("Compared to National").alias("compared_to_national"),
        score.alias("score"),
        score.str.replace_all(",", "").cast(pl.Float64, strict=False).alias("score_value"),
        t("Denominator", "Sample", "Number of Patients").str.replace_all(",", "").cast(pl.Float64, strict=False).alias("denominator"),
        t("Lower Estimate").cast(pl.Float64, strict=False).alias("lower_estimate"),
        t("Higher Estimate").cast(pl.Float64, strict=False).alias("higher_estimate"),
        t("Footnote").replace("", None).alias("footnote"),
        d("Start Date").alias("measure_start"),
        d("End Date").alias("measure_end"),
    )


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    frames, members = [], []
    for g in GROUPS:
        pat = rel["members"].get(g)
        if not pat:
            continue
        mem = raw.member(pat)
        frames.append(add_lineage(_read(mem, g), mem, effective_start=as_date(rel["effective_start"]),
                                  effective_end=as_date(rel["effective_end"]), period=str(rel["period"])))
        members.append(mem)
    return ReleaseOutput(df=pl.concat(frames, how="diagonal_relaxed"), members=members, raw_files=[raw])
