"""Readers for CMS-style CSVs that carry title rows, copyright notes and
footnotes around the real table."""
from __future__ import annotations

import csv
import io
import re

import polars as pl

from .raw import Member


def _norm(s: str) -> str:
    # strip a UTF-8 BOM, whether decoded as UTF-8 or as latin-1
    return re.sub(r"\s+", " ", (s or "").replace("﻿", "").replace("ï»¿", "")).strip()


def read_cms_csv(member: Member, *, header_startswith: str, encoding: str = "utf-8-sig",
                 key_col: int = 0, key_regex: str | None = None,
                 header_rows: int = 1, delimiter: str = ",") -> pl.DataFrame:
    """Find the header row whose first cell starts with `header_startswith`
    (case-insensitive), then keep data rows whose `key_col` matches
    `key_regex`. Returns all-string columns named from the header.

    `header_rows` > 1 joins that many rows above-and-including the found row
    (the RVU file spreads one header over 5 rows).
    """
    rows = member_rows(member, encoding=encoding, delimiter=delimiter)
    target = header_startswith.lower()
    hdr_idx = next((i for i, r in enumerate(rows)
                    if r and _norm(r[0]).lower().startswith(target)), None)
    if hdr_idx is None:
        raise ValueError(f"{member.lineage_name}: header row starting {header_startswith!r} not found")
    stack = rows[max(0, hdr_idx - header_rows + 1): hdr_idx + 1]
    width = max(len(r) for r in stack)
    names = []
    for j in range(width):
        parts = [_norm(r[j]) for r in stack if j < len(r) and _norm(r[j])]
        names.append(" ".join(parts) or f"col_{j}")
    names = _dedupe(names)
    rx = re.compile(key_regex) if key_regex else None
    data = []
    for r in rows[hdr_idx + 1:]:
        if not r or key_col >= len(r):
            continue
        k = r[key_col].strip()
        if not k or (rx and not rx.match(k)):
            continue
        r = (r + [""] * width)[:width]
        data.append(r)
    return pl.DataFrame(data, schema={n: pl.Utf8 for n in names}, orient="row")


def guess_delimiter(member: Member, encoding: str = "utf-8-sig") -> str:
    """Tab for a tab-separated .txt (CMS ASC Jan/Jul 2024), else comma."""
    if not member.name.lower().endswith(".txt"):
        return ","
    head = member.read_bytes()[:20000].decode(encoding, errors="replace")
    return "\t" if head.count("\t") > head.count(",") else ","


def read_csv_fast(member: Member, *, separator: str = ",", quote_char: str | None = '"',
                  encoding: str = "utf8-lossy") -> pl.DataFrame:
    """Large plain CSV/TXT with the header in row 1 (NADAC, FDA NDC, CMS data
    catalog files): read with Polars, every column as text, BOM removed from names."""
    import io as _io
    df = pl.read_csv(_io.BytesIO(member.read_bytes()), separator=separator, quote_char=quote_char,
                     infer_schema_length=0, encoding=encoding, truncate_ragged_lines=True)
    return df.rename({c: _norm(c) for c in df.columns})


def member_rows(member: Member, *, encoding: str = "utf-8-sig", delimiter: str = ",") -> list[list[str]]:
    """All rows of a CSV or the first sheet of an XLSX, as strings."""
    name = member.name.lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(member.read_bytes()), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        out = []
        for r in ws.iter_rows(values_only=True):
            out.append(["" if v is None else _cell(v) for v in r])
        wb.close()
        return out
    text = member.read_bytes().decode(encoding, errors="replace")
    # newline='' lets csv accept \r, \n and \r\n line ends (some CMS files end lines with a bare \r)
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


def _cell(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if hasattr(v, "strftime"):
        return v.strftime("%m/%d/%Y")
    return str(v)


def find_col_exact(df: pl.DataFrame, *names: str) -> str | None:
    want = {re.sub(r"[^A-Z0-9]", "", n.upper()) for n in names}
    for c in df.columns:
        if re.sub(r"[^A-Z0-9]", "", c.upper()) in want:
            return c
    return None


def _dedupe(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for n in names:
        if n in seen:
            seen[n] += 1
            out.append(f"{n}_{seen[n]}")
        else:
            seen[n] = 0
            out.append(n)
    return out


def find_col(df: pl.DataFrame, *must: str, exclude: tuple[str, ...] = ()) -> str:
    """First column whose upper-case name contains every word in `must`."""
    for c in df.columns:
        u = c.upper()
        if all(m.upper() in u for m in must) and not any(x.upper() in u for x in exclude):
            return c
    raise KeyError(f"No column containing {must} in {df.columns}")
