"""Writing outputs: ZSTD Parquet (Spec §3.3) plus a JSON manifest per table.

The manifest is the pipeline's own record of what it loaded. The Django
backend copies it into PostgreSQL; verify_step1 and the README source list
are built from it, so they work even without the database.
"""
from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from .config import Paths
from .lineage import LINEAGE_COLS


@dataclass
class SourceRecord:
    period: str
    file: str
    sha256: str
    size_bytes: int
    page: str | None
    members: list[str] = field(default_factory=list)
    rows: int = 0


@dataclass
class TableResult:
    table: str
    output: str
    rows: int
    columns: list[str]
    sources: list[SourceRecord]
    started_at: str
    finished_at: str
    seconds: float
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return asdict(self)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_lineage(columns: list[str], table: str) -> None:
    missing = [c for c in LINEAGE_COLS if c not in columns]
    if missing:
        raise ValueError(f"{table}: missing lineage columns {missing}")


def write_table(df: pl.DataFrame, paths: Paths, table: str, *,
                partition_by: str | None = None, sort_by: list[str] | None = None) -> Path:
    """Write atomically: build in a temp location, then swap."""
    check_lineage(df.columns, table)
    if sort_by:
        df = df.sort(sort_by, nulls_last=True)
    if partition_by:
        final = paths.ref / table
        tmp = paths.ref / f".{table}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for (key,), part in df.group_by([partition_by], maintain_order=True):
            d = tmp / f"{partition_by}={key if key is not None else '__NULL__'}"
            d.mkdir()
            part.drop(partition_by).write_parquet(d / "part-0.parquet", compression="zstd")
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)
        return final
    final = paths.ref / f"{table}.parquet"
    tmp = final.with_suffix(".parquet.tmp")
    df.write_parquet(tmp, compression="zstd", statistics=True)
    tmp.replace(final)
    return final


def write_manifest(paths: Paths, result: TableResult) -> Path:
    p = paths.manifests / f"{result.table}.json"
    p.write_text(json.dumps(result.to_json(), indent=2, default=str), encoding="utf-8")
    return p


def read_manifests(paths: Paths) -> dict[str, dict]:
    out = {}
    for p in sorted(paths.manifests.glob("*.json")):
        out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        self.started = utcnow()
        return self

    def __exit__(self, *exc):
        self.seconds = round(time.perf_counter() - self.t0, 2)
        self.finished = utcnow()
