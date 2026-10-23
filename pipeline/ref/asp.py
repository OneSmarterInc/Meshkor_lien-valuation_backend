"""Table 10a - ref_asp: Medicare Part B drug payment limits, one row per
HCPCS code per quarter (ASP Pricing File; from 2026 "Medicare Part B Payment
Limit File"), plus the NOC drugs (no HCPCS code; NOC Pricing File, to 2025).
payment_limit = ASP + 6 % (8 % for biosimilars), per HCPCS billing unit
(`dosage`). Dates come from the quarter folder (CMS end dates have typos)."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage
from ..runner import Context, ReleaseOutput
from ._asp_common import find_one, quarter_dates, read_508, to_num

SORT_BY = ["price_type", "hcpcs", "description", "effective_start"]
NUM = ["payment_limit", "coinsurance_pct", "vaccine_awp_pct", "vaccine_limit",
       "blood_awp_pct", "blood_limit", "clotting_factor"]
COLS = ["hcpcs", "description", "dosage", *NUM, "notes", "price_type", "header_line"]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    period = str(rel["period"])
    start, end = quarter_dates(period)
    pats = rel["members"]
    frames, used = [], []
    for kind, key, required in (("ASP", "pricing", True), ("NOC", "noc_pricing", False)):
        mem = find_one(raw, pats.get(key), required)
        if mem is None:
            continue
        df, hdr = read_508(mem, period)
        for c in COLS:
            if c not in df.columns and c not in ("price_type", "header_line"):
                df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
        df = df.with_columns(
            pl.col("hcpcs").str.to_uppercase() if kind == "ASP" else pl.lit(None, dtype=pl.Utf8).alias("hcpcs"),
            *[to_num(c) for c in NUM],
            pl.lit(kind).alias("price_type"), pl.lit(hdr).alias("header_line"))
        key_col = "hcpcs" if kind == "ASP" else "description"
        df = df.filter(pl.col(key_col).is_not_null()).select(COLS)
        frames.append(add_lineage(df, mem, effective_start=start, effective_end=end, period=period))
        used.append(mem)
    return ReleaseOutput(df=pl.concat(frames, how="vertical_relaxed"), members=used, raw_files=[raw])
