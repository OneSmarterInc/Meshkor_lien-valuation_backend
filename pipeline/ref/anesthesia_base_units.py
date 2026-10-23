"""Table 14 (part 2) — ref_anesthesia_base_units: base units per anesthesia code.

CMS posts this file on the Anesthesiologists Center page. The CY 2022 file is
the latest; CMS says the base units did not change for 2024, 2025 and 2026, so
the release is open-ended (effective_end 9999-12-31) until CMS posts a new one.
Payment = (base units + time units [minutes / 15]) x anesthesia CF (ref_anesthesia_cf).
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["base_units"])
    delim = "\t" if m.name.lower().endswith(".txt") else ","
    df = read_cms_csv(m, header_startswith="CODE", delimiter=delim, key_regex=r"^\d{5}$", encoding="latin-1")
    df = df.select(pl.col(df.columns[0]).str.strip_chars().alias("hcpcs"),
                   pl.col(df.columns[1]).str.strip_chars().cast(pl.Int32, strict=False).alias("base_units"))
    bad = df.filter(pl.col("base_units").is_null()).height
    if bad:
        ctx.warn(f"{bad} anesthesia codes without a base unit")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
