"""Shared reader for the CMS quarterly ASP download (Table 10).

One raw folder per quarter, e.g. ASP/2026Q4, holding the CMS zips and the
files taken out of them. We read only the "Section 508" CSV files: they hold
the same data as the .xls/.xlsx files. Each CSV has 1-13 lines of notes above
the real header, and CMS changes header names between years (_2024_CODE,
_2026_CODE, NDC2, NDC ...). The column-name map below turns every known
header into one schema name; an unknown header stops the load.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, timedelta

import polars as pl

from ..common.raw import Member, RawFile

MONTH_Q = {"january": 1, "april": 2, "july": 3, "october": 4}

# normalised CMS header -> schema column ("" = blank header cell, ignored)
COLMAP = {
    "HCPCSCODE": "hcpcs",
    "SHORTDESCRIPTION": "description", "SHORTDESCRIPTOR": "description",
    "DRUGGENERICNAME": "description", "DRUGGENERICNAMETRADENAME": "description",
    "HCPCSCODEDOSAGE": "dosage", "HCPCSDOSAGE": "dosage", "DOSAGE": "dosage",
    "PAYMENTLIMIT": "payment_limit", "COINSURANCEPERCENTAGE": "coinsurance_pct",
    "VACCINEAWP": "vaccine_awp_pct", "VACCINELIMIT": "vaccine_limit",
    "BLOODAWP": "blood_awp_pct", "BLOODLIMIT": "blood_limit",
    "CLOTTINGFACTOR": "clotting_factor", "NOTES": "notes",
    "LABELERNAME": "labeler", "NDC": "ndc", "NDC2": "ndc", "NDCORALTERNATEID": "ndc",
    "DRUGNAME": "drug_name", "PKGSIZE": "pkg_size", "PKGQTY": "pkg_qty",
    "BILLUNITS": "bill_units", "BILLUNITSPKG": "bill_units_pkg",
}
HEADER_START = re.compile(r"(?i)^\s*(hcpcs code|_\d{4}_code|drug generic name)")
EFFECTIVE = re.compile(r"(?i)(january|april|july|october)\s+1,\s*(\d{4})")


def norm(h: str) -> str:
    h = (h or "").replace("﻿", "").strip()
    if re.fullmatch(r"(?i)_\d{4}_code", h):
        return "HCPCSCODE"
    return re.sub(r"[^A-Z0-9]", "", h.upper())


def quarter_dates(period: str) -> tuple[date, date]:
    """'2026Q4' -> (2026-10-01, 2026-12-31)."""
    m = re.fullmatch(r"(\d{4})Q([1-4])", str(period))
    if not m:
        raise ValueError(f"ASP period must look like 2026Q4, got {period!r}")
    y, q = int(m.group(1)), int(m.group(2))
    start = date(y, 3 * q - 2, 1)
    end = date(y, 12, 31) if q == 4 else date(y, 3 * q + 1, 1) - timedelta(days=1)
    return start, end


def decode(b: bytes) -> str:
    """Most CMS 508 files are Windows-1252, a few are UTF-8."""
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return b.decode("cp1252", errors="replace")


def find_one(raw: RawFile, pattern: str | None, required: bool) -> Member | None:
    if not pattern:
        return None
    found = raw.members(pattern)
    if len(found) > 1:
        raise ValueError(f"{raw.rel_path}: pattern {pattern!r} matched {len(found)} files "
                         f"({[m.name for m in found]}); expected 1. Delete the extra copy.")
    if not found:
        if required:
            raise ValueError(f"{raw.rel_path}: no file matches {pattern!r}")
        return None
    return found[0]


def read_508(member: Member, period: str) -> tuple[pl.DataFrame, int]:
    """Return (all-string frame with schema column names, header line number)."""
    rows = list(csv.reader(io.StringIO(decode(member.read_bytes()), newline="")))
    hdr = next((i for i, r in enumerate(rows) if r and HEADER_START.match(r[0])), None)
    if hdr is None:
        raise ValueError(f"{member.lineage_name}: header row not found")
    # quarter check: the 'Effective <Month> 1, <Year>' line must match the folder
    for r in rows[:hdr]:
        m = EFFECTIVE.search(" ".join(r))
        if m:
            got = f"{m.group(2)}Q{MONTH_Q[m.group(1).lower()]}"
            if got != period:
                raise ValueError(f"{member.lineage_name}: file says {got}, folder says {period}. "
                                 "Wrong folder?")
            break
    cols = []
    for j, h in enumerate(rows[hdr]):
        n = norm(h)
        if not n:
            continue
        if n not in COLMAP:
            raise ValueError(f"{member.lineage_name}: unknown header {h!r}. Add it to COLMAP.")
        cols.append((j, COLMAP[n]))
    names = [c for _, c in cols]
    data = []
    for r in rows[hdr + 1:]:
        vals = [(r[j].strip() if j < len(r) else "") for j, _ in cols]
        if any(vals):
            data.append(vals)
    df = pl.DataFrame(data, schema={n: pl.Utf8 for n in names}, orient="row")
    df = df.with_columns([pl.col(c).replace("", None) for c in names])
    return df, hdr + 1


def to_num(c: str) -> pl.Expr:
    return (pl.col(c).str.replace_all(r"[\$,\s%]", "").replace("", None)
            .cast(pl.Float64, strict=False).alias(c))


def ndc11(c: str = "ndc") -> pl.Expr:
    """'13533-0636-01' (any 4-4-2 / 5-3-2 / 5-4-1 dash form) -> '13533063601'.
    NULL for an alternate ID that is not an NDC."""
    p = pl.col(c).str.strip_chars().str.replace_all("[\u2010-\u2015\u00ad]", "-")
    parts = p.str.extract_groups(r"^(\d{4,5})-(\d{3,4})-(\d{1,2})$")
    dashed = (parts.struct.field("1").str.zfill(5) + parts.struct.field("2").str.zfill(4)
              + parts.struct.field("3").str.zfill(2))
    return (pl.when(p.str.contains(r"^\d{11}$")).then(p)
            .when(p.str.contains(r"^\d{4,5}-\d{3,4}-\d{1,2}$")).then(dashed)
            .otherwise(None).alias("ndc11"))
