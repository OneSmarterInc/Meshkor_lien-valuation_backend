"""Lineage columns (Spec §3.4) and shared cleaning helpers."""
from __future__ import annotations

from datetime import date

import polars as pl

from .config import OPEN_END
from .raw import Member

LINEAGE_COLS = ["effective_start", "effective_end", "source_file", "source_sha256"]


def add_lineage(df: pl.DataFrame | pl.LazyFrame, member: Member, *,
                effective_start: date | None = None,
                effective_end: date | None = None,
                period: str | None = None):
    """Add the four lineage columns. If the frame already has row-level
    effective dates (NCCI, NPPES), pass None to keep them."""
    exprs = [
        pl.lit(member.lineage_name).alias("source_file"),
        pl.lit(member.sha256).alias("source_sha256"),
    ]
    if effective_start is not None:
        exprs.append(pl.lit(effective_start, dtype=pl.Date).alias("effective_start"))
    if effective_end is not None:
        exprs.append(pl.lit(effective_end, dtype=pl.Date).alias("effective_end"))
    if period is not None:
        exprs.append(pl.lit(period).alias("period"))
    return df.with_columns(exprs)


def as_date(value) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def money(col: str | pl.Expr) -> pl.Expr:
    """'$1,644.87 ' -> 1644.87"""
    e = pl.col(col) if isinstance(col, str) else col
    return (e.cast(pl.Utf8).str.replace_all(r"[\$,\s]", "")
            .replace("", None).cast(pl.Float64, strict=False))


def num(col: str | pl.Expr) -> pl.Expr:
    e = pl.col(col) if isinstance(col, str) else col
    return e.cast(pl.Utf8).str.strip_chars().replace("", None).cast(pl.Float64, strict=False)


def code(col: str | pl.Expr) -> pl.Expr:
    e = pl.col(col) if isinstance(col, str) else col
    return e.cast(pl.Utf8).str.strip_chars().str.to_uppercase().replace("", None)


def hcpcs_level2_description(code_col: str, desc_col: str) -> pl.Expr:
    """Spec §10: keep descriptions only for HCPCS Level II codes.

    CPT (all-numeric, or 4 digits + F/T/U/M) is AMA-owned; D codes (CDT) are
    ADA-owned. Level II = starts with a letter A–V other than D.
    """
    c = pl.col(code_col)
    is_level2 = c.str.contains(r"^[A-CE-V][0-9A-Z]{4}$")
    return pl.when(is_level2).then(pl.col(desc_col).str.strip_chars()).otherwise(None)


def open_end() -> pl.Expr:
    return pl.lit(OPEN_END, dtype=pl.Date)
