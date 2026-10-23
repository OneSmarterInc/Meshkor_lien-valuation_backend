#!/usr/bin/env python
"""
load_msdrg.py: load the CMS MS-DRG Definitions Manual text files (V41 … V44) into Parquet.

Tables (each with the 5 lineage columns):
  ref_msdrg          Appendix A: one row per MS-DRG x version (mdc, M/P, title)
  ref_msdrg_dx       Appendix B: one row per ICD-10-CM diagnosis x MDC x DRG range x version
  ref_msdrg_cc       Appendix C part 1 (+2): one row per CC/MCC diagnosis x version
  ref_msdrg_cc_excl  Appendix C part 3: diagnoses that lose CC/MCC status in listed DRGs

Usage (from D:\\meshkor-data):
    python load_msdrg.py --raw "E:\\Hansavahini\\Datasetof CMS\\MSDRG"            # all versions found
    python load_msdrg.py --raw "E:\\Hansavahini\\Datasetof CMS\\MSDRG" --version V44

Output: data\\ref\\<table>\\period=V44\\part-000.parquet and data\\ref\\_manifest\\ref_msdrg\\V44.json
The grouper jars (ms-drg-mce-*-java*.zip) are hashed into the manifest, not parsed.
"""
import argparse, csv, hashlib, json, re, sys, time
from datetime import datetime
from pathlib import Path

import duckdb

PAGE = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/ms-drg-classifications-and-software"

# version -> (effective_start, effective_end, fiscal_year). x.0 = Oct 1 final rule; x.1 = Apr 1 update.
VERSIONS = {
    "V41":   ("2023-10-01", "2024-03-31", "FY2024"),
    "V41.1": ("2024-04-01", "2024-09-30", "FY2024"),
    "V42":   ("2024-10-01", "2025-03-31", "FY2025"),
    "V42.1": ("2025-04-01", "2025-09-30", "FY2025"),
    "V43":   ("2025-10-01", "2026-03-31", "FY2026"),
    "V43.1": ("2026-04-01", "2026-09-30", "FY2026"),
    "V44":   ("2026-10-01", "2027-09-30", "FY2027"),
}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_lines(p: Path):
    return p.read_text(encoding="utf-8", errors="replace").splitlines()


def parse_appendix_a(lines):
    """DRG(3) MDC(2) M/P(1) title. Returns list of dicts."""
    out, started = [], False
    rx = re.compile(r"^(\d{3}) (\d{2}| {2}) {2}([MP ]) {2}(.*)$")
    for ln in lines:
        if ln.startswith("DRG MDC MS"):
            started = True; continue
        if not started or not ln.strip():
            continue
        m = rx.match(ln)
        if not m:
            continue
        drg, mdc, mp, title = m.groups()
        out.append({"ms_drg": drg, "mdc": mdc.strip() or "", "drg_type": {"M": "MED", "P": "SURG"}.get(mp.strip(), ""),
                    "title": title.strip()})
    return out


def parse_appendix_b(lines):
    """' I10 Dx  MDC DRG(s)      Description' with continuation rows (blank code)."""
    out, started, cur = [], False, None
    rx = re.compile(r"^ (\S+)\s+(\d{2})\s+(\S+)\s*(.*)$")
    rx_cont = re.compile(r"^\s{6,}(\d{2})\s+(\S+)\s*(.*)$")
    for ln in lines:
        if ln.strip().startswith("I10 Dx"):
            started = True; continue
        if not started or not ln.strip():
            continue
        m = rx.match(ln)
        if m and not ln.startswith("  "):
            code, mdc, drgs, desc = m.groups()
            cur = {"icd10": code, "description": desc.strip()}
            for rng in drgs.split(","):
                lo, _, hi = rng.partition("-")
                out.append({"icd10": code, "mdc": mdc, "drg_from": lo, "drg_to": hi or lo, "description": cur["description"]})
            continue
        m = rx_cont.match(ln)
        if m and cur:
            mdc, drgs, _ = m.groups()
            for rng in drgs.split(","):
                lo, _, hi = rng.partition("-")
                out.append({"icd10": cur["icd10"], "mdc": mdc, "drg_from": lo, "drg_to": hi or lo, "description": cur["description"]})
    return out


def parse_appendix_c(lines):
    """Part 1: code Lev HAC PDX-exclusions description. Part 2: codes CC/MCC only if alive. Part 3: exclusions by DRG."""
    cc, excl = {}, []
    part = 0
    rx1 = re.compile(r"^ (\S+)\s+(CC|MCC)\s+(?:(\d{2})\s+)?(?:(\d{4}):([\d,]+) codes?|No Excl)?\s*(.*)$")
    rx_hdr3 = re.compile(r"^MDC (\d{2}) DRGs? (\d{3})(?:-(\d{3}))?\s*(.*)$")
    rx_code = re.compile(r"^\s+([A-Z]\S+)\s+(.*)$")
    cur_hdr = None
    for ln in lines:
        if ln.startswith("Appendix C Part 1"):
            part = 1; continue
        if ln.startswith("Appendix C Part 2"):
            part = 2; continue
        if ln.startswith("Appendix C Part 3"):
            part = 3; continue
        if not ln.strip():
            continue
        if part == 0 and ln.strip().startswith("I10 Dx"):
            part = 1; continue          # V41 has no "Part 1:" heading; data starts after this header
        if part == 1:
            m = rx1.match(ln)
            if m and not ln.strip().startswith("I10"):
                code, lev, hac, grp, cnt, desc = m.groups()
                cc[code] = {"icd10": code, "cc_level": lev, "hac": hac or None, "pdx_exclusion_group": grp,
                            "pdx_exclusion_count": int(cnt.replace(",", "")) if cnt else None, "description": desc.strip(),
                            "cc_only_if_alive": False}
        elif part == 2:
            m = rx_code.match(ln)
            if m and m.group(1) in cc:
                cc[m.group(1)]["cc_only_if_alive"] = True
        elif part == 3:
            m = rx_hdr3.match(ln)
            if m:
                cur_hdr = m.groups(); continue
            m = rx_code.match(ln)
            if m and cur_hdr:
                mdc, lo, hi, title = cur_hdr
                excl.append({"mdc": mdc, "drg_from": lo, "drg_to": hi or lo, "drg_group_title": title.strip(),
                             "icd10": m.group(1), "description": m.group(2).strip()})
    return list(cc.values()), excl


