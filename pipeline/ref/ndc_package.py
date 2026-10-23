"""Table 21 — ref_ndc_package: FDA NDC directory, package file (package.txt).
`ndc11` is the 11-digit 5-4-2 form of the package NDC (each part padded with
leading zeros), the form NADAC and claims use. Join: ref_nadac.ndc = ndc11."""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..runner import Context, ReleaseOutput
from .ndc_product import read_fda

SORT_BY = ["ndc11"]
COLS = {
    "PRODUCTID": "product_id", "PRODUCTNDC": "product_ndc", "NDCPACKAGECODE": "package_ndc",
    "PACKAGEDESCRIPTION": "package_description", "STARTMARKETINGDATE": "start_marketing_date",
    "ENDMARKETINGDATE": "end_marketing_date", "NDC_EXCLUDE_FLAG": "ndc_exclude_flag",
    "SAMPLE_PACKAGE": "sample_package",
}


def ndc11(col: str) -> pl.Expr:
    """'0002-0152-01' -> '00002015201' (labeler 5, product 4, package 2)."""
    parts = pl.col(col).str.split("-")
    return pl.when(parts.list.len() == 3).then(pl.concat_str([
        parts.list.get(0).str.zfill(5), parts.list.get(1).str.zfill(4), parts.list.get(2).str.zfill(2)]))


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    mem = raw.member(rel["members"]["package"])
    df = read_fda(mem, COLS).with_columns(ndc11("package_ndc").alias("ndc11"),
                                          (pl.col("sample_package") == "Y").alias("sample_package"))
    df = add_lineage(df, mem, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[mem], raw_files=[raw])
