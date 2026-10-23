"""Table 4b — ref_ipps_hospital: per-hospital IPPS factors (final rule Impact
File) plus the national rates that apply to that hospital (Tables 1A–1D).

Spec §6: per CCN — wage index, operating base rate, capital rate, and the
hospital-specific adjustments in the impact file (IME, DSH, uncompensated
care, VBP and readmission proxies, COLA, GAF).

The national rates are not in the impact file; they come from the final
rule / correction notice and are set per release in config (`rates`). The
operating rate a hospital gets depends on (a) wage index > 1 or <= 1
(Table 1A or 1B) and (b) its quality-reporting and EHR status (the proxy
flags in the impact file).
"""
from __future__ import annotations

import re

import polars as pl

from ..common.lineage import add_lineage, as_date, num
from ..common.tabular import find_col, find_col_exact, read_cms_csv
from ..runner import Context, ReleaseOutput
from .hcris import SSA_STATE

SORT_BY = ["ccn", "effective_start"]

# impact-file column -> our name (numeric)
NUMERIC = {
    "WAGE INDEX": "wage_index", "COST OF LIVING ADJUSTMENT": "cola",
    "RESIDENT TO BED RATIO": "resident_to_bed_ratio", "BEDS": "beds",
    "TCHOP": "ime_operating", "TCHCP": "ime_capital", "DSHPCT": "dsh_patient_pct",
    "DSHOPP": "dsh_operating", "DSHCPP": "dsh_capital", "UCP_ADJ": "ucp_factor",
    "UCP PER CLAIM AMOUNT": "ucp_per_claim", "OPERATING CCR": "operating_ccr",
    "CAPITAL CCR": "capital_ccr", "HSP RATE": "hospital_specific_rate", "BILLS": "medicare_bills",
    "GAF": "gaf", "CAPITAL COST OF LIVING ADJUSTMENT": "capital_cola",
    "OUTFACT_F": "operating_outlier_pct", "PROXY VALUE BASED PURCHASING ADJUSTMENT FACTOR": "vbp_factor",
    "PROXY READMISSION ADJUSTMENT FACTOR": "hrrp_factor", "LOW VOLUME HOSPITAL ADJUSTMENT": "low_volume_factor",
}
TEXT = {
    "NAME": "hospital_name", "GEOGRAPHIC LABOR MARKET AREA": "cbsa_geographic",
    "PAYMENT LABOR MARKET AREA": "cbsa_payment", "FIPS COUNTY CODE": "fips_county",
    "URGEO": "urban_rural_geographic", "RECLASS": "reclass_status", "PROVIDER TYPE": "provider_type",
    "OWNERSHIP CONTROL TYPE": "ownership", "MDH FLAG": "mdh_flag",
}


def _col(df, name):
    c = find_col_exact(df, name)
    if c is None:
        # e.g. "FY 2027 Wage Index", "UCP Per Claim Amount" (not "... LY")
        cands = [x for x in df.columns if name in x.upper() and not x.upper().rstrip().endswith("LY")]
        if not cands:
            raise KeyError(f"impact file has no column like {name!r}")
        c = min(cands, key=len)
    return c


def _cmi_col(df) -> str:
    """Latest transfer-adjusted CMI column: CMIV44 (FY2027), CMIV43 (FY2026), CMIV42 (FY2025)."""
    cands = [(int(m.group(1)), c) for c in df.columns
             if (m := re.fullmatch(r"CMIV(\d+)", c.strip().upper()))]
    if not cands:
        raise KeyError("impact file has no CMIVnn column")
    return max(cands)[1]


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["impact"])
    delim = "\t" if m.name.lower().endswith(".txt") else ","
    df = read_cms_csv(m, header_startswith="Provider Number", encoding="latin-1", delimiter=delim,
                      key_regex=r"^[0-9A-Z]{6}$")
    exprs = [pl.col(df.columns[0]).str.strip_chars().alias("ccn")]
    exprs += [num(_col(df, k)).alias(v) for k, v in NUMERIC.items()]
    exprs.append(num(_cmi_col(df)).alias("case_mix_index"))
    exprs += [pl.col(_col(df, k)).str.strip_chars().replace("", None).alias(v) for k, v in TEXT.items()]
    exprs += [(num(_col(df, "PROXY QUALITY REDUCTION")) == 1).alias("quality_reduction"),
              (num(_col(df, "PROXY EHR REDUCTION")) == 1).alias("ehr_reduction")]
    out = df.select(exprs)

    r = rel["rates"]
    hi, lo = r["operating_wi_gt_1"], r["operating_wi_le_1"]

    def pick(table: dict, part: str) -> pl.Expr:
        q, e = pl.col("quality_reduction"), pl.col("ehr_reduction")
        return (pl.when(~q & ~e).then(table["full"][part])
                  .when(~q & e).then(table["no_ehr"][part])
                  .when(q & ~e).then(table["no_quality"][part])
                  .otherwise(table["no_quality_no_ehr"][part]))

    gt1 = pl.col("wage_index") > 1
    out = out.with_columns(
        pl.col("ccn").str.slice(0, 2).replace_strict(SSA_STATE, default=None).alias("state"),
        pl.col("cola").fill_null(1.0), pl.col("vbp_factor").fill_null(1.0),
        pl.col("hrrp_factor").fill_null(1.0), pl.col("low_volume_factor").fill_null(1.0),
        *[pl.col(c).fill_null(0.0) for c in ("ime_operating", "ime_capital", "dsh_operating",
                                              "dsh_capital", "ucp_per_claim")],
        pl.when(gt1).then(pick(hi, "labor")).otherwise(pick(lo, "labor")).alias("operating_labor_rate"),
        pl.when(gt1).then(pick(hi, "nonlabor")).otherwise(pick(lo, "nonlabor")).alias("operating_nonlabor_rate"),
        pl.lit(float(r["capital_federal_rate"])).alias("capital_federal_rate"),
        pl.lit(str(rel["period"])).alias("fiscal_year"),
    ).with_columns(
        # Wage-adjusted operating base rate per case (before the DRG weight):
        # labor x wage index + nonlabor x COLA (COLA is 1 outside AK/HI).
        (pl.col("operating_labor_rate") * pl.col("wage_index")
         + pl.col("operating_nonlabor_rate") * pl.col("cola")).round(2).alias("operating_base_rate"),
        (pl.col("capital_federal_rate") * pl.col("gaf")).round(2).alias("capital_base_rate"),
    )
    missing_wi = out.filter(pl.col("wage_index").is_null()).height
    if missing_wi:
        ctx.warn(f"{missing_wi} hospitals have no wage index")
    out = add_lineage(out, m, effective_start=as_date(rel["effective_start"]),
                      effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=out, members=[m], raw_files=[raw])
