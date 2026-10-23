"""Table 20 — ref_ownership: owners of Medicare-enrolled hospitals.
Sources: "Hospital All Owners" (dataset = all_owners) and "Hospital Change of
Ownership - Owner Information" (dataset = chow_owners). One row per hospital
enrollment x owner x role. Join to a CCN / NPI through
ref_ccn_npi.enrollment_id (view v_hospital_owners).

Column names follow the CMS file in snake_case ("PERCENTAGE OWNERSHIP" ->
percentage_ownership). Y/N flag columns become booleans."""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["enrollment_id", "owner_associate_id", "role_code"]
RENAME = {
    "enrollment_id": "enrollment_id", "associate_id": "associate_id", "organization_name": "organization_name",
    "associate_id_owner": "owner_associate_id", "type_owner": "owner_type", "role_code_owner": "role_code",
    "role_text_owner": "role_text", "association_date_owner": "association_date",
}


def snake(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def tidy(df: pl.DataFrame, rename: dict) -> pl.DataFrame:
    df = df.rename({c: rename.get(snake(c), snake(c)) for c in df.columns})
    flags = [c for c in df.columns
             if df[c].drop_nulls().str.strip_chars().is_in(["Y", "N"]).all() and df[c].drop_nulls().len() > 0]
    return df.with_columns(
        *[pl.col(c).str.strip_chars().replace("", None) for c in df.columns if c not in flags],
        *[(pl.col(c).str.strip_chars() == "Y").alias(c) for c in flags])


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    frames, members = [], []
    for key in ("all_owners", "chow_owners"):
        pat = rel["members"].get(key)
        if not pat:
            continue
        mem = raw.member(pat)
        df = tidy(read_csv_fast(mem), RENAME).with_columns(
            pl.lit(key).alias("dataset"),
            pl.col("association_date").str.strptime(pl.Date, "%m/%d/%Y", strict=False),
            pl.col("percentage_ownership").cast(pl.Float64, strict=False),
            pl.coalesce("organization_name_owner",
                        pl.concat_str(["first_name_owner", "last_name_owner"], separator=" ", ignore_nulls=True)
                        ).alias("owner_name"))
        frames.append(add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                                  effective_end=as_date(rel["effective_end"]), period=str(rel["period"])))
        members.append(mem)
    # a flag column that is empty in one file stays text there: make it boolean in every file
    flags = {c for f in frames for c, t in f.schema.items() if t == pl.Boolean}
    frames = [f.with_columns(*[(pl.col(c) == "Y").alias(c) for c in flags
                               if c in f.columns and f.schema[c] != pl.Boolean]) for f in frames]
    return ReleaseOutput(df=pl.concat(frames, how="diagonal_relaxed"), members=members, raw_files=[raw])
