"""Table 11 — ref_clfs: Clinical Laboratory Fee Schedule (national limit per HCPCS).

The PUF CSV has title lines, then a header "YEAR,HCPCS,MOD,EFF_DATE,INDICATOR,RATE,..."
RATE is the national limitation amount. Descriptions are kept only for HCPCS
Level II codes (Spec §10); CPT and PLA descriptions are dropped.
"""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date, code, hcpcs_level2_description, money
from ..common.tabular import find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "modifier", "effective_start"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["clfs"])
    df = read_cms_csv(m, header_startswith="YEAR", key_col=1, key_regex=r"^[0-9A-Z]{5}$", encoding="latin-1")

    def col(*names: str, required: bool = True) -> str | None:
        c = find_col_exact(df, *names)
        if c is None and required:
            raise ValueError(f"CLFS {rel['period']}: no column {names} in {df.columns}")
        return c
    # CY2024 Q1-Q3 files name the rate column RATE2024; later files use RATE.
    rate_col = find_col_exact(df, "RATE", "NATIONAL LIMIT", "PAYMENT RATE") or next(
        (c for c in df.columns if re.fullmatch(r"RATE\s*20\d\d", c.strip().upper())), None)
    if rate_col is None:
        raise ValueError(f"CLFS {rel['period']}: no rate column in {df.columns}")
    eff = pl.col(col("EFF_DATE", "EFFECTIVE DATE", "EFF DATE")).str.strip_chars()
    df = df.select(
        code(col("HCPCS")).alias("hcpcs"),
        pl.col(col("MOD", "MODIFIER")).str.strip_chars().fill_null("").alias("modifier"),
        money(rate_col).alias("rate"),
        code(col("INDICATOR", "IND")).alias("indicator"),
        pl.when(eff.str.contains(r"^\d{8}$")).then(eff.str.strptime(pl.Date, "%Y%m%d", strict=False))
          .alias("code_effective_date"),
        (pl.col(d) if (d := col("SHORTDESC", "SHORT DESC", "SHORT DESCRIPTION", "SHORT DESCRIPTOR",
                                "DESCRIPTION", required=False)) else pl.lit(None, dtype=pl.Utf8)).alias("description"),
    ).with_columns(hcpcs_level2_description("hcpcs", "description").alias("description"))
    dup = df.select(pl.struct("hcpcs", "modifier").is_duplicated().sum()).item()
    if dup:
        ctx.warn(f"{dup} duplicate hcpcs+modifier rows in CLFS {rel['period']}")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
