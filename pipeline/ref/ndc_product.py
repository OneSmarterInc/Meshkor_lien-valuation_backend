"""Table 21 — ref_ndc_product: FDA National Drug Code directory, product file
(product.txt, tab-separated). One row per product (labeler-product NDC)."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..common.tabular import read_csv_fast
from ..runner import Context, ReleaseOutput

SORT_BY = ["product_ndc"]
COLS = {
    "PRODUCTID": "product_id", "PRODUCTNDC": "product_ndc", "PRODUCTTYPENAME": "product_type",
    "PROPRIETARYNAME": "proprietary_name", "PROPRIETARYNAMESUFFIX": "proprietary_name_suffix",
    "NONPROPRIETARYNAME": "nonproprietary_name", "DOSAGEFORMNAME": "dosage_form", "ROUTENAME": "route",
    "STARTMARKETINGDATE": "start_marketing_date", "ENDMARKETINGDATE": "end_marketing_date",
    "MARKETINGCATEGORYNAME": "marketing_category", "APPLICATIONNUMBER": "application_number",
    "LABELERNAME": "labeler_name", "SUBSTANCENAME": "substance_name",
    "ACTIVE_NUMERATOR_STRENGTH": "active_strength", "ACTIVE_INGRED_UNIT": "active_unit",
    "PHARM_CLASSES": "pharm_classes", "DEASCHEDULE": "dea_schedule", "NDC_EXCLUDE_FLAG": "ndc_exclude_flag",
}


def read_fda(member, cols: dict) -> pl.DataFrame:
    df = read_csv_fast(member, separator="\t", quote_char=None, encoding="utf8-lossy")
    up = {c.upper(): c for c in df.columns}
    missing = [k for k in cols if k not in up]
    if missing:
        raise ValueError(f"{member.lineage_name}: FDA columns not found: {missing}")
    df = df.select([pl.col(up[k]).str.strip_chars().replace("", None).alias(v) for k, v in cols.items()])
    for c in [v for v in df.columns if v.endswith("_date")]:
        df = df.with_columns(pl.col(c).str.strptime(pl.Date, "%Y%m%d", strict=False))
    return df


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["product"])
    df = add_lineage(read_fda(mem, COLS), mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
