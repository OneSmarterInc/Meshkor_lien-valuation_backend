"""Table 12 helper — ref_dmepos_rural_zip: zip codes CMS treats as rural for DMEPOS
in a quarter (use the "(R)" fee in ref_dmepos for these zips)."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import find_col, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["zip5"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["rural_zip"])
    df = read_cms_csv(m, header_startswith="STATE", key_col=1, key_regex=r"^\d{5}$", encoding="latin-1")
    df = df.select(pl.col(df.columns[0]).str.strip_chars().alias("state"),
                   pl.col(find_col(df, "ZIP")).str.strip_chars().alias("zip5")).unique(maintain_order=True)
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
