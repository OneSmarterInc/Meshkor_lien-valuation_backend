"""Table 17 helper — ref_geo_zcta_county: Census 2020 ZCTA -> county
relationship file (pipe-separated). One row per ZCTA x county part, with the
land and water area of that part (use AREALAND_PART to split a ZCTA)."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, num
from ..common.tabular import find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["zcta5", "county_fips"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["rel"])
    df = read_cms_csv(mem, header_startswith="OID_ZCTA5", key_col=1, key_regex=r"^\d{5}$", delimiter="|")
    c = lambda n: find_col_exact(df, n)
    df = df.select(
        pl.col(c("GEOID_ZCTA5_20")).alias("zcta5"),
        pl.col(c("GEOID_COUNTY_20")).str.zfill(5).alias("county_fips"),
        pl.col(c("NAMELSAD_COUNTY_20")).alias("county_name"),
        num(c("AREALAND_PART")).alias("area_land_part"),
        num(c("AREAWATER_PART")).alias("area_water_part"),
        num(c("AREALAND_ZCTA5_20")).alias("area_land_zcta"),
    ).with_columns((pl.col("area_land_part") / pl.col("area_land_zcta")).alias("land_share"))
    df = add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
