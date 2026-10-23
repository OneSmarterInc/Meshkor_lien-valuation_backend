"""check_project.py - is all the data for the lien report and the drug audit here?

Run from D:\\meshkor-data:   python check_project.py
Writes: data\\reports\\check_project.md   (send this file back)

It reads only file names, row counts and dates. It never changes a file.
"""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MESHKOR_DATA_ROOT", ROOT / "data"))
REF = DATA / "ref"
REP = DATA / "reports"
DB = DATA / "meshkor.duckdb"


def raw_dir() -> Path:
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("MESHKOR_RAW_DIR="):
                return Path(line.split("=", 1)[1].strip().strip('"'))
    return Path(r"E:\Hansavahini\Datasetof CMS")


RAW = raw_dir()
out: list[str] = []
miss = 0


def say(s=""):
    out.append(s)
    print(s)


def find_parquet(pattern: str) -> list[str]:
    """'ANY:a|b' = every Parquet under data/ref whose path contains a or b (any layout)."""
    if pattern.startswith("ANY:"):
        keys = pattern[4:].split("|")
        allp = [Path(f).as_posix() for f in glob.glob(str(REF / "**" / "*.parquet"), recursive=True)]
        hit = [f for f in allp if any(k in f for k in keys)]
        if keys[0].startswith("ref_msdrg/"):   # titles table only, not dx / cc
            hit = [f for f in hit if not any(x in f for x in ("msdrg_dx", "msdrg_cc"))]
        return hit
    return [f for f in glob.glob(str(REF / pattern), recursive=True) if f.endswith(".parquet")]


def parquet_rows(pattern: str) -> tuple[int, int] | None:
    files = find_parquet(pattern)
    if not files:
        return None
    con = duckdb.connect()
    n = con.execute("SELECT count(*) FROM read_parquet(?, union_by_name=true)",
                    [[Path(f).as_posix() for f in files]]).fetchone()[0]
    return n, len(files)


def periods(pattern: str) -> set[str]:
    files = [Path(f).as_posix() for f in find_parquet(pattern)]
    if not files:
        return set()
    try:
        return {str(r[0]) for r in duckdb.connect().execute(
            "SELECT DISTINCT period FROM read_parquet(?, union_by_name=true)", [files]).fetchall()}
    except duckdb.Error:
        return set()


Q12 = {f"{y}Q{q}" for y in (2024, 2025, 2026) for q in (1, 2, 3, 4)}

# (product, item, parquet glob, need these periods or a min row count)
TABLES = [
    ("Both", "Providers (NPPES)", "ref_provider/**/*.parquet", 1_000_000),
    ("Both", "CCN-NPI links", "ref_ccn_npi*.parquet", 1_000),
    ("Lien", "Physician fees (MPFS)", "ref_mpfs/**/*.parquet", 1_000_000),
    ("Lien", "Outpatient (OPPS)", "ref_opps*.parquet", 100_000),
    ("Lien", "Surgery center (ASC)", "ref_asc*.parquet", 10_000),
    ("Lien", "Inpatient DRG weights", "ref_ipps_drg*.parquet", 1_000),
    ("Lien", "Inpatient hospital factors", "ref_ipps_hospital*.parquet", 1_000),
    ("Lien", "Cost reports (cost-to-charge)", "ref_hcris*.parquet", 1_000),
    ("Lien", "Lab fees (CLFS)", "ref_clfs*.parquet", 1_000),
    ("Lien", "Equipment fees (DMEPOS)", "ref_dmepos.parquet", 100_000),
    ("Lien", "Ambulance fees", "ref_ambulance*.parquet", 100),
    ("Lien", "Anesthesia conversion factors", "ref_anesthesia_cf*.parquet", 100),
    ("Lien", "Anesthesia base units", "ref_anesthesia_base_units*.parquet", 100),
    ("Lien", "Zip to locality", "ref_zip_locality*.parquet", 10_000),
    ("Lien", "Coding edits (NCCI)", "ref_ncci_ptp*.parquet", 100_000),
    ("Lien", "Unit limits (MUE)", "ref_mue*.parquet", 10_000),
    ("Both", "Drug payment limits (ASP)", "ref_asp.parquet", Q12),
    ("Both", "NDC to HCPCS crosswalk", "ref_ndc_hcpcs.parquet", Q12),
    ("Both", "HCPCS code names", "ref_hcpcs_code.parquet", Q12),
    ("Drug", "NADAC drug costs", "ref_nadac*.parquet", 10_000),
    ("Drug", "FDA NDC products", "ref_ndc_product*.parquet", 10_000),
    ("Drug", "FDA NDC packages", "ref_ndc_package*.parquet", 10_000),
    ("Drug", "340B entities", "ANY:340b_entity", 10_000),
    ("Drug", "340B contract pharmacies", "ANY:340b_contract", 1_000),
    ("Lien", "MS-DRG list (titles)", "ANY:ref_msdrg/|ref_msdrg.|ref_msdrg_", 1_000),
    ("Lien", "MS-DRG diagnosis map", "ANY:msdrg_dx", 10_000),
]

