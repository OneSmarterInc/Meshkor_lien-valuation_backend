"""Table 2 — ref_mpfs: Medicare Physician Fee Schedule, every code x locality.

CMS no longer posts a full dollar file per locality, so we compute it from
the RVU release (PPRRVU + GPCI), the same way CMS does:

  rate = (work_rvu * work_gpci + pe_rvu * pe_gpci + mp_rvu * mp_gpci) * CF

with pe_rvu = non-facility or facility PE RVU. Where the "NA" indicator is
set for a setting, that rate is null. Imaging codes on OPPSCAP are capped at
the OPPS amount for that locality (OPPSCAP file, same release).

Spec §6 notes: keep modifier rows (26, TC, 53 ...), store both settings,
confirm Ohio carrier/locality from the locality file (see config/geography).
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import (add_lineage, as_date, code, hcpcs_level2_description,
                              num)
from ..common.tabular import read_cms_csv
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "modifier", "carrier", "locality"]
STREAM = True   # one Parquet file per release (12 quarters x ~2M rows)

PAYABLE_STATUS = {"A", "R", "T"}   # active, restricted, paid-as-bundle exception


def read_rvu(member) -> pl.DataFrame:
    raw = read_cms_csv(member, header_startswith="HCPCS", header_rows=5,
                       key_regex=r"^[0-9A-Z]{5}$")
    # Columns by header name: CMS added "PRIC IND" in 2026, so positions after
    # column 22 differ between releases (CONV FACTOR is 24 in 2024/2025, 25 in 2026).
    cols = raw.columns
    want = {
        "hcpcs": "HCPCS", "modifier": "MOD", "description": "DESCRIPTION", "status_code": "STATUS CODE",
        "work_rvu": "WORK RVU", "pe_rvu_nonfac": "NON-FAC PE RVU", "nonfac_na_ind": "NON-FAC NA INDICATOR",
        "pe_rvu_fac": "FACILITY PE RVU", "fac_na_ind": "FACILITY NA INDICATOR", "mp_rvu": "MP RVU",
        "pctc_ind": "PCTC IND", "global_days": "GLOB DAYS", "mult_proc": "MULT PROC",
        "bilat_surg": "BILAT SURG", "asst_surg": "ASST SURG", "co_surg": "CO- SURG",
        "team_surg": "TEAM SURG", "conversion_factor": "CONV FACTOR",
    }
    pick = {n: _col_index(cols, h) for n, h in want.items()}
    df = raw.select([pl.col(cols[i]).alias(n) for n, i in pick.items()])
    return df.with_columns(
        code("hcpcs"),
        pl.col("modifier").str.strip_chars().fill_null("").alias("modifier"),
        code("status_code"),
        *[num(c) for c in ["work_rvu", "pe_rvu_nonfac", "pe_rvu_fac", "mp_rvu", "conversion_factor"]],
        (pl.col("nonfac_na_ind").str.strip_chars() == "NA").alias("nonfac_na"),
        (pl.col("fac_na_ind").str.strip_chars() == "NA").alias("fac_na"),
    ).drop("nonfac_na_ind", "fac_na_ind").with_columns(
        hcpcs_level2_description("hcpcs", "description").alias("description"))


def _col_index(cols: list[str], header: str) -> int:
    norm = [" ".join(c.upper().replace("-", "- ").split()) for c in cols]
    key = " ".join(header.upper().replace("-", "- ").split())
    hits = [i for i, c in enumerate(norm) if c == key]
    if len(hits) != 1:
        raise ValueError(f"RVU header changed: column {header!r} found {len(hits)} times in {cols}")
    return hits[0]


def _assert_header(cols: list[str], expect: dict[int, str]) -> None:
    for i, word in expect.items():
        got = cols[i].upper() if i < len(cols) else ""
        if word not in got:
            raise ValueError(f"RVU header changed: column {i} is {got!r}, expected to contain {word!r}")


def read_gpci(member) -> pl.DataFrame:
    raw = read_cms_csv(member, header_startswith="Medicare Administrative Contractor",
                       key_regex=r"^\d{5}$")
    c = raw.columns
    return raw.select(
        pl.col(c[0]).str.strip_chars().alias("carrier"),
        pl.col(c[1]).str.strip_chars().alias("state"),
        pl.col(c[2]).str.strip_chars().str.zfill(2).alias("locality"),
        pl.col(c[3]).str.strip_chars().str.replace_all(r"\*+$", "").alias("locality_name"),
        num(c[4]).alias("work_gpci"),
        num(c[5]).alias("pe_gpci"),
        num(c[6]).alias("mp_gpci"),
    )


def read_oppscap(member) -> pl.DataFrame:
    raw = read_cms_csv(member, header_startswith="HCPCS", key_regex=r"^[0-9A-Z]{5}$")
    c = raw.columns
    return raw.select(
        code(c[0]).alias("hcpcs"),
        pl.col(c[1]).str.strip_chars().fill_null("").alias("modifier"),
        pl.col(c[3]).str.strip_chars().alias("carrier"),
        pl.col(c[4]).str.strip_chars().str.zfill(2).alias("locality"),
        num(c[5]).alias("cap_fac"),
        num(c[6]).alias("cap_nonfac"),
    )


def compute_rates(rvu: pl.DataFrame, gpci: pl.DataFrame, cap: pl.DataFrame | None) -> pl.DataFrame:
    df = rvu.join(gpci, how="cross")
    payable = pl.col("status_code").is_in(list(PAYABLE_STATUS))
    nonfac = ((pl.col("work_rvu") * pl.col("work_gpci")
               + pl.col("pe_rvu_nonfac") * pl.col("pe_gpci")
               + pl.col("mp_rvu") * pl.col("mp_gpci")) * pl.col("conversion_factor"))
    fac = ((pl.col("work_rvu") * pl.col("work_gpci")
            + pl.col("pe_rvu_fac") * pl.col("pe_gpci")
            + pl.col("mp_rvu") * pl.col("mp_gpci")) * pl.col("conversion_factor"))
    df = df.with_columns(
        pl.when(payable & ~pl.col("nonfac_na")).then(nonfac).alias("pfs_nonfac"),
        pl.when(payable & ~pl.col("fac_na")).then(fac).alias("pfs_fac"),
    )
    if cap is not None and cap.height:
        df = df.join(cap, on=["hcpcs", "modifier", "carrier", "locality"], how="left")
        # The cap can only lower a rate that exists; a null (NA) setting stays null.
        df = df.with_columns(
            pl.when(pl.col("pfs_nonfac").is_not_null())
              .then(pl.min_horizontal("pfs_nonfac", "cap_nonfac")).alias("rate_nonfacility"),
            pl.when(pl.col("pfs_fac").is_not_null())
              .then(pl.min_horizontal("pfs_fac", "cap_fac")).alias("rate_facility"),
        ).with_columns(
            ((pl.col("rate_nonfacility") < pl.col("pfs_nonfac"))
             | (pl.col("rate_facility") < pl.col("pfs_fac"))).fill_null(False).alias("opps_cap_applied"),
        )
    else:
        df = df.with_columns(pl.col("pfs_nonfac").alias("rate_nonfacility"),
                             pl.col("pfs_fac").alias("rate_facility"),
                             pl.lit(False).alias("opps_cap_applied"))
    return df.with_columns(
        pl.col("rate_nonfacility").round(2), pl.col("rate_facility").round(2),
        pl.col("pfs_nonfac").round(2), pl.col("pfs_fac").round(2),
    ).drop([c for c in ("cap_fac", "cap_nonfac") if c in df.columns])


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = rel["members"]
    rvu_m, gpci_m = raw.member(m["rvu"]), raw.member(m["gpci"])
    cap_m = raw.member(m["oppscap"]) if m.get("oppscap") else None
    rvu, gpci = read_rvu(rvu_m), read_gpci(gpci_m)
    cap = read_oppscap(cap_m) if cap_m else None
    _check_ohio(gpci, ctx)
    df = compute_rates(rvu, gpci, cap)
    df = add_lineage(df, rvu_m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    members = [x for x in (rvu_m, gpci_m, cap_m) if x]
    df = df.with_columns(pl.lit(", ".join(x.lineage_name for x in members)).alias("source_file"))
    return ReleaseOutput(df=df, members=members, raw_files=[raw])


def _check_ohio(gpci: pl.DataFrame, ctx: Context) -> None:
    want = ctx.geography["mpfs_locality"]
    oh = gpci.filter(pl.col("state") == ctx.geography["state"])
    pairs = set(zip(oh["carrier"], oh["locality"]))
    if pairs != {(want["carrier"], want["locality"])}:
        ctx.warn(f"Ohio localities in GPCI file are {sorted(pairs)}; "
                 f"config/geography.yaml says {want}. Check before use (Spec §6).")
