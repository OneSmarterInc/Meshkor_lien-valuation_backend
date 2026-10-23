"""Table 4a — ref_ipps_drg: MS-DRG relative weights (IPPS final rule Table 5).

The CMS zip holds the final-rule (FR) and correction-notice (CN) versions;
config picks the CN file, which replaces the FR. Weights use the "10% cap
applied" column (the one used for payment); the uncapped weight is kept too.
MS-DRG titles are public (not AMA-licensed), so they are stored.
Fiscal year runs Oct 1 – Sep 30 (Spec §6: FY2027 began Oct 1, 2026).
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, num
from ..common.tabular import find_col, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["ms_drg", "effective_start"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["table5"])
    delim = "\t" if m.name.lower().endswith(".txt") else ","
    df = read_cms_csv(m, header_startswith="MS-DRG", encoding="latin-1", delimiter=delim,
                      key_regex=r"^\d{3}$")
    out = df.select(
        pl.col(df.columns[0]).str.strip_chars().alias("ms_drg"),
        pl.col(find_col(df, "MS-DRG TITLE")).str.strip_chars().alias("ms_drg_title"),
        pl.col(find_col(df, "MDC")).str.strip_chars().replace("", None).alias("mdc"),
        pl.col(find_col(df, "TYPE")).str.strip_chars().alias("drg_type"),
        (pl.col(find_col(df, "POST-ACUTE")).str.strip_chars() == "Yes").alias("post_acute_transfer"),
        (pl.col(find_col(df, "SPECIAL PAY")).str.strip_chars() == "Yes").alias("special_pay"),
        num(find_col(df, "CAP APPLIED")).alias("relative_weight"),
        num(find_col(df, "BEFORE CAP")).alias("relative_weight_before_cap"),
        num(find_col(df, "GEOMETRIC")).alias("gmlos"),
        num(find_col(df, "ARITHMETIC")).alias("amlos"),
    )
    if out.height < 700:
        ctx.warn(f"only {out.height} MS-DRGs read from {m.name}; expected about 770")
    out = add_lineage(out, m, effective_start=as_date(rel["effective_start"]),
                      effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=out.with_columns(pl.lit(str(rel["period"])).alias("fiscal_year")),
                         members=[m], raw_files=[raw])
