"""Table 20 helper — ref_chow_npi: all NPIs of each enrollment in the CHOW
file (Hospital_CHOW_NPIs). The SNF file in the same zip is not used."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import find_col_exact, read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["enrollment_id", "npi"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["npis"])
    df = read_csv_fast(mem)
    df = df.select(pl.col(find_col_exact(df, "ENROLLMENT ID")).str.strip_chars().alias("enrollment_id"),
                   pl.col(find_col_exact(df, "NPI")).str.strip_chars().cast(pl.Int64, strict=False).alias("npi")
                   ).unique(maintain_order=True)
    df = add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
