"""Register a price file that was downloaded BY HAND in the browser (for example with a
browser-only VPN such as Urban VPN, where Python has no US address).

What it does for one hospital and one period:
  1. --file: moves the downloaded file from Downloads into <raw>\\MRF\\<period>\\<ccn>\\ (never overwrites)
  2. extracts a zip beside itself, hashes the data file (SHA-256)
  3. if the hash equals the newest earlier period for this CCN -> "unchanged" (nothing new to load)
  4. writes SHA256SUMS.txt and a row in data\\reports\\hpt_downloads.csv (result = manual)
  5. prints the release block for config\\sources_local.yaml; with --write-yaml it inserts it
     under ref_hospital_mrf.releases itself (refuses a duplicate ccn + period)

Run:
  python -m pipeline.hpt.intake --period 2026-11 --ccn 360051 --file "C:\\Users\\hansa\\Downloads\\310536568_miami-valley-hospital_standardcharges.csv" --page https://www.premierhealth.com/... --write-yaml
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from ..common import config

DATA_EXT = {".csv", ".json", ".xlsx", ".txt"}


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def previous_hashes(raw: Path, ccn: str, period: str) -> dict[str, str]:
    """{sha256: period} of every data file in earlier period folders of this CCN."""
    out: dict[str, str] = {}
    base = raw / "MRF"
    if not base.exists():
        return out
    for per in sorted(p.name for p in base.iterdir() if p.is_dir() and p.name < period and (p / ccn).is_dir()):
        sums = base / per / ccn / "SHA256SUMS.txt"
        if sums.exists():
            for line in sums.read_text().splitlines():
                parts = line.split()
                if len(parts) >= 2 and Path(parts[-1]).suffix.lower() in DATA_EXT:
                    out.setdefault(parts[0], per)
    return out


def hospital_name(ccn: str, paths) -> str:
    sites = config.PROJECT_ROOT / "config" / "hospital_sites.csv"
    if sites.exists():
        with open(sites, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r.get("ccn") == ccn:
                    return r.get("hospital_name", "")
    return ""


def yaml_block(period: str, ccn: str, page: str, member: str) -> str:
    return (f"  - period: \"{period}\"\n    ccn: \"{ccn}\"\n"
            f"    effective_start: {period}-01   # set to the file's last_updated_on after loading\n"
            f"    effective_end: 9999-12-31\n    page: {page or 'downloaded by hand'}\n"
            f"    file: MRF/{period}/{ccn}\n    members:\n      mrf: \"{member}\"\n")


def write_yaml(block: str, period: str, ccn: str, sources_path: Path) -> str:
    """Insert the block right after `releases:` of the ref_hospital_mrf table. Text edit; comments stay."""
    text = sources_path.read_text(encoding="utf-8")
    if re.search(rf'period:\s*"?{re.escape(period)}"?\s*\n\s*ccn:\s*"?{re.escape(ccn)}"?', text):
        return f"already in {sources_path.name}: ccn {ccn} period {period} (not added twice)"
    m = re.search(r"^ref_hospital_mrf:.*?\n(?:.*\n)*?(\s*releases:\s*\n)", text, re.M)
    if not m:
        return f"ref_hospital_mrf: block not found in {sources_path.name}; paste the lines by hand"
    pos = m.end()
    sources_path.write_text(text[:pos] + block + text[pos:], encoding="utf-8")
    return f"added ccn {ccn} period {period} to {sources_path.name}"


def remove_release(period: str, ccn: str, sources_path: Path) -> bool:
    """Delete the release block for ccn + period from sources_local.yaml (used when a file is quarantined)."""
    text = sources_path.read_text(encoding="utf-8")
    pat = re.compile(r'^  - period: "?' + re.escape(period) + r'"?\s*\n    ccn: "?' + re.escape(ccn) + r'"?\s*\n(?:    .*\n|\s*\n)*?(?=  - |\S|\Z)', re.M)
    new, n = pat.subn("", text)
    if n:
        sources_path.write_text(new, encoding="utf-8")
    return bool(n)


def run(period: str, ccn: str, file: str | None, page: str, data_root: str | None, do_yaml: bool) -> int:
    if not re.fullmatch(r"\d{6}", ccn):
        raise SystemExit("ccn must be 6 digits")
    if not re.fullmatch(r"\d{4}-\d{2}", period):
        raise SystemExit("period must be yyyy-mm")
    paths = config.data_paths(data_root)
    folder = paths.raw / "MRF" / period / ccn
    folder.mkdir(parents=True, exist_ok=True)
    if file:
        src = Path(file)
        if not src.exists():
            raise SystemExit(f"not found: {src}")
        dest = folder / src.name
        if dest.exists():
            raise SystemExit(f"refusing to overwrite {dest}; delete it first if you mean to replace it")
        shutil.move(str(src), str(dest))
        print(f"moved {src.name} -> {folder}")
    files = [p for p in folder.iterdir() if p.is_file() and p.name not in ("SHA256SUMS.txt",) and not p.name.startswith("source_page")]
    for z in [p for p in files if p.suffix.lower() == ".zip" and zipfile.is_zipfile(p)]:
        with zipfile.ZipFile(z) as zf:
            for n in zf.namelist():
                if not n.endswith("/") and not (folder / n).exists():
                    zf.extract(n, folder); print(f"extracted {n}")
    data = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in DATA_EXT
                   and not p.name.startswith("source_page") and p.name != "SHA256SUMS.txt"],
                  key=lambda p: p.stat().st_size, reverse=True)
    if not data:
        raise SystemExit(f"no csv/json/xlsx file in {folder}. Download it in the browser first, or pass --file.")
    main = data[0]
    sha = sha256_file(main)
    prev_period = previous_hashes(paths.raw, ccn, period).get(sha)
    if "standardcharges" not in main.name.lower():
        print(f"note: CMS names these files <EIN>_<hospital>_standardcharges.<ext>; '{main.name}' does not. Check it is the right file.")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    name = hospital_name(ccn, paths)
    log_path = paths.root / "reports" / "hpt_downloads.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    (folder / "SHA256SUMS.txt").write_text("".join(f"{sha256_file(p)}  {p.name}\n" for p in sorted(folder.iterdir())
                                                     if p.is_file() and p.name != "SHA256SUMS.txt"), encoding="ascii", errors="replace")
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["downloaded_at", "period", "ccn", "hospital_name", "mrf_url", "file", "bytes", "sha256", "result", "note"])
        if prev_period:
            w.writerow([now, period, ccn, name, page, main.name, main.stat().st_size, sha, "unchanged", f"same as {prev_period}; by hand"])
            for f in list(folder.iterdir()):
                f.unlink()
            folder.rmdir()
            print(f"{ccn} {period}: file is identical to period {prev_period} (sha {sha[:12]}). Nothing new to load; "
                  f"the duplicate copy was removed, the {prev_period} copy stays.")
            return 0
        w.writerow([now, period, ccn, name, page, main.name, main.stat().st_size, sha, "manual", "downloaded by hand in browser"])
    print(f"{ccn} {period}: {main.name} {main.stat().st_size/1e6:.1f} MB sha256 {sha}")
    block = yaml_block(period, ccn, page, main.name)
    if do_yaml:
        print(write_yaml(block, period, ccn, config.PROJECT_ROOT / "config" / "sources_local.yaml"))
    else:
        print("\nAdd under ref_hospital_mrf.releases in config/sources_local.yaml:\n" + block)
    print("next: python backend\\manage.py load_ref ref_hospital_mrf  &&  build_duckdb  &&  python -m pipeline.hpt.verify")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--period", required=True); ap.add_argument("--ccn", required=True)
    ap.add_argument("--file", help="file in Downloads to move into the raw folder (optional if already there)")
    ap.add_argument("--page", default="", help="the hospital page the file came from (proof)")
    ap.add_argument("--write-yaml", action="store_true", help="insert the release into config/sources_local.yaml")
    ap.add_argument("--data-root", default=None)
    a = ap.parse_args(argv)
    return run(a.period, a.ccn, a.file, a.page, a.data_root, a.write_yaml)


if __name__ == "__main__":
    raise SystemExit(main())
