"""Table 6 — ref_mue: Medically Unlikely Edits, practitioner and outpatient
hospital (Spec §6: separate download, keep the adjudication indicator).

The CSV is Latin-1, starts with an AMA notice, and its header cell is
"HCPCS/\\nCPT Code" (a quoted line break).
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, code
from ..common.tabular import find_col, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "setting", "effective_start"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["mue"])
    df = read_cms_csv(m, header_startswith="HCPCS", encoding="latin-1",
                      key_regex=r"^[0-9A-Z]{5}$")
    mai = pl.col(find_col(df, "Adjudication Indicator")).str.strip_chars()
    df = df.select(
        code(df.columns[0]).alias("hcpcs"),
        pl.lit(rel["setting"]).alias("setting"),
        pl.col(find_col(df, "MUE Values")).str.strip_chars().cast(pl.Int32, strict=False).alias("mue_value"),
        mai.str.extract(r"^(\d)").cast(pl.Int8).alias("mue_adjudication_indicator"),
        mai.str.replace(r"^\d\s*", "").alias("mue_adjudication_desc"),
        pl.col(find_col(df, "Rationale")).str.strip_chars().alias("mue_rationale"),
    )
    bad = df.filter(pl.col("mue_value").is_null() | pl.col("mue_adjudication_indicator").is_null())
    if bad.height:
        ctx.warn(f"{bad.height} MUE rows with blank value or indicator ({rel['setting']})")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
