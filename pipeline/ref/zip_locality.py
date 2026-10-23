"""Table 13 helper — ref_zip_locality: CMS ZIP5 file (zip -> carrier, pricing
locality, rural indicator). Fixed-width text; layout from ZIP5lyout.txt:
state 1-2, zip 3-7, carrier 8-12, locality 13-14, rural indicator 15
(blank = urban, R = rural, B = super rural), lab CB locality 16-17,
plus-four flag 21. Used for ambulance rates and to map any zip to its MPFS locality.
"""
from __future__ import annotations

import io

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..runner import Context, ReleaseOutput

SORT_BY = ["zip5"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["zip5"])
    lines = m.read_bytes().decode("latin-1").splitlines()
    s = pl.Series("l", [ln for ln in lines if len(ln) >= 15 and ln[2:7].isdigit()])
    sl = lambda a, b: s.str.slice(a - 1, b - a + 1)
    df = pl.DataFrame({
        "state": sl(1, 2), "zip5": sl(3, 7), "carrier": sl(8, 12), "locality": sl(13, 14),
        "rural_indicator": sl(15, 15).str.strip_chars().replace("", "U"),
        "lab_cb_locality": sl(16, 17).str.strip_chars(),
        "plus_four_flag": sl(21, 21) == "1",
    })
    bad = df.filter(~pl.col("rural_indicator").is_in(["U", "R", "B"])).height
    if bad:
        ctx.warn(f"{bad} zip rows with an unknown rural indicator")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
