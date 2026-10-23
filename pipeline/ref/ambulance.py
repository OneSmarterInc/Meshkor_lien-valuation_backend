"""Table 13 — ref_ambulance: Ambulance Fee Schedule by carrier, locality and HCPCS.

The PUF (tab-separated 508 text) gives, per locality and code: RVU, GPCI, base
rate, and the urban, rural and super-rural ("lowest quartile") amounts. For
mileage codes (A0425, A0435, A0436) the amounts are per mile and the last
column is the rural rate for miles 1-17. Which amount applies depends on the
pickup zip: see ref_zip_locality (rural_indicator blank = urban, R = rural,
B = super rural) and the ambulance_rate() macro.
"""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date, code, money, num
from ..common.tabular import member_rows, read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["carrier", "locality", "hcpcs"]


def _header(m, delim: str) -> tuple[str, int]:
    """(first cell of the header row, index of the carrier column).
    The header row is the row that has an HCPCS column. Column order changes:
    2026 and 2024 start with CONTRACTOR/CARRIER, 2025 starts with HCPCS."""
    for r in member_rows(m, encoding="latin-1", delimiter=delim)[:30]:
        cells = [_squash(c) for c in r]
        if "HCPCS" in cells and cells[0]:
            car = next((i for i, c in enumerate(cells) if "CONTRACTOR" in c or "CARRIER" in c), None)
            if car is None:
                raise ValueError(f"{m.lineage_name}: header has no CONTRACTOR/CARRIER column: {r}")
            first = re.sub(r"\s+", " ", r[0].replace("\ufeff", "").replace("\u00ef\u00bb\u00bf", "")).strip()
            return first[:10], car
    raise ValueError(f"{m.lineage_name}: no header row with an HCPCS column in the first 30 rows")


def _squash(text: str) -> str:
    """Upper case, BOM and all spaces removed: 'RURALBASE RATE' == 'RURAL BASE RATE'."""
    return re.sub(r"\s+", "", (text or "").replace("\ufeff", "").replace("\u00ef\u00bb\u00bf", "")).upper()


def _col(df: pl.DataFrame, *words: str, exact: bool = False) -> str | None:
    want = [_squash(w) for w in words]
    for c in df.columns:
        sc = _squash(c)
        if (sc == want[0]) if exact else all(w in sc for w in want):
            return c
    return None


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["afs"])
    # 2026 is a tab-separated .txt; the 2024 and 2025 508 files are .csv
    delim = "," if m.name.lower().endswith(".csv") else "\t"
    first, car = _header(m, delim)
    df = read_cms_csv(m, header_startswith=first, delimiter=delim, key_col=car,
                      key_regex=r"^\d{4,5}$", encoding="latin-1")   # Excel-saved CSVs can drop the leading 0

    def need(*words, exact=False):
        c = _col(df, *words, exact=exact)
        if c is None:
            raise KeyError(f"{m.lineage_name}: no column like {words} in {df.columns}")
        return c

    def opt(*words):
        c = _col(df, *words)
        if c is None:
            ctx.warn(f"{rel['period']}: no column like {words}; left empty")
            return pl.lit(None, dtype=pl.Float64)
        return money(c)

    df = df.select(
        pl.col(df.columns[car]).str.strip_chars().str.zfill(5).alias("carrier"),
        pl.col(need("LOCALITY", exact=True)).str.strip_chars().str.zfill(2).alias("locality"),
        code(need("HCPCS", exact=True)).alias("hcpcs"),
        num(need("RVU", exact=True)).alias("rvu"),
        num(need("GPCI", exact=True)).alias("gpci"),
        money(need("BASE RATE", exact=True)).alias("base_rate"),
        money(need("URBAN")).alias("rate_urban"),
        money(need("RURAL BASE RATE / RURAL")).alias("rate_rural"),
        opt("LOWEST QUARTILE").alias("rate_super_rural"),
        opt("MILES 1-17").alias("rate_rural_miles_1_17"),
    ).with_columns(pl.col("hcpcs").is_in(["A0425", "A0435", "A0436"]).alias("is_mileage"))
    if df.height == 0:
        raise ValueError(f"{m.lineage_name}: 0 ambulance rows read; check the carrier column")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
