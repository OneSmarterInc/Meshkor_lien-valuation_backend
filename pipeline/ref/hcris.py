"""Table 7 — ref_hcris: hospital cost reports (CMS-2552-10), one row per
cost report, with the hospital-wide cost-to-charge ratio (Spec §6).

Inputs per fiscal-year zip (HOSP10FYyyyy.zip): RPT and NMRC CSVs with no
header row; column order from HCRIS_TABLE_DESCRIPTIONS_AND_SQL.txt.

Cells used are set in config/sources.yaml (ref_hcris.cells). The NMRC file
is large, so it is extracted once to data/work/ and scanned lazily, keeping
only the worksheet/line/column cells we need.

Known limit (Spec §6): the ratio is hospital-wide. Department-level ratios
need Worksheet C line detail; not built in Step 1.
"""
from __future__ import annotations

import polars as pl

from ..runner import Context, ReleaseOutput

SORT_BY = ["ccn", "fy_begin"]

RPT_COLS = ["RPT_REC_NUM", "PRVDR_CTRL_TYPE_CD", "PRVDR_NUM", "NPI", "RPT_STUS_CD",
            "FY_BGN_DT", "FY_END_DT", "PROC_DT", "INITL_RPT_SW", "LAST_RPT_SW",
            "TRNSMTL_NUM", "FI_NUM", "ADR_VNDR_CD", "FI_CREAT_DT", "UTIL_CD", "NPR_DT",
            "SPEC_IND", "FI_RCPT_DT"]
NMRC_COLS = ["RPT_REC_NUM", "WKSHT_CD", "LINE_NUM", "CLMN_NUM", "ITM_VAL_NUM"]

# HCRIS_STATE_CODES.csv (SSA state codes; the first two CCN digits).
SSA_STATE = {
    "01": "AL", "02": "AK", "03": "AZ", "04": "AR", "05": "CA", "55": "CA", "75": "CA",
    "06": "CO", "07": "CT", "08": "DE", "09": "DC", "10": "FL", "68": "FL", "69": "FL",
    "11": "GA", "12": "HI", "13": "ID", "14": "IL", "78": "IL", "15": "IN", "16": "IA",
    "76": "IA", "17": "KS", "70": "KS", "18": "KY", "19": "LA", "71": "LA", "20": "ME",
    "21": "MD", "80": "MD", "22": "MA", "23": "MI", "24": "MN", "77": "MN", "25": "MS",
    "26": "MO", "27": "MT", "28": "NE", "29": "NV", "30": "NH", "31": "NJ", "32": "NM",
    "33": "NY", "34": "NC", "35": "ND", "36": "OH", "72": "OH", "37": "OK", "38": "OR",
    "39": "PA", "73": "PA", "40": "PR", "41": "RI", "42": "SC", "43": "SD", "44": "TN",
    "45": "TX", "67": "TX", "74": "TX", "46": "UT", "47": "VT", "48": "VI", "49": "VA",
    "50": "WA", "51": "WV", "52": "WI", "53": "WY", "64": "AS", "65": "GU",
}
# HCRIS_FACILITY_NUMBERING.csv (last four CCN digits) — hospital ranges only.
FACILITY_RANGES = [
    (1, 879, "short_term_acute"), (1300, 1399, "critical_access"),
    (2000, 2299, "long_term_care"), (3025, 3099, "rehabilitation"),
    (3300, 3399, "childrens"), (4000, 4499, "psychiatric"),
]
STATUS = {"1": "as_submitted", "2": "settled_no_audit", "3": "settled_audit",
          "4": "reopened", "5": "amended"}


def facility_type_expr(ccn: pl.Expr) -> pl.Expr:
    tail = ccn.str.slice(2, 4).cast(pl.Int32, strict=False)
    e = pl.lit("other")
    for lo, hi, name in reversed(FACILITY_RANGES):
        e = pl.when(tail.is_between(lo, hi)).then(pl.lit(name)).otherwise(e)
    return e


def _dt(c: str) -> pl.Expr:
    s = pl.col(c).str.strip_chars()
    return pl.coalesce(s.str.to_date("%m/%d/%Y", strict=False), s.str.to_date("%Y-%m-%d", strict=False))


def read_rpt(member) -> pl.DataFrame:
    import io
    df = pl.read_csv(io.BytesIO(member.read_bytes()), has_header=False, new_columns=RPT_COLS,
                     schema_overrides={c: pl.Utf8 for c in RPT_COLS}, truncate_ragged_lines=True)
    return df.select(
        pl.col("RPT_REC_NUM").cast(pl.Int64).alias("rpt_rec_num"),
        pl.col("PRVDR_NUM").str.strip_chars().str.zfill(6).alias("ccn"),
        pl.col("NPI").str.strip_chars().cast(pl.Int64, strict=False).alias("npi"),
        pl.col("PRVDR_CTRL_TYPE_CD").str.strip_chars().alias("provider_control_type"),
        pl.col("RPT_STUS_CD").str.strip_chars().alias("report_status_code"),
        _dt("FY_BGN_DT").alias("fy_begin"),
        _dt("FY_END_DT").alias("fy_end"),
        _dt("PROC_DT").alias("processed_date"),
        pl.col("UTIL_CD").str.strip_chars().alias("medicare_utilization"),
    )


