"""Table 12 — ref_dmepos: DMEPOS fee schedule, one row per HCPCS x modifiers x state.

The CMS file is wide: after HCPCS, Mod, Mod2, JURIS, CATG, Ceiling, Floor it has
two columns per state, "OH (NR)" (non-rural) and "OH (R)" (rural). We store
both: fee_nonrural and fee_rural (null where the file has 0.00 for rural, which
means no separate rural fee). Use the rural fee when the patient's zip is in
ref_dmepos_rural_zip for that quarter.
"""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date, code, hcpcs_level2_description, money
from ..common.tabular import find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "modifier", "modifier2", "state"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["fees"])
    df = read_cms_csv(m, header_startswith="HCPCS", key_regex=r"^[0-9A-Z]{5}$", encoding="latin-1")
    state_cols = [c for c in df.columns if re.fullmatch(r"[A-Z]{2} \((NR|R)\)", c.strip())]
    if len(state_cols) < 100:
        raise ValueError(f"{m.lineage_name}: expected about 106 state columns, found {len(state_cols)}")
    col = lambda n: find_col_exact(df, n)
    base = df.select(
        code(df.columns[0]).alias("hcpcs"),
        pl.col(col("Mod")).str.strip_chars().fill_null("").alias("modifier"),
        pl.col(col("Mod2")).str.strip_chars().fill_null("").alias("modifier2"),
        code(col("JURIS")).alias("jurisdiction"),
        code(col("CATG")).alias("category"),
        money(col("Ceiling")).alias("ceiling"),
        money(col("Floor")).alias("floor"),
        pl.col(col("Description")).alias("description"),
        *[money(c).alias(c.strip()) for c in state_cols],
    ).with_row_index("_row")
    long = base.unpivot(index=["_row"], on=[c.strip() for c in state_cols], variable_name="k", value_name="fee")
    long = long.with_columns(pl.col("k").str.slice(0, 2).alias("state"),
                             pl.col("k").str.contains(r"\(R\)").alias("is_rural")).drop("k")
    wide = long.pivot(on="is_rural", index=["_row", "state"], values="fee")
    wide = wide.rename({"false": "fee_nonrural", "true": "fee_rural"})
    wide = wide.with_columns(pl.when(pl.col("fee_rural") == 0).then(None).otherwise(pl.col("fee_rural"))
                             .alias("fee_rural"))
    out = base.select("_row", "hcpcs", "modifier", "modifier2", "jurisdiction", "category",
                      "ceiling", "floor", "description").join(wide, on="_row").drop("_row")
    out = out.with_columns(hcpcs_level2_description("hcpcs", "description").alias("description"))
    out = add_lineage(out, m, effective_start=as_date(rel["effective_start"]),
                      effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=out, members=[m], raw_files=[raw])
