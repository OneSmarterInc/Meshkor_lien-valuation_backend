"""Table 1 — ref_provider: NPPES Downloadable File V.2 (all states).

Spec §6 rules implemented here:
  * lazy scan (Polars scan_csv) — the main CSV is ~11 GB; never loaded whole
  * practice-location state / zip3 (not mailing) for the Ohio filter
  * primary taxonomy = the slot whose Primary Taxonomy Switch_N = 'Y';
    if none is flagged, slot 1 and primary_flag_missing = true
  * deactivated NPIs are kept, with the deactivation date (main file plus
    the monthly Deactivated NPI Report)
  * output partitioned by practice_state (Spec §4)

Lineage dates: effective_start = enumeration date, effective_end =
deactivation date (or 9999-12-31 if active / reactivated). A query "was this
NPI active on the date of service" is then a simple BETWEEN.

Column names are matched against the real header file (…_fileheader.csv)
before the scan starts; a missing column stops the load with a clear list.
"""
from __future__ import annotations

import csv
import io
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import polars as pl

from ..common.config import OPEN_END
from ..common.lineage import LINEAGE_COLS
from ..common.raw import Member
from ..runner import Context, ReleaseOutput

NPPES_START = date(2005, 5, 23)
TAXONOMY_SLOTS = 15

