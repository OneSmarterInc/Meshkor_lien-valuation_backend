"""Table 3 — ref_opps: OPPS Addendum B (national rates by HCPCS).

Spec §6: store the national rate and the status indicator. The hospital's
actual rate needs the wage index (labor share x wage index + non-labor
share); that is done in a DuckDB view joined to ref_ipps_hospital.

STATUS: written against the usual Addendum B layout (title rows, then a
header row starting "HCPCS Code"). The column finder fails loudly if a
column is missing. Confirm on the real October 2026 file.
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, code, hcpcs_level2_description, money, num
from ..common.tabular import find_col, find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "effective_start"]


def _pick_member(raw, pattern: str):
    ms = raw.members(pattern)
    for ext in (".csv", ".xlsx", ".txt"):
        cands = [m for m in ms if m.name.lower().endswith(ext) and "addendum b" in m.name.lower().replace("_", " ").replace("-", " ")]
        cands = cands or [m for m in ms if m.name.lower().endswith(ext)]
        if cands:
            return sorted(cands, key=lambda m: len(m.name))[0]
    raise ValueError(f"{raw.path.name}: no CSV/XLSX member found ({[m.name for m in ms]})")


def parse(member) -> pl.DataFrame:
    df = read_cms_csv(member, header_startswith="HCPCS", key_regex=r"^[0-9A-Z]{5}$")
    si = find_col_exact(df, "SI", "Status Indicator") or find_col(df, "STATUS", "INDICATOR")
    apc = find_col_exact(df, "APC")
    if apc is None:
        apc = find_col(df, "APC")
    cols = {
        "hcpcs": df.columns[0],
        "description": find_col(df, "SHORT DESCRIPTOR"),
        "status_indicator": si,
        "apc": apc,
        "relative_weight": find_col(df, "RELATIVE WEIGHT"),
        "payment_rate": find_col(df, "PAYMENT RATE"),
        "national_unadjusted_copay": find_col(df, "NATIONAL UNADJUSTED"),
        "minimum_unadjusted_copay": find_col(df, "MINIMUM UNADJUSTED"),
    }
    out = df.select(
        # Excel can store all-digit codes as numbers ("00100" -> 100); pad back.
        code(cols["hcpcs"]).str.zfill(5).alias("hcpcs"),
        pl.col(cols["description"]).alias("description"),
        code(cols["status_indicator"]).alias("status_indicator"),
        pl.col(cols["apc"]).str.strip_chars().replace("", None).alias("apc"),
        num(cols["relative_weight"]).alias("relative_weight"),
        money(cols["payment_rate"]).alias("payment_rate_national"),
        money(cols["national_unadjusted_copay"]).alias("national_unadjusted_copay"),
        money(cols["minimum_unadjusted_copay"]).alias("minimum_unadjusted_copay"),
    )
    return out.with_columns(hcpcs_level2_description("hcpcs", "description").alias("description"))


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = _pick_member(raw, rel["members"].get("addendum_b", "*"))
    df = parse(m)
    if df.select(pl.col("hcpcs").is_duplicated().any()).item():
        ctx.warn("duplicate HCPCS rows in Addendum B; check the file")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
