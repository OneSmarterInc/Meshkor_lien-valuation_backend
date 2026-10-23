"""Table 9 — ref_code_specialty: which specialties plausibly perform a code
(the ghost-rate filter, Spec §6).

CMS does not publish this crosswalk, so we build it from "Medicare Physician
& Other Practitioners — by Provider and Service" (one row per NPI x HCPCS x
place of service):

  1. Sum Tot_Srvcs per (hcpcs, Medicare specialty = Rndrng_Prvdr_Type).
  2. A specialty plausibly performs a code if it has at least `min_share` of
     the national services for that code, or is in the top `top_n`.
  3. Map specialty to NPPES taxonomy: join each rendering NPI to its primary
     taxonomy in ref_provider, so each row is (hcpcs, specialty, taxonomy).

HCPCS descriptions are not stored (CPT text is AMA-licensed, Spec §10).
The 3 GB CSV is read lazily and aggregated in streaming mode.
"""
from __future__ import annotations

import polars as pl

from ..common.lineage import add_lineage, as_date
from ..runner import Context, ReleaseOutput

SORT_BY = ["hcpcs", "specialty_rank", "medicare_specialty", "taxonomy"]

COLS = {"Rndrng_NPI": "npi", "Rndrng_Prvdr_Type": "medicare_specialty",
        "HCPCS_Cd": "hcpcs", "Tot_Srvcs": "services", "Tot_Benes": "beneficiaries"}


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    m = raw.member(rel["members"]["utilization"])
    min_share = float(rel.get("min_share", 0.01))
    top_n = int(rel.get("top_n", 10))
    path = m.local_path(ctx.paths.work)

    head = pl.read_csv(path, n_rows=0, infer_schema=False)
    missing = [c for c in COLS if c not in head.columns]
    if missing:
        raise ValueError(f"{m.lineage_name}: columns not found: {missing}")

    lf = (pl.scan_csv(path, infer_schema=False, encoding="utf8-lossy")
          .select([pl.col(k).alias(v) for k, v in COLS.items()])
          .with_columns(
              pl.col("npi").str.strip_chars().cast(pl.Int64, strict=False),
              pl.col("hcpcs").str.strip_chars().str.to_uppercase(),
              pl.col("medicare_specialty").str.strip_chars(),
              pl.col("services").cast(pl.Float64, strict=False),
              pl.col("beneficiaries").cast(pl.Float64, strict=False)))

    prov = ctx.paths.ref / "ref_provider"
    if prov.exists():
        tax = (pl.scan_parquet(str(prov / "**" / "*.parquet"), hive_partitioning=True)
               .select("npi", pl.col("primary_taxonomy").alias("taxonomy")))
        lf = lf.join(tax, on="npi", how="left")
    else:
        ctx.warn("ref_provider not built yet; taxonomy is empty (run load_ref ref_provider first)")
        lf = lf.with_columns(pl.lit(None, dtype=pl.Utf8).alias("taxonomy"))

    # (hcpcs, specialty, taxonomy) level
    t = (lf.group_by("hcpcs", "medicare_specialty", "taxonomy")
         .agg(pl.col("services").sum().alias("services"),
              pl.col("npi").n_unique().alias("providers"))
         .collect(engine="streaming"))

    spec = (t.group_by("hcpcs", "medicare_specialty")
            .agg(pl.col("services").sum().alias("specialty_services"),
                 pl.col("providers").sum().alias("specialty_providers")))
    spec = spec.with_columns(
        pl.col("specialty_services").sum().over("hcpcs").alias("code_total_services"),
        pl.col("specialty_services").rank(method="min", descending=True).over("hcpcs")
          .cast(pl.Int32).alias("specialty_rank"),
    ).with_columns(
        (pl.col("specialty_services") / pl.col("code_total_services")).round(6).alias("specialty_share"),
    ).with_columns(
        ((pl.col("specialty_share") >= min_share) | (pl.col("specialty_rank") <= top_n)).alias("plausible"),
    )
    df = t.join(spec, on=["hcpcs", "medicare_specialty"], how="left").with_columns(
        (pl.col("services") / pl.col("specialty_services")).round(6).alias("taxonomy_share_in_specialty"),
        (pl.col("services") / pl.col("code_total_services")).round(6).alias("taxonomy_share_of_code"),
        pl.lit(int(rel["data_year"])).alias("data_year"),
        pl.lit(min_share).alias("rule_min_share"),
        pl.lit(top_n).alias("rule_top_n"),
    )
    unmatched = df.filter(pl.col("taxonomy").is_null())["services"].sum() or 0
    total = df["services"].sum() or 1
    if unmatched:
        ctx.warn(f"{unmatched / total:.1%} of services have an NPI not found in ref_provider (taxonomy empty)")
    df = add_lineage(df, m, effective_start=as_date(rel["effective_start"]),
                     effective_end=as_date(rel["effective_end"]), period=str(rel["period"]))
    return ReleaseOutput(df=df, members=[m], raw_files=[raw])