def write_table(con, table, rows, cols, version, start, end, fy, src_name, sha, data):
    out_dir = Path(data) / "ref" / table / f"period={version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(data) / "work"; work.mkdir(parents=True, exist_ok=True)
    tmp = work / f"{table}_{version}.csv"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
    out, tmpq = out_dir / "part-000.parquet", out_dir / "part-000.parquet.tmp"
    typed = {"pdx_exclusion_count": "INTEGER", "cc_only_if_alive": "BOOLEAN"}
    cast = ", ".join(f"TRY_CAST({c} AS {typed[c]}) AS {c}" if c in typed else c for c in cols)
    con.execute(f"""COPY (SELECT {cast}, '{fy}' AS fiscal_year,
                      DATE '{start}' AS effective_start, DATE '{end}' AS effective_end,
                      '{src_name}' AS source_file, '{sha}' AS source_sha256, '{version}' AS period
                    FROM read_csv('{tmp.as_posix()}', header=true, all_varchar=true))
                    TO '{tmpq.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)""")
    if out.exists():
        out.unlink()
    tmpq.rename(out)
    return str(out), len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", required=True, help="folder holding V41, V41.1, … subfolders")
    ap.add_argument("--version", default="", help="one version only, e.g. V44")
    ap.add_argument("--data", default="data")
    a = ap.parse_args()
    raw = Path(a.raw)
    versions = [a.version] if a.version else [v for v in VERSIONS if (raw / v).is_dir()]
    if not versions:
        sys.exit(f"no version folders found under {raw}")
    con = duckdb.connect()
    man_dir = Path(a.data) / "ref" / "_manifest" / "ref_msdrg"; man_dir.mkdir(parents=True, exist_ok=True)

    for v in versions:
        if v not in VERSIONS:
            sys.exit(f"unknown version {v}; add it to VERSIONS with its dates")
        t0 = time.time()
        d = raw / v
        start, end, fy = VERSIONS[v]
        fa, fb, fc = d / "appendix_A.txt", d / "appendix_B.txt", d / "appendix_C.txt"
        for p in (fa, fb, fc):
            if not p.exists():
                sys.exit(f"{p} not found; extract the definitions zip next to it first")
        print(f"== {v}  ({fy}, {start} → {end})")
        sha = {p.name: sha256_file(p) for p in (fa, fb, fc)}
        drgs = parse_appendix_a(read_lines(fa))
        dx = parse_appendix_b(read_lines(fb))
        ccs, excl = parse_appendix_c(read_lines(fc))
        tables = {}
        for table, rows, cols, src in (
            ("ref_msdrg", drgs, ["ms_drg", "mdc", "drg_type", "title"], fa),
            ("ref_msdrg_dx", dx, ["icd10", "mdc", "drg_from", "drg_to", "description"], fb),
            ("ref_msdrg_cc", ccs, ["icd10", "cc_level", "hac", "pdx_exclusion_group", "pdx_exclusion_count", "description", "cc_only_if_alive"], fc),
            ("ref_msdrg_cc_excl", excl, ["mdc", "drg_from", "drg_to", "drg_group_title", "icd10", "description"], fc),
        ):
            out, n = write_table(con, table, rows, cols, v, start, end, fy, f"{v}/{src.name}", sha[src.name], a.data)
            tables[table] = {"rows": n, "output": out, "source_file": src.name}
            print(f"  {table:<20} {n:>8,} rows -> {out}")
        zips = sorted(d.glob("*.zip"))
        manifest = {
            "version": v, "fiscal_year": fy, "effective_start": start, "effective_end": end, "page_url": PAGE,
            "raw_folder": str(d),
            "sources": [{"file": p.name, "sha256": sha[p.name], "bytes": p.stat().st_size, "parsed": True} for p in (fa, fb, fc)]
                       + [{"file": z.name, "sha256": sha256_file(z), "bytes": z.stat().st_size, "parsed": False,
                           "role": "grouper software" if re.search(r"java|jar", z.name, re.I) else "definitions manual zip"} for z in zips],
            "tables": tables, "loaded_at": datetime.now().isoformat(timespec="seconds"), "seconds": round(time.time() - t0, 1),
        }
        (man_dir / f"{v}.json").write_text(json.dumps(manifest, indent=2))
        print(f"  manifest: {man_dir / (v + '.json')}  ({manifest['seconds']} s)")


if __name__ == "__main__":
    main()