say(f"# MeshKor: project data check  ({datetime.now():%Y-%m-%d %H:%M})")
say(f"Raw folder: {RAW}   exists: {RAW.exists()}")
say()
say("## 1. Parquet tables")
say("| Status | For | Data | Rows | Detail |")
say("|---|---|---|---|---|")
for prod, name, pat, need in TABLES:
    r = parquet_rows(pat)
    if r is None:
        st, rows, det = "MISSING", "-", "no Parquet file"
    else:
        rows, nfiles = r
        if isinstance(need, set):
            got = periods(pat)
            lack = sorted(need - got)
            st = "OK" if not lack else "PARTIAL"
            det = f"{len(need & got)} of {len(need)} quarters" + (f"; missing {', '.join(lack)}" if lack else "")
        else:
            st = "OK" if rows >= need else "LOW"
            det = f"{nfiles} file(s)"
        rows = f"{rows:,}"
    if st != "OK":
        miss += 1
    say(f"| {st} | {prod} | {name} | {rows} | {det} |")

say()
say("## 2. Hospital price files (ref_hospital_mrf)")
say("| Status | CCN | Hospital | Period | Rows | Last updated |")
say("|---|---|---|---|---|---|")
want = {"360085": "Ohio State University Hospitals", "360242": "James Cancer Hospital",
        "360051": "Miami Valley Hospital", "360180": "Cleveland Clinic Main Campus"}
parts = sorted(glob.glob(str(REF / "ref_hospital_mrf" / "ccn=*" / "period=*")))
have = {}
for p in parts:
    ccn = Path(p).parent.name.split("=", 1)[1]
    per = Path(p).name.split("=", 1)[1]
    files = [Path(f).as_posix() for f in glob.glob(p + "/*.parquet")]
    if not files:
        continue
    n, lu = duckdb.connect().execute(
        "SELECT count(*), max(last_updated_on) FROM read_parquet(?)", [files]).fetchone()
    have.setdefault(ccn, []).append((per, n, lu))
for ccn, nm in want.items():
    if ccn in have:
        for per, n, lu in have[ccn]:
            say(f"| OK | {ccn} | {nm} | {per} | {n:,} | {lu} |")
    else:
        miss += 1
        rawp = list(RAW.glob(f"MRF/*/{ccn}/*standardcharges*"))
        say(f"| {'DOWNLOADED, NOT LOADED' if rawp else 'MISSING'} | {ccn} | {nm} | - | - | - |")
for ccn in sorted(set(have) - set(want)):
    for per, n, lu in have[ccn]:
        say(f"| OK (extra) | {ccn} | - | {per} | {n:,} | {lu} |")

say()
say("## 3. Downloaded but not loaded (raw folders)")
say("| Folder | Files | Note |")
say("|---|---|---|")
for folder, note in (("MSDRG", "tables loaded by load_msdrg.py; the Java grouper is used later"),
                     ("PARTB_SPEND", "Part B spending by drug; loader not written"),
                     ("IDR", "loader not written"), ("MEDICAID_OH", "loader not written"),
                     ("BWC_OH", "loader not written")):
    p = RAW / folder
    n = sum(1 for f in p.rglob("*") if f.is_file() and not f.name.endswith(".sha256")) if p.exists() else 0
    say(f"| {folder} | {n if p.exists() else 'not downloaded'} | {note} |")

say()
say("## 4. Not available yet (no action in this check)")
say("| Item | Why |")
say("|---|---|")
say("| Real pilot bills + EOBs | come from the 3 law firms |")
say("| Price files 2024-2025 history | Wayback search / hospital request |")
say("| Price files of the pilot-bill hospitals | known after the bills arrive |")
say("| NUBC revenue codes | paid license |")
say("| HUD ZIP crosswalk 2026 Q3 | not published yet |")

say()
say("## 5. Last verify reports")
names = ["verify_latest.md", "check_downloads.txt"] + sorted(Path(x).name for x in glob.glob(str(REP / "verify_msdrg*.md")))
names = list(dict.fromkeys(names)) + sorted(Path(x).name for x in glob.glob(str(REP / "verify_mrf_*.md"))) \
        + sorted(Path(x).name for x in glob.glob(str(REP / "verify_340b*.md")))
for f in names:
    p = REP / f
    if not p.exists():
        say(f"- {f}: not found")
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    key = next((ln.strip() for ln in t.splitlines()[::-1]
                if "FAIL" in ln.upper() and any(c.isdigit() for c in ln)), "(no summary line)")
    say(f"- {f} ({datetime.fromtimestamp(p.stat().st_mtime):%Y-%m-%d %H:%M}): {key[:160]}")

say()
say(f"## RESULT: {miss} item(s) missing or incomplete")
REP.mkdir(parents=True, exist_ok=True)
(REP / "check_project.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"\nSaved: {REP / 'check_project.md'}")
