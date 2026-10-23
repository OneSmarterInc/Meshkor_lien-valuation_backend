"""Table 5 — ref_asc: ASC payment rates (Addendum AA surgical procedures and
Addendum BB covered ancillary services), with payment-indicator meanings
from Addendum DD1. Rates are national; wage adjustment happens at query time.
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, code, hcpcs_level2_description, money, num
from ..common.tabular import find_col, guess_delimiter, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "effective_start"]
HCPCS_RX = r"^[0-9A-Z]{5}$"


def _addendum(member, which: str) -> pl.DataFrame:
    df = read_cms_csv(member, header_startswith="HCPCS Code", key_regex=HCPCS_RX,
                      delimiter=guess_delimiter(member))
    if which == "AA":
        mpd = pl.col(find_col(df, "Multiple Procedure")).str.strip_chars().eq("Y")
    else:
        mpd = pl.lit(None, dtype=pl.Boolean)
    out = df.select(
        code(df.columns[0]).alias("hcpcs"),
        pl.col(find_col(df, "Short Descriptor")).alias("description"),
        code(find_col(df, "Payment Indicator")).alias("payment_indicator"),
        num(find_col(df, "Payment Weight")).alias("payment_weight"),
        money(find_col(df, "Payment Rate")).alias("payment_rate"),
        mpd.alias("multiple_procedure_discount"),
    ).with_columns(pl.lit(which).alias("addendum"))
    return out.with_columns(hcpcs_level2_description("hcpcs", "description").alias("description"))


def _indicators(member) -> pl.DataFrame:
    df = read_cms_csv(member, header_startswith="Indicator", key_regex=r"^[A-Z0-9]{2}$",
                      delimiter=guess_delimiter(member))
    return df.select(code(df.columns[0]).alias("payment_indicator"),
                     pl.col(df.columns[1]).str.strip_chars().alias("payment_indicator_desc"))


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = rel["members"]
    aa_m, bb_m = raw.member(m["aa"]), raw.member(m["bb"])
    frames = []
    for mem, which in ((aa_m, "AA"), (bb_m, "BB")):
        d = _addendum(mem, which)
        frames.append(add_lineage(d, mem, effective_start=as_date(rel["effective_start"]),
                                  effective_end=as_date(rel["effective_end"]),
                                  period=str(rel["period"])))
    df = pl.concat(frames, how="diagonal_relaxed")
    members = [aa_m, bb_m]
    if m.get("dd1"):
        dd1_m = raw.member(m["dd1"])
        df = df.join(_indicators(dd1_m), on="payment_indicator", how="left")
        members.append(dd1_m)
    dupes = df.group_by("hcpcs").len().filter(pl.col("len") > 1)
    if dupes.height:
        ctx.warn(f"{dupes.height} HCPCS codes appear in both AA and BB in {rel['period']}")
    return ReleaseOutput(df=df, members=members, raw_files=[raw])
