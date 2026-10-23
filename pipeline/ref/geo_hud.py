"""Table 17 — ref_geo: HUD-USPS ZIP crosswalk, ZIP -> county and ZIP -> CBSA,
one release per quarter. One ZIP can be split over 2+ counties; the ratios
say which share of the ZIP's addresses (residential, business, other, total)
is in each county or CBSA. CBSA 99999 = the part of the ZIP outside any CBSA.
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, num
from ..common.tabular import find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["geo_type", "zip5", "geoid", "effective_start"]


def _read(member, geo_type: str) -> pl.DataFrame:
    df = read_cms_csv(member, header_startswith="zip", key_regex=r"^\d{3,5}$")
    c = lambda *n: find_col_exact(df, *n)
    width = 5
    return df.select(
        pl.col(c("zip")).str.strip_chars().str.zfill(5).alias("zip5"),
        pl.lit(geo_type).alias("geo_type"),
        pl.col(c("geoid", "county", "cbsa")).str.strip_chars().str.zfill(width).alias("geoid"),
        pl.col(c("city", "usps_zip_pref_city")).str.strip_chars().alias("city"),
        pl.col(c("state", "usps_zip_pref_state")).str.strip_chars().alias("state"),
        *[num(c(r)).alias(r) for r in ("res_ratio", "bus_ratio", "oth_ratio", "tot_ratio")],
    )


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = rel["members"]
    members, frames = [], []
    for key, geo in (("county", "county"), ("cbsa", "cbsa")):
        if not m.get(key):
            continue
        mem = raw.member(m[key])
        frames.append(add_lineage(_read(mem, geo), mem, effective_start=as_date(rel["effective_start"]),
                                  effective_end=as_date(rel["effective_end"]), period=str(rel["period"])))
        members.append(mem)
    df = pl.concat(frames, how="diagonal_relaxed")
    return ReleaseOutput(df=df, members=members, raw_files=[raw])