def read_cells(nmrc_path, cells: dict) -> pl.DataFrame:
    lf = pl.scan_csv(nmrc_path, has_header=False, new_columns=NMRC_COLS, infer_schema=False)
    conds = None
    for spec in cells.values():
        c = ((pl.col("WKSHT_CD") == spec["wksht"]) & (pl.col("LINE_NUM") == spec["line"])
             & (pl.col("CLMN_NUM") == spec["col"]))
        conds = c if conds is None else conds | c
    hit = lf.filter(conds).collect()
    out = None
    for name, spec in cells.items():
        part = hit.filter((pl.col("WKSHT_CD") == spec["wksht"]) & (pl.col("LINE_NUM") == spec["line"])
                          & (pl.col("CLMN_NUM") == spec["col"])).select(
            pl.col("RPT_REC_NUM").cast(pl.Int64).alias("rpt_rec_num"),
            pl.col("ITM_VAL_NUM").cast(pl.Float64, strict=False).alias(name))
        part = part.group_by("rpt_rec_num").agg(pl.col(name).sum())
        out = part if out is None else out.join(part, on="rpt_rec_num", how="full", coalesce=True)
    return out if out is not None else pl.DataFrame({"rpt_rec_num": []}, schema={"rpt_rec_num": pl.Int64})


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    rpt_m, nmrc_m = raw.member(rel["members"]["rpt"]), raw.member(rel["members"]["nmrc"])
    rpt = read_rpt(rpt_m)
    cells = read_cells(nmrc_m.local_path(ctx.paths.work), ctx.spec["cells"])
    df = rpt.join(cells, on="rpt_rec_num", how="left").with_columns(
        pl.col("ccn").str.slice(0, 2).replace_strict(SSA_STATE, default=None).alias("state"),
        facility_type_expr(pl.col("ccn")).alias("facility_type"),
        pl.col("report_status_code").replace_strict(STATUS, default=None).alias("report_status"),
        pl.when(pl.col("total_charges") > 0)
          .then(pl.col("total_costs") / pl.col("total_charges")).alias("cost_to_charge_ratio"),
        pl.lit(str(rel["period"])).alias("hcris_file_year"),
        pl.col("fy_begin").alias("effective_start"),
        pl.col("fy_end").alias("effective_end"),
        pl.lit(f"{rpt_m.lineage_name}, {nmrc_m.lineage_name}").alias("source_file"),
        pl.lit(rpt_m.sha256).alias("source_sha256"),
        pl.lit(str(rel["period"])).alias("period"),
    )
    odd = df.filter((pl.col("cost_to_charge_ratio") < 0.05) | (pl.col("cost_to_charge_ratio") > 1.5))
    if odd.height:
        ctx.warn(f"{rel['period']}: {odd.height} reports with cost-to-charge ratio outside 0.05–1.5")
    return ReleaseOutput(df=df, members=[rpt_m, nmrc_m], raw_files=[raw])


def finalize(frames, ctx: Context) -> pl.DataFrame:
    """A hospital can file two reports in one year that cover different
    periods (fiscal-year change, change of ownership) — both are valid and
    kept. Two reports for the SAME period (same CCN and FY begin date, e.g.
    the same report in two yearly files) are duplicates: `is_primary` marks
    the highest-status, latest-processed one."""
    df = pl.concat(frames, how="diagonal_relaxed")
    df = df.with_columns(pl.col("fy_end").dt.year().alias("fy_end_year"))
    df = (df.sort(["ccn", "fy_begin", "report_status_code", "processed_date", "fy_end"],
                  descending=[False, False, True, True, True], nulls_last=True)
            .with_columns((pl.int_range(pl.len()).over("ccn", "fy_begin") == 0).alias("is_primary")))
    n_dup = df.filter(~pl.col("is_primary")).height
    if n_dup:
        ctx.warn(f"{n_dup} duplicate reports for the same hospital and period (is_primary = false)")
    multi = df.filter(pl.col("is_primary")).group_by("ccn", "fy_end_year").len().filter(pl.col("len") > 1)
    if multi.height:
        ctx.warn(f"{multi.height} hospital-years have 2+ reports for different periods "
                 "(fiscal-year change or change of ownership); all kept")
    return df
