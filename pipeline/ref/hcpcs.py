"""ref_hcpcs_code - CMS HCPCS Level II quarterly file (alpha-numeric codes:
A-V, no CPT). One row per code (record_type 'code') or modifier
('modifier') per quarter. Reads the ANWEB .xlsx (one row per code, long
description already joined); the .txt holds the same data in fixed width.
dose_from_description = the unit at the end of a drug descriptor
("Injection, pembrolizumab, 1 mg" -> "1 mg"); the ASP file `dosage` is the
billing unit Medicare uses."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage
from ..common.tabular import member_rows
from ..runner import Context, ReleaseOutput
from ._asp_common import quarter_dates

SORT_BY = ["record_type", "hcpcs", "effective_start"]
SKIP = ("trans", "correct", "changes")
COLS = {   # CMS header -> column
    "HCPC": "hcpcs", "RECID": "recid", "LONG DESCRIPTION": "long_description",
    "SHORT DESCRIPTION": "short_description", "PRICE1": "pricing_indicator", "PRICE2": "pricing_indicator_2",
    "PRICE3": "pricing_indicator_3", "PRICE4": "pricing_indicator_4", "MULT_PI": "multiple_pricing_indicator",
    "STATUTE": "statute", "XREF1": "xref1", "XREF2": "xref2", "XREF3": "xref3", "XREF4": "xref4", "XREF5": "xref5",
    "COV": "coverage_code", "ASC_GRP": "asc_group", "OPPS": "mog_group", "OPPS_PI": "mog_indicator",
    "PROCNOTE": "processing_note", "BETOS": "betos", "TOS1": "tos1", "TOS2": "tos2", "TOS3": "tos3",
    "TOS4": "tos4", "TOS5": "tos5", "ANEST_BU": "anesthesia_base_units", "ADD DT": "added_date",
    "ACT EFF DT": "action_effective_date", "TERM DT": "termination_date", "ACTION CD": "action_code",
}
DOSE = (r"(?i)[,\s]\s*((?:per\s+|up to\s+)?(?:[0-9][0-9.,]*\s*)?(?:usp\s+)?(?:mg|mcg|micrograms?|milligrams?|ml|cc|"
        r"units?|k?iu|gm?|grams?|mci|millicuries?|microcuries?|meq|mmol|sq\.? ?cm|cm|ug))\b")
DATES = ["added_date", "action_effective_date", "termination_date"]


def _member(raw, pattern):
    found = [m for m in raw.members(pattern)
             if not any(s in m.name.rsplit("/", 1)[-1].lower() for s in SKIP)]
    if len(found) != 1:
        raise ValueError(f"{raw.rel_path}: pattern {pattern!r} matched {[m.name for m in found]}; expected 1")
    return found[0]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    period = str(rel["period"])
    start, end = quarter_dates(period)
    mem = _member(raw, rel["members"]["anweb"])
    rows = member_rows(mem)
    hdr = [str(h or "").strip().upper() for h in rows[0]]
    missing = [h for h in ("HCPC", "RECID", "LONG DESCRIPTION", "SHORT DESCRIPTION") if h not in hdr]
    if missing:
        raise ValueError(f"{mem.lineage_name}: header {missing} not found; got {hdr[:8]}")
    idx = [(hdr.index(h), c) for h, c in COLS.items() if h in hdr]
    data = [[(r[i].strip() if i < len(r) and r[i] is not None else "") for i, _ in idx] for r in rows[1:]]
    df = pl.DataFrame(data, schema={c: pl.Utf8 for _, c in idx}, orient="row")
    df = df.with_columns([pl.col(c).replace("", None) for c in df.columns]).filter(pl.col("hcpcs").is_not_null())
    df = df.with_columns(
        pl.col("hcpcs").str.to_uppercase(),
        pl.when(pl.col("recid").is_in(["7", "8"])).then(pl.lit("modifier")).otherwise(pl.lit("code")).alias("record_type"),
        *[pl.col(c).str.strptime(pl.Date, "%Y%m%d", strict=False) for c in DATES if c in df.columns],
        pl.col("anesthesia_base_units").cast(pl.Int32, strict=False),
        pl.col("long_description").str.extract(DOSE, 1).str.strip_chars().alias("dose_from_description"),
    ).drop("recid")
    # Level II only; a D code (CDT, ADA-owned) keeps no description (Spec §10)
    is_cdt = pl.col("hcpcs").str.starts_with("D") & (pl.col("record_type") == "code")
    df = df.with_columns([pl.when(is_cdt).then(None).otherwise(pl.col(c)).alias(c)
                          for c in ("long_description", "short_description")])
    df = add_lineage(df, mem, effective_start=start, effective_end=end, period=period)
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
