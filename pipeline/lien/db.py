"""Read-only connection to data/meshkor.duckdb (made by build_duckdb)."""
from __future__ import annotations

from pathlib import Path

import duckdb

from ..common import config


class ReferenceDataMissing(Exception):
    """meshkor.duckdb is missing; run build_duckdb first."""


def path() -> Path:
    return config.data_paths().duckdb


def connect(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    p = Path(db_path) if db_path else path()
    if not p.exists():
        raise ReferenceDataMissing(f"{p} does not exist. Run: python backend\\manage.py build_duckdb")
    # Read-only and closed after each case, so build_duckdb can replace the file.
    return duckdb.connect(str(p), read_only=True)


def objects(con) -> set[str]:
    """Names of every table, view and macro in the database."""
    names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    names |= {r[0] for r in con.execute(
        "SELECT function_name FROM duckdb_functions() WHERE function_type IN ('table_macro', 'macro')").fetchall()}
    return names


def rows(con, sql: str, params: list | tuple = ()) -> list[dict]:
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
