"""Table 10b - ref_ndc_hcpcs: CMS NDC-HCPCS crosswalks, one row per NDC per
HCPCS per quarter per crosswalk (ASP, OPPS, AWP, NOC, PREP). Gives the
billable units per NDC package (bill_units_pkg), which turns a hospital's
NDC price into a price per HCPCS unit. ndc11 (no dashes) joins to NADAC and
the FDA NDC directory."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage
from ..runner import Context, ReleaseOutput
from ._asp_common import find_one, ndc11, quarter_dates, read_508, to_num

SORT_BY = ["crosswalk_type", "hcpcs", "ndc", "effective_start"]
NUM = ["pkg_size", "pkg_qty", "bill_units", "bill_units_pkg"]
TEXT = ["hcpcs", "description", "labeler", "ndc", "drug_name", "dosage"]
KINDS = (("ASP", "asp_xw", True), ("OPPS", "opps_xw", False), ("AWP", "awp_xw", False),
         ("NOC", "noc_xw", False), ("PREP", "prep_xw", False))


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    period = str(rel["period"])
    start, end = quarter_dates(period)
    pats = rel["members"]
    frames, used = [], []
    for kind, key, required in KINDS:
        mem = find_one(raw, pats.get(key), required)
        if mem is None:
            continue
        df, hdr = read_508(mem, period)
        for c in TEXT + NUM:
            if c not in df.columns:
                df = df.with_columns(pl.lit(None, dtype=pl.Utf8).alias(c))
        df = (df.with_columns(pl.col("hcpcs").str.to_uppercase(), pl.col("ndc").str.strip_chars())
                .filter(pl.col("ndc").is_not_null())
                .with_columns(ndc11(), *[to_num(c) for c in NUM],
                              pl.lit(kind).alias("crosswalk_type"), pl.lit(hdr).alias("header_line"))
                .select(*TEXT, "ndc11", *NUM, "crosswalk_type", "header_line"))
        frames.append(add_lineage(df, mem, effective_start=start, effective_end=end, period=period))
        used.append(mem)
    return ReleaseOutput(df=pl.concat(frames, how="vertical_relaxed"), members=used, raw_files=[raw])
