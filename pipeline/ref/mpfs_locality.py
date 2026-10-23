"""Table 2 helper — ref_mpfs_locality: which counties make up each locality.

The LOCCO file lists the state only on the first row of each state, and has
blank spacer rows. We forward-fill the state.
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["state_name", "carrier", "locality"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["locco"])
    df = read_cms_csv(m, header_startswith="Medicare Adminstrative Contractor",
                      key_regex=r"^\d{5}$")
    c = df.columns
    df = df.select(
        pl.col(c[0]).str.strip_chars().alias("carrier"),
        pl.col(c[1]).str.strip_chars().str.zfill(2).alias("locality"),
        pl.col(c[2]).str.strip_chars().replace("", None).forward_fill().alias("state_name"),
        pl.col(c[3]).str.strip_chars().alias("fee_schedule_area"),
        pl.col(c[4]).str.strip_chars().alias("counties"),
    )
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
