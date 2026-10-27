"""Build data/meshkor.duckdb: copy every ref_* Parquet into a DuckDB table
(decision: tables, not views), then create the views/macros in sql/views.sql.

Parquet stays the main copy (Spec §3.3); the DuckDB file can always be
rebuilt from it. The build writes to a temp file and swaps it in, so a
reader never sees a half-built database. Only this command writes DuckDB.
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path

import duckdb

from .common import config

log = logging.getLogger("meshkor.duckdb")
SQL_DIR = config.PROJECT_ROOT / "sql"


def _parquet_sources(paths: config.Paths) -> dict[str, str]:
    out = {}
    for p in sorted(paths.ref.iterdir()):
        if p.name.startswith((".", "_")):
            continue
        if p.is_file() and p.suffix == ".parquet":
            out[p.stem] = f"read_parquet('{p.as_posix()}')"
        elif p.is_dir() and any(p.rglob("*.parquet")):
            out[p.name] = f"read_parquet('{p.as_posix()}/**/*.parquet', hive_partitioning = true, union_by_name = true)"
    return out


def _geo_rows(geo: dict) -> list[tuple]:
    lo, hi = geo["ohio_zip3"]["range"]
    rows = [(f"{z:03d}", "ohio", geo["state"], "Ohio") for z in range(lo, hi + 1)]
    for b in geo["border_zip3"]:
        for st in str(b["state"]).split(","):
            for z in b["zip3"]:
                rows.append((z, "border", st.strip(), b["metro"]))
    return rows


RECLASS_CATEGORIES = {"closed", "not_acute", "not_hospital", "federal"}


def _reclass_rows() -> list[tuple]:
    """config/ccn_npi_reclass.csv: reviewed Ohio hospital NPIs that cannot have an
    acute-care CCN (closed, outpatient site, post-acute, behavioral, not a hospital).
    Columns: npi, category, reason, source. Missing file = no rows."""
    import csv
    path = Path(os.environ.get("MESHKOR_CONFIG_DIR", config.PROJECT_ROOT / "config")) / "ccn_npi_reclass.csv"
    if not path.exists():
        return []
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            npi, cat = (r.get("npi") or "").strip(), (r.get("category") or "").strip().lower()
            if not npi:
                continue
            if cat not in RECLASS_CATEGORIES:
                raise ValueError(f"{path.name}: npi {npi}: category {cat!r} not in {sorted(RECLASS_CATEGORIES)}")
            if not (r.get("reason") or "").strip():
                raise ValueError(f"{path.name}: npi {npi}: reason is required")
            rows.append((npi, cat, r["reason"].strip(), (r.get("source") or "").strip()))
    return rows


def statements() -> list[tuple[str, str]]:
    text = (SQL_DIR / "views.sql").read_text(encoding="utf-8")
    parts = re.split(r"^-- @stmt\s+", text, flags=re.M)[1:]
    out = []
    for p in parts:
        name = p.split(":", 1)[0].strip()
        body = p.split("\n", 1)[1]
        # Drop whole-line comments (a section header after the last statement would otherwise be
        # part of it, and a table name inside the comment would make the probe below skip the macro).
        body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("--"))
        out.append((name, body.strip().rstrip(";")))
    return out


def build(data_root: str | None = None) -> dict:
    paths = config.data_paths(data_root)
    final = paths.duckdb
    tmp = final.with_suffix(".duckdb.tmp")
    tmp.unlink(missing_ok=True)
    t0 = time.perf_counter()
    con = duckdb.connect(str(tmp))
    tables = {}
    for name, src in _parquet_sources(paths).items():
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM {src}")
        if name == "ref_provider":
            # hive partition column duplicates practice_state; drop it
            cols = [r[0] for r in con.execute("DESCRIBE ref_provider").fetchall()]
            if "state_part" in cols:
                con.execute("ALTER TABLE ref_provider DROP COLUMN state_part")
        tables[name] = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
    from .common.output import read_manifests
    mismatch = {}
    for name, m in read_manifests(paths).items():
        if name in tables and tables[name] != m["rows"]:
            mismatch[name] = {"manifest": m["rows"], "duckdb": tables[name]}
            log.error("%s: load wrote %s rows but DuckDB has %s", name, f"{m['rows']:,}", f"{tables[name]:,}")
    con.execute("CREATE TABLE cfg_first_market_zip3 (zip3 VARCHAR, market_part VARCHAR, state VARCHAR, metro VARCHAR)")
    con.executemany("INSERT INTO cfg_first_market_zip3 VALUES (?, ?, ?, ?)", _geo_rows(config.geography()))
    con.execute("CREATE TABLE cfg_ccn_npi_reclass (npi VARCHAR, category VARCHAR, reason VARCHAR, source VARCHAR)")
    reclass = _reclass_rows()
    if reclass:
        con.executemany("INSERT INTO cfg_ccn_npi_reclass VALUES (?, ?, ?, ?)", reclass)
    created, skipped = [], {}
    for name, sql in statements():
        # A view file (views_mrf.sql, views_340b.sql ...) may define a view over Parquet that
        # this build has already copied in as a table of the same name: keep the table.
        same = [v for v in re.findall(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([A-Za-z0-9_]+)", sql, flags=re.I)
                if v in tables]
        if same:
            sql = re.sub(r"(?is)CREATE\s+OR\s+REPLACE\s+VIEW\s+(" + "|".join(same) + r")\b.*?;", "", sql).strip()
            if not sql.strip(" ;\n"):
                created.append(f"{name} (already a table)")
                continue
        try:
            con.execute(sql)
            # Macros bind lazily: probe that referenced tables exist.
            for t in re.findall(r"\b(ref_[a-z0-9_]+|cfg_[a-z0-9_]+)\b", sql):
                if t not in tables and not t.startswith("cfg_"):
                    raise duckdb.CatalogException(f"table {t} not loaded")
            created.append(name)
        except duckdb.Error as e:
            skipped[name] = str(e).splitlines()[0]
            for drop in (f"DROP MACRO TABLE IF EXISTS {name}", f"DROP VIEW IF EXISTS {name}"):
                try:
                    con.execute(drop)
                except duckdb.Error:
                    pass
    con.execute("CHECKPOINT")
    con.close()
    tmp.replace(final)
    wal = Path(str(tmp) + ".wal")
    wal.unlink(missing_ok=True)
    summary = {"path": str(final), "tables": tables, "objects_created": created,
               "objects_skipped": skipped, "row_mismatch": mismatch, "seconds": round(time.perf_counter() - t0, 2),
               "size_bytes": final.stat().st_size}
    for k, v in tables.items():
        log.info("table %-22s %12s rows", k, f"{v:,}")
    for k in created:
        log.info("created  %s", k)
    for k, v in skipped.items():
        log.info("skipped  %s (%s)", k, v)
    return summary


def connect_readonly(data_root: str | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.data_paths(data_root).duckdb), read_only=True)


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    a = ap.parse_args(argv)
    build(a.data_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
