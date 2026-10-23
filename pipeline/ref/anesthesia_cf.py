"""Table 14 — ref_anesthesia_cf: anesthesia conversion factor per locality.

ANES file columns: contractor, locality, locality name, QP CF, non-QP CF.
We store the non-qualifying-APM CF as the standard rate (and the QP CF for
reference). Anesthesia base units are a separate CMS file (Anesthesiologists
Center); they are not in RVU26D. See README "known gaps".
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date, num
from ..common.tabular import read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["carrier", "locality"]


def cf_columns(cols: list[str]) -> tuple[str, str | None]:
    """(standard CF column, QP CF column or None).
    CY2026 has 2 factors (qualifying APM participant and non-qualifying).
    CY2024 and CY2025 have 1 conversion factor for everyone."""
    up = {c: c.upper() for c in cols}
    nonqp = next((c for c, u in up.items() if "NON-QUALIFYING" in u or "NON QUALIFYING" in u), None)
    qp = next((c for c, u in up.items() if "QUALIFYING" in u and "NON" not in u), None)
    if nonqp:
        return nonqp, qp
    single = [c for c, u in up.items() if "CONVERSION" in u or "FACTOR" in u or u.strip() in ("CF", "ANES CF")]
    if len(single) == 1:
        return single[0], None
    if len(cols) >= 4:      # contractor, locality, locality name, conversion factor
        return cols[3], None
    raise KeyError(f"no anesthesia conversion factor column in {cols}")


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["anes"])
    df = read_cms_csv(m, header_startswith="Contractor", key_regex=r"^\s*\d{5}\s*$")
    c = df.columns
    nonqp, qp = cf_columns(c)
    df = df.select(
        pl.col(c[0]).str.strip_chars().alias("carrier"),
        pl.col(c[1]).str.strip_chars().str.zfill(2).alias("locality"),
        pl.col(c[2]).str.strip_chars().str.replace_all(r"\*+$", "").alias("locality_name"),
        num(nonqp).alias("anesthesia_cf"),
        (num(qp) if qp else pl.lit(None, dtype=pl.Float64)).alias("anesthesia_cf_qp"),
    )
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
