#!/usr/bin/env python
"""One-time repair of sql/views.sql: remove the Step 2 block appended on 2026-10-22 (it had
CREATE VIEW statements that collide with the tables build_duckdb makes) and append
sql/views_step2.sql (macros and views only, with -- @stmt markers).

Run from the repo root:  python tools/patch_views_sql.py
Safe to run twice: the new block is replaced, not duplicated. A backup is written beside the file.
"""
from __future__ import annotations

import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / "sql" / "views.sql"
NEW = ROOT / "sql" / "views_step2.sql"
OLD_MARKERS = ["-- ===== Step 2 and later (added 2026-10-22) =====",
               "-- ===== Step 2 macros (macros_step2.sql, added 2026-10-23) =====",
               "-- ===== Step 2: hospital price files, MS-DRG definitions, 340B (added 2026-10-23) ====="]


def main() -> int:
    text = VIEWS.read_text(encoding="utf-8")
    cut = min((i for i in (text.find(m) for m in OLD_MARKERS) if i >= 0), default=-1)
    backup = VIEWS.with_name(f"views.sql.bak_{date.today():%Y%m%d}")
    shutil.copy(VIEWS, backup)
    head = text[:cut].rstrip() + "\n" if cut >= 0 else text.rstrip() + "\n"
    VIEWS.write_text(head + "\n" + NEW.read_text(encoding="utf-8"), encoding="utf-8")
    n_stmt = head.count("-- @stmt") + NEW.read_text(encoding="utf-8").count("-- @stmt")
    print(f"{'replaced the old Step 2 block' if cut >= 0 else 'appended Step 2 block'} in {VIEWS} "
          f"({n_stmt} statements; backup {backup.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