REQUIRED = {
    "npi": "NPI",
    "entity_type": "Entity Type Code",
    "replacement_npi": "Replacement NPI",
    "org_name": "Provider Organization Name (Legal Business Name)",
    "last_name": "Provider Last Name (Legal Name)",
    "first_name": "Provider First Name",
    "middle_name": "Provider Middle Name",
    "credential": "Provider Credential Text",
    "practice_address_1": "Provider First Line Business Practice Location Address",
    "practice_city": "Provider Business Practice Location Address City Name",
    "practice_state": "Provider Business Practice Location Address State Name",
    "practice_postal": "Provider Business Practice Location Address Postal Code",
    "practice_country": "Provider Business Practice Location Address Country Code (If outside U.S.)",
    "enumeration_date": "Provider Enumeration Date",
    "last_update_date": "Last Update Date",
    "deactivation_reason": "NPI Deactivation Reason Code",
    "deactivation_date": "NPI Deactivation Date",
    "reactivation_date": "NPI Reactivation Date",
}
OPTIONAL = {
    "is_subpart": "Is Organization Subpart",
    "parent_org_lbn": "Parent Organization LBN",
    "is_sole_proprietor": "Is Sole Proprietor",
}


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_columns(header: list[str]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    """Map logical names to the file's real header names (tolerant of case,
    spacing and punctuation changes). Returns (found, optional_found, missing)."""
    by_key = {_key(h): h for h in header}
    found, opt, missing = {}, {}, []
    for logical, name in REQUIRED.items():
        h = by_key.get(_key(name))
        if h is None:
            missing.append(name)
        else:
            found[logical] = h
    for logical, name in OPTIONAL.items():
        if (h := by_key.get(_key(name))) is not None:
            opt[logical] = h
    for i in range(1, TAXONOMY_SLOTS + 1):
        for logical, name in ((f"tax_{i}", f"Healthcare Provider Taxonomy Code_{i}"),
                              (f"sw_{i}", f"Healthcare Provider Primary Taxonomy Switch_{i}")):
            h = by_key.get(_key(name))
            if h is None:
                missing.append(name)
            else:
                found[logical] = h
    # "Other Provider Identifier" slots: type 06 = Medicare OSCAR/Certification
    # (the CCN). Used later by table 8 as a fallback match.
    i = 1
    while (h := by_key.get(_key(f"Other Provider Identifier_{i}"))) is not None:
        t = by_key.get(_key(f"Other Provider Identifier Type Code_{i}"))
        if t is None:
            break
        opt[f"oid_{i}"], opt[f"oidt_{i}"] = h, t
        i += 1
    return found, opt, missing


def read_header(member: Member) -> list[str]:
    first = member.read_head(200_000).decode("utf-8-sig", errors="replace").splitlines()[0]
    return next(csv.reader(io.StringIO(first)))


def _date(col: str) -> pl.Expr:
    return pl.col(col).str.strip_chars().str.to_date("%m/%d/%Y", strict=False)


def scan_raw(csv_path: Path, cols: dict[str, str], opt: dict[str, str]) -> pl.LazyFrame:
    """Lazy scan that keeps only the ~70 columns we use (of ~330)."""
    use = {**cols, **opt}
    return pl.scan_csv(csv_path, infer_schema=False, quote_char='"', encoding="utf8-lossy",
                       low_memory=True).select([pl.col(v).alias(k) for k, v in use.items()])


def transform(lf: pl.LazyFrame, opt: dict[str, str], snapshot: date) -> pl.LazyFrame:
    """All row-level rules. Applied per batch (see write()), so memory stays
    flat however large the file is."""
    s = {k: pl.col(k).str.strip_chars().replace("", None) for k in lf.collect_schema().names()}

    flagged = [pl.when(s[f"sw_{i}"] == "Y").then(s[f"tax_{i}"]) for i in range(1, TAXONOMY_SLOTS + 1)]
    primary_flagged = pl.coalesce(flagged)
    n_oid = len([k for k in opt if k.startswith("oid_")])
    ccn_ids = (pl.concat_list([pl.when(s[f"oidt_{i}"] == "06").then(s[f"oid_{i}"])
                               for i in range(1, n_oid + 1)]).list.drop_nulls().list.unique()
               if n_oid else pl.lit([], dtype=pl.List(pl.Utf8)))
    name_ind = pl.concat_str([s["last_name"], s["first_name"]], separator=", ", ignore_nulls=True)
    postal = s["practice_postal"].str.replace_all(r"[^0-9]", "")
    deact, react = _date("deactivation_date"), _date("reactivation_date")
    is_deactivated = deact.is_not_null() & (react.is_null() | (react < deact))

    out = lf.select(
        s["npi"].cast(pl.Int64).alias("npi"),
        s["entity_type"].cast(pl.Int8, strict=False).alias("entity_type"),
        s["replacement_npi"].cast(pl.Int64, strict=False).alias("replacement_npi"),
        pl.when(s["entity_type"] == "2").then(s["org_name"])
          .otherwise(name_ind.replace("", None)).alias("provider_name"),
        s["org_name"].alias("organization_name"),
        s["last_name"].alias("last_name"),
        s["first_name"].alias("first_name"),
        s["credential"].alias("credential"),
        s["practice_address_1"].alias("practice_address_1"),
        s["practice_city"].str.to_uppercase().alias("practice_city"),
        s["practice_state"].str.to_uppercase().alias("practice_state"),
        postal.str.slice(0, 5).alias("zip5"),
        postal.str.slice(0, 3).alias("zip3"),
        s["practice_country"].alias("practice_country"),
        pl.coalesce(primary_flagged, s["tax_1"]).alias("primary_taxonomy"),
        (primary_flagged.is_null() & s["tax_1"].is_not_null()).alias("primary_flag_missing"),
        pl.concat_list([s[f"tax_{i}"] for i in range(1, TAXONOMY_SLOTS + 1)]).list.drop_nulls().alias("all_taxonomies"),
        ccn_ids.alias("medicare_oscar_ids"),
        _date("enumeration_date").alias("enumeration_date"),
        _date("last_update_date").alias("last_update_date"),
        deact.alias("deactivation_date"),
        react.alias("reactivation_date"),
        s["deactivation_reason"].alias("deactivation_reason"),
        is_deactivated.alias("is_deactivated"),
        *[s[k].alias(k) for k in ("is_subpart", "parent_org_lbn", "is_sole_proprietor") if k in opt],
    )
    return out.with_columns(
        pl.coalesce("enumeration_date", pl.lit(NPPES_START)).alias("effective_start"),
        pl.when(pl.col("is_deactivated")).then(pl.col("deactivation_date"))
          .otherwise(pl.lit(OPEN_END)).alias("effective_end"),
        pl.lit(snapshot).alias("snapshot_date"),
    )


def read_deactivation_report(member: Member) -> pl.DataFrame:
    """Monthly Deactivated NPI Report: NPI + deactivation date. CSV or XLSX,
    with title rows above the header."""
    from ..common.tabular import member_rows
    rows = member_rows(member)
    hdr = next(i for i, r in enumerate(rows) if r and any(_key(c) == "npi" for c in r))
    names = [_key(c) for c in rows[hdr]]
    i_npi = names.index("npi")
    i_dt = next(j for j, n in enumerate(names) if "date" in n)
    recs = [(r[i_npi].strip(), r[i_dt].strip()) for r in rows[hdr + 1:]
            if len(r) > max(i_npi, i_dt) and r[i_npi].strip().isdigit()]
    df = pl.DataFrame(recs, schema={"npi": pl.Utf8, "d": pl.Utf8}, orient="row")
    return df.select(pl.col("npi").cast(pl.Int64),
                     pl.coalesce(pl.col("d").str.to_date("%m/%d/%Y", strict=False),
                                 pl.col("d").str.to_date("%Y-%m-%d", strict=False),
                                 pl.col("d").str.to_date("%Y%m%d", strict=False)).alias("report_deactivation_date"))


@dataclass
class NppesPlan:
    """What to load; executed batch by batch in write()."""
    raw: pl.LazyFrame
    opt: dict
    snapshot: date
    lineage: dict
    deactivations: pl.DataFrame | None


def apply_deactivation_report(lf: pl.LazyFrame, rep: pl.DataFrame) -> pl.LazyFrame:
    return (lf.join(rep.lazy(), on="npi", how="left")
              .with_columns(pl.coalesce("deactivation_date", "report_deactivation_date").alias("deactivation_date"))
              .with_columns(
                  (pl.col("deactivation_date").is_not_null()
                   & (pl.col("reactivation_date").is_null()
                      | (pl.col("reactivation_date") < pl.col("deactivation_date")))).alias("is_deactivated"))
              .with_columns(pl.when(pl.col("is_deactivated")).then(pl.col("deactivation_date"))
                            .otherwise(pl.lit(OPEN_END)).alias("effective_end"))
              .drop("report_deactivation_date"))


def run_plan(plan: NppesPlan, batch: pl.DataFrame) -> pl.DataFrame:
    lf = transform(batch.lazy(), plan.opt, plan.snapshot).with_columns(
        *[pl.lit(v).alias(k) for k, v in plan.lineage.items()])
    if plan.deactivations is not None:
        lf = apply_deactivation_report(lf, plan.deactivations)
    return lf.collect()


def load_release(rel: dict, ctx: Context) -> ReleaseOutput:
    raw = ctx.raw(rel["file"])
    main = raw.member(rel["members"]["main"])
    hdr_m = raw.members(rel["members"].get("header", "__none__"))
    header = read_header(hdr_m[0]) if hdr_m else read_header(main)
    cols, opt, missing = resolve_columns(header)
    if missing:
        raise ValueError("NPPES header is missing columns (V.2 layout change?): " + "; ".join(missing))
    if not any(k.startswith("oid_") for k in opt):
        ctx.warn("no 'Other Provider Identifier' columns; medicare_oscar_ids will be empty")
    snapshot = date.fromisoformat(str(rel["snapshot_date"]))
    csv_path = main.local_path(ctx.paths.work)
    members, raws, rep = [main], [raw], None
    if rel.get("deactivation_file"):
        try:
            draw = ctx.raw(rel["deactivation_file"])
            dm = next(m for m in draw.members("*") if m.name.lower().endswith((".xlsx", ".csv")))
            rep = read_deactivation_report(dm)
            members.append(dm)
            raws.append(draw)
        except FileNotFoundError as e:
            ctx.warn(f"deactivation report not found ({e}); using main-file dates only")
    plan = NppesPlan(raw=scan_raw(csv_path, cols, opt), opt=opt, snapshot=snapshot, deactivations=rep,
                     lineage={"source_file": main.lineage_name, "source_sha256": main.sha256,
                              "period": str(rel["period"])})
    return ReleaseOutput(df=plan, members=members, raw_files=raws)


def finalize(frames, ctx: Context):
    if len(frames) > 1:
        ctx.warn("several NPPES snapshots configured; loading only the newest")
    return max(frames, key=lambda p: p.snapshot)


BATCH_ROWS = 250_000


def write(plan: NppesPlan, ctx: Context):
    """Transform in batches of 250k rows (memory stays flat), write each
    batch as a Parquet part in data/work, then let DuckDB partition the parts
    by state into data/ref/ref_provider/state_part=XX/."""
    parts = ctx.paths.work / "ref_provider_parts"
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir(parents=True)
    rows = 0
    for i, batch in enumerate(plan.raw.collect_batches(chunk_size=BATCH_ROWS)):
        out = run_plan(plan, batch)
        out.write_parquet(parts / f"part-{i:05d}.parquet", compression="zstd")
        rows += out.height
        del out, batch
    final = ctx.paths.ref / "ref_provider"
    tmp = ctx.paths.ref / ".ref_provider.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    con = duckdb.connect()
    con.execute("SET preserve_insertion_order = false")
    w, t = (parts / "*.parquet").as_posix(), tmp.as_posix()   # forward slashes for DuckDB on Windows
    con.execute(f"""
        COPY (SELECT *,
                     -- Folder names must be safe on Windows: a 2-letter code, or XX for
                     -- blank / foreign / odd values (practice_state itself is unchanged).
                     CASE WHEN regexp_full_match(coalesce(practice_state, ''), '[A-Z]{{2}}')
                          THEN practice_state ELSE 'XX' END AS state_part
              FROM read_parquet('{w}'))
        TO '{t}' (FORMAT parquet, COMPRESSION zstd, PARTITION_BY (state_part))""")
    written = con.execute(f"SELECT count(*) FROM read_parquet('{t}/**/*.parquet', hive_partitioning = true)").fetchone()[0]
    n_dupe = con.execute(f"SELECT count(*) - count(DISTINCT npi) FROM read_parquet('{w}')").fetchone()[0]
    columns = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{w}')").fetchall()]
    con.close()
    if written != rows:
        raise ValueError(f"ref_provider: {rows:,} rows transformed but {written:,} read back from "
                         f"the state folders; output not replaced")
    if n_dupe:
        ctx.warn(f"{n_dupe:,} duplicate NPI rows in the NPPES file")
    missing = [c for c in LINEAGE_COLS if c not in columns]
    if missing:
        raise ValueError(f"ref_provider missing lineage columns {missing}")
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    shutil.rmtree(parts, ignore_errors=True)
    return final, rows, columns
