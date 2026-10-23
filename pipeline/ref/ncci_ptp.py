"""Table 6 — ref_ncci_ptp: NCCI procedure-to-procedure edits.

File layout (tab-delimited, CRLF, 6 header lines):
  Column 1 | Column 2 | * = in existence prior to 1996 | Effective Date |
  Deletion Date (* = none) | Modifier (0/1/9) | PTP Edit Rationale

Spec §6: keep deleted edits with their deletion date; store both settings
with a `setting` column. The lineage effective dates are row-level here:
effective_start = edit effective date, effective_end = deletion date
(9999-12-31 when not deleted).

ASSUMPTION to confirm against the NCCI PTP policy manual: the deletion date
is the last date of service the edit applies (inclusive). Edits with
effective = deletion date then apply for that single day.
"""
from __future__ import annotations

import io

import polars as pl

from ..common.config import OPEN_END
from ..runner import Context, ReleaseOutput

SORT_BY = ["setting", "column_1", "column_2", "effective_start"]
# Unique within one release (checked on the Q4 2026 hospital file): the same
# pair can appear twice with the same effective date — once as a real edit
# (modifier 0/1) and once as a withdrawn edit (modifier 9).
KEY = ["setting", "column_1", "column_2", "effective_start", "modifier_indicator"]
COLS = ["column_1", "column_2", "prior_1996", "effective_date", "deletion_date",
        "modifier_indicator", "rationale"]


def _read_part(member) -> pl.DataFrame:
    text = member.read_bytes().decode("latin-1")
    lines = text.splitlines()
    # Data starts at the first line whose first field looks like a code.
    start = next(i for i, ln in enumerate(lines)
                 if ln[:5].isalnum() and len(ln.split("\t")) >= 6 and ln.split("\t")[3].strip().isdigit())
    body = "\n".join(lines[start:])
    df = pl.read_csv(io.StringIO(body), separator="\t", has_header=False, new_columns=COLS,
                     schema_overrides={c: pl.Utf8 for c in COLS}, quote_char=None,
                     truncate_ragged_lines=True)
    return df


def _parse(df: pl.DataFrame, setting: str, version: str) -> pl.DataFrame:
    d = pl.col("deletion_date").str.strip_chars()
    return df.select(
        pl.lit(setting).alias("setting"),
        pl.col("column_1").str.strip_chars().alias("column_1"),
        pl.col("column_2").str.strip_chars().alias("column_2"),
        (pl.col("prior_1996").str.strip_chars() == "*").alias("prior_1996"),
        pl.col("effective_date").str.strip_chars().str.to_date("%Y%m%d").alias("effective_start"),
        pl.when(d == "*").then(None).otherwise(d).str.to_date("%Y%m%d", strict=False).alias("deletion_date"),
        pl.col("modifier_indicator").str.strip_chars().cast(pl.Int8, strict=False).alias("modifier_indicator"),
        pl.col("rationale").str.strip_chars().alias("rationale"),
        pl.lit(version).alias("ncci_version"),
    ).with_columns(
        pl.col("deletion_date").fill_null(pl.lit(OPEN_END)).alias("effective_end"),
        # Modifier indicator 9 = "not applicable": in the Q4 2026 file every
        # such edit has deletion date = effective date (deleted back to its
        # start). Queries treat these as never in effect.
        (pl.col("modifier_indicator") != 9).alias("is_applicable"))


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    frames, members, raws = [], [], []
    files = rel.get("files") or [rel["file"]]
    missing = []
    for f in files:
        try:
            raw = ctx.raw(f)
        except FileNotFoundError:
            missing.append(f)
            continue
        m = raw.member(rel["members"]["ptp"])
        part = _parse(_read_part(m), rel["setting"], rel.get("version", str(rel["period"])))
        part = part.with_columns(pl.lit(m.lineage_name).alias("source_file"),
                                 pl.lit(m.sha256).alias("source_sha256"),
                                 pl.lit(str(rel["period"])).alias("period"))
        frames.append(part)
        members.append(m)
        raws.append(raw)
    if missing:
        ctx.warn(f"{rel['setting']} {rel['period']}: {len(missing)} of {len(files)} parts missing: {missing}")
    if not frames:
        from ..common.raw import RawFileMissing
        raise RawFileMissing(f"no parts found for {rel['setting']} {rel['period']}")
    return ReleaseOutput(df=pl.concat(frames), members=members, raw_files=raws)


def finalize(frames: list[pl.DataFrame], ctx: Context) -> pl.DataFrame:
    """When several quarterly releases are loaded, the same edit appears in
    each. For each edit key keep only the rows from the NEWEST release that
    has it. Rows inside one release are never removed: CMS files can hold two
    rows with the same key (for example, different deletion dates), and the
    published record counts include both."""
    df = pl.concat(frames, how="diagonal_relaxed")
    before = df.height
    if df["period"].n_unique() > 1:
        df = df.filter(pl.col("period") == pl.col("period").max().over(KEY))
    if before != df.height:
        ctx.warn(f"removed {before - df.height:,} rows that newer releases replace")
    same = df.filter(pl.struct(KEY).is_duplicated()).height
    if same:
        ctx.warn(f"{same:,} rows share a key with another row in the same release (kept; see deletion_date)")
    return df
