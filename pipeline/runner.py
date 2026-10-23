"""Run table loaders. Plain Python: `python -m pipeline.runner ref_mpfs`.

Each loader module exposes:
    load_release(release: dict, ctx: Context) -> ReleaseOutput
and optionally:
    finalize(frames: list[pl.DataFrame], ctx) -> pl.DataFrame   (dedupe etc.)
    write(df, ctx) -> Path                                      (custom writer)
    PARTITION_BY, SORT_BY
"""
from __future__ import annotations

import argparse
import importlib
import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl

from .common import config
from .common.output import (SourceRecord, check_lineage, TableResult, Timer, write_manifest,
                            write_table)
from .common.raw import Member, RawFile, RawFileMissing

log = logging.getLogger("meshkor.pipeline")

TABLE_ORDER = [
    "ref_provider", "ref_mpfs", "ref_mpfs_locality", "ref_opps", "ref_asc",
    "ref_ncci_ptp", "ref_mue", "ref_hcris", "ref_anesthesia_cf", "ref_anesthesia_base_units", "ref_ipps_drg", "ref_ipps_hospital",
    "ref_clfs", "ref_dmepos", "ref_dmepos_rural_zip", "ref_ambulance", "ref_zip_locality",
    "ref_ccn_npi", "ref_code_specialty",   # need ref_provider first
    "ref_asp", "ref_ndc_hcpcs",          # Table 10
    "ref_hcpcs_code",
    # Spec §11 (own definition of done)
    "ref_geo", "ref_geo_zcta_county", "ref_quality_hospital", "ref_quality_measure", "ref_quality_asc",
    "ref_ownership", "ref_chow", "ref_chow_npi", "ref_nadac", "ref_ndc_product", "ref_ndc_package",
]


@dataclass
class Context:
    paths: config.Paths
    table: str
    spec: dict
    geography: dict
    warnings: list[str] = field(default_factory=list)

    def raw(self, rel_path: str | list[str]) -> RawFile:
        """`file:` may be one path or a list of choices (first one found wins),
        e.g. the CMS zip or the spreadsheet taken out of it."""
        choices = [rel_path] if isinstance(rel_path, str) else list(rel_path)
        for c in choices:
            try:
                return RawFile(self.paths.raw, c)
            except RawFileMissing:
                continue
        raise RawFileMissing("raw file not found: " + " or ".join(f"data/raw/{c}" for c in choices))

    def warn(self, msg: str) -> None:
        log.warning("%s: %s", self.table, msg)
        self.warnings.append(msg)


@dataclass
class ReleaseOutput:
    df: pl.DataFrame | pl.LazyFrame
    members: list[Member]
    raw_files: list[RawFile]


class TableNotConfigured(KeyError):
    pass


def run_table(table: str, *, data_root: str | None = None, periods: list[str] | None = None) -> TableResult:
    paths = config.data_paths(data_root)
    all_specs = config.sources()
    if table not in all_specs:
        raise TableNotConfigured(f"{table} not in config/sources.yaml")
    spec = all_specs[table]
    mod = importlib.import_module(f"pipeline.ref.{spec['loader']}")
    ctx = Context(paths=paths, table=table, spec=spec, geography=config.geography())

    frames: list[pl.DataFrame] = []
    sources: list[SourceRecord] = []
    skipped: list[str] = []
    # STREAM tables (ref_mpfs: ~2M rows per quarter) write each release to its own
    # file at once, so memory holds one release, not all of them.
    stream = getattr(mod, "STREAM", False)
    stream_dir = paths.ref / f".{table}.tmp"
    if stream:
        shutil.rmtree(stream_dir, ignore_errors=True)
        stream_dir.mkdir(parents=True)
    stream_rows, stream_cols, part, stream_schema = 0, [], 0, None
    with Timer() as t:
        for rel in spec["releases"]:
            if periods and str(rel["period"]) not in periods:
                continue
            label = f"{rel['period']}" + (f"/{rel['setting']}" if rel.get("setting") else "")
            try:
                out: ReleaseOutput = mod.load_release(rel, ctx)
            except RawFileMissing as e:
                skipped.append(f"{label}: {e}")
                ctx.warn(f"skipped {label} — {e}")
                continue
            if stream:
                check_lineage(out.df.columns, table)
                d = out.df.sort(mod.SORT_BY, nulls_last=True) if getattr(mod, "SORT_BY", None) else out.df
                if stream_schema is None:
                    stream_schema = d.schema
                else:   # same column types in every file (e.g. an all-null column)
                    d = d.cast({c: dt for c, dt in stream_schema.items() if c in d.columns and d.schema[c] != dt})
                d.write_parquet(stream_dir / f"part-{part:03d}.parquet", compression="zstd", statistics=True)
                part += 1
                stream_rows += out.df.height
                stream_cols = stream_cols or list(out.df.columns)
                frames.append(None)
                del d
            else:
                frames.append(out.df)
            for rf in out.raw_files:
                sources.append(SourceRecord(
                    period=label, file=rf.rel_path, sha256=rf.sha256,
                    size_bytes=rf.size_bytes, page=rel.get("page"),
                    members=sorted({m.name for m in out.members if m.raw.rel_path == rf.rel_path}),
                    rows=out.df.height if isinstance(out.df, pl.DataFrame) and len(out.raw_files) == 1 else 0))
            if stream:
                out = None   # free this release before the next one loads
        if not frames:
            if stream:
                shutil.rmtree(stream_dir, ignore_errors=True)
            raise RawFileMissing(f"{table}: no raw files found. Skipped: {skipped}")
        if stream:
            final = paths.ref / table
            shutil.rmtree(final, ignore_errors=True)
            (paths.ref / f"{table}.parquet").unlink(missing_ok=True)   # old single-file output
            stream_dir.rename(final)
            out_path, rows, columns = final, stream_rows, stream_cols
        else:
            df = mod.finalize(frames, ctx) if hasattr(mod, "finalize") else pl.concat(frames, how="diagonal_relaxed")
            if hasattr(mod, "write"):
                # Large tables (NPPES) stream to disk and report their own count.
                out_path, rows, columns = mod.write(df, ctx)
            else:
                out_path = write_table(df, paths, table,
                                       partition_by=getattr(mod, "PARTITION_BY", None),
                                       sort_by=getattr(mod, "SORT_BY", None))
                rows, columns = df.height, list(df.columns)
    result = TableResult(
        table=table, output=str(Path(out_path).relative_to(paths.root)), rows=rows,
        columns=columns, sources=sources, started_at=t.started,
        finished_at=t.finished, seconds=t.seconds, warnings=ctx.warnings, skipped=skipped)
    write_manifest(paths, result)
    log.info("%s: %s rows -> %s (%.1fs)", table, f"{rows:,}", out_path, t.seconds)
    return result


def configured_tables() -> list[str]:
    specs = config.sources()
    return [t for t in TABLE_ORDER if t in specs] + [t for t in specs if t not in TABLE_ORDER]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Load MeshKor Step 1 reference tables")
    ap.add_argument("tables", nargs="+", help="table names or 'all'")
    ap.add_argument("--period", action="append", help="only this period (repeatable)")
    ap.add_argument("--data-root")
    a = ap.parse_args(argv)
    tables = configured_tables() if a.tables == ["all"] else a.tables
    failed = 0
    for t in tables:
        try:
            run_table(t, data_root=a.data_root, periods=a.period)
        except RawFileMissing as e:
            log.warning("%s", e)
        except Exception:  # noqa: BLE001
            failed += 1
            log.exception("%s failed", t)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
