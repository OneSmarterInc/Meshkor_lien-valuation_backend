"""Guide 2.3: download every catalogued price file, keep every version, re-run monthly.

For each catalog row with an mrf_url:
  1. stream the file to <raw>/MRF/<period>/<ccn>/<file name>, hashing while writing
  2. if the hash equals the newest earlier period's hash, delete the new copy and record "unchanged"
  3. extract a zip next to itself (the loader reads the csv/json inside)
  4. save the hospital's source page HTML beside it (the proof of where it came from)
  5. write SHA256SUMS.txt in the folder and a row in data/reports/hpt_downloads.csv

Then add the new releases to config/sources_local.yaml (printed at the end) and run
    python backend\\manage.py load_ref ref_hospital_mrf

Run:  python -m pipeline.hpt.download --period 2026-11 [--only 360051,360180] [--delay 2]
Windows Task Scheduler, 1st of each month:  python -m pipeline.hpt.download --period %date:~-4%-%date:~4,2%
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import polars as pl

from ..common import config

UA = "MeshKor-HPT/1.0 (+price transparency research)"
CHUNK = 8 * 1024 * 1024


def stream_download(url: str, dest: Path, timeout: int = 120) -> tuple[str, int, int]:
    import requests
    h = hashlib.sha256(); n = 0
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": UA}) as r:
        status = r.status_code
        if status != 200:
            return "", 0, status
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    f.write(chunk); h.update(chunk); n += len(chunk)
    tmp.rename(dest)
    return h.hexdigest(), n, status


def previous_hash(raw: Path, ccn: str, period: str) -> tuple[str | None, str | None]:
    """Newest earlier period folder's SHA256SUMS.txt entry for a standardcharges file."""
    base = raw / "MRF"
    if not base.exists():
        return None, None
    periods = sorted(p.name for p in base.iterdir() if p.is_dir() and p.name < period and (p / ccn).is_dir())
    for p in reversed(periods):
        sums = base / p / ccn / "SHA256SUMS.txt"
        if sums.exists():
            for line in sums.read_text().splitlines():
                if "standardcharges" in line.lower() and not line.lower().endswith(".zip"):
                    return line.split()[0], p
    return None, None


def filename_from(url: str) -> str:
    name = Path(urlparse(url).path).name or "standardcharges"
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", name)


def run(period: str, data_root: str | None = None, only: list[str] | None = None,
        delay: float = 2.0, timeout: int = 300) -> Path:
    import requests
    paths = config.data_paths(data_root)
    cat = pl.read_parquet(paths.ref / "hpt_catalog.parquet").filter(pl.col("mrf_url").is_not_null())
    if only:
        cat = cat.filter(pl.col("ccn").is_in(only))
    log_path = paths.root / "reports" / "hpt_downloads.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    yaml_lines = []
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["downloaded_at", "period", "ccn", "hospital_name", "mrf_url", "file", "bytes", "sha256", "result", "note"])
        for row in cat.iter_rows(named=True):
            ccn, url = row["ccn"], row["mrf_url"]
            folder = paths.raw / "MRF" / period / ccn
            folder.mkdir(parents=True, exist_ok=True)
            dest = folder / filename_from(url)
            if dest.exists():
                w.writerow([now, period, ccn, row["hospital_name"], url, dest.name, dest.stat().st_size, "", "skipped", "already present"])
                print(f"{ccn} skip (already there) {dest.name}")
                continue
            try:
                sha, nbytes, status = stream_download(url, dest, timeout)
            except requests.RequestException as e:
                w.writerow([now, period, ccn, row["hospital_name"], url, dest.name, 0, "", "error", str(e)[:200]])
                print(f"{ccn} ERROR {e}")
                time.sleep(delay); continue
            if status != 200:
                w.writerow([now, period, ccn, row["hospital_name"], url, dest.name, 0, "", "error", f"http {status}"])
                print(f"{ccn} http {status}")
                time.sleep(delay); continue
            # the zip's content hash is what matters for "unchanged"; compare after extraction below
            extracted = []
            if dest.suffix.lower() == ".zip" and zipfile.is_zipfile(dest):
                with zipfile.ZipFile(dest) as zf:
                    for n in zf.namelist():
                        if not n.endswith("/"):
                            zf.extract(n, folder); extracted.append(folder / n)
            data_file = extracted[0] if extracted else dest
            data_sha = hashlib.sha256(data_file.read_bytes()).hexdigest() if data_file != dest else sha
            prev, prev_period = previous_hash(paths.raw, ccn, period)
            if prev and prev == data_sha:
                for p in [dest, *extracted]:
                    p.unlink(missing_ok=True)
                try:
                    folder.rmdir()
                except OSError:
                    pass
                w.writerow([now, period, ccn, row["hospital_name"], url, dest.name, nbytes, data_sha, "unchanged", f"same as {prev_period}"])
                print(f"{ccn} unchanged since {prev_period}")
                time.sleep(delay); continue
            # source page as proof
            page = row.get("source_page_url")
            if page:
                try:
                    r = requests.get(page, timeout=60, headers={"User-Agent": UA})
                    (folder / f"source_page_{period}.html").write_text(r.text, encoding="utf-8", errors="replace")
                except requests.RequestException:
                    pass
            lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest() if p.stat().st_size < 2_000_000_000 else '(large)'}  {p.name}"
                     for p in sorted(folder.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
            (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
            w.writerow([now, period, ccn, row["hospital_name"], url, dest.name, nbytes, data_sha, "downloaded", ""])
            print(f"{ccn} downloaded {nbytes/1e6:.1f} MB {dest.name}")
            member = data_file.name if extracted else dest.name
            yaml_lines.append(
                f"  - period: \"{period}\"\n    ccn: \"{ccn}\"\n    effective_start: {period}-01   # set to the file's last_updated_on after loading\n"
                f"    effective_end: 9999-12-31\n    page: {page or url}\n    file: MRF/{period}/{ccn}\n"
                f"    members:\n      mrf: \"{member}\"")
            time.sleep(delay)
    if yaml_lines:
        print("\nAdd under ref_hospital_mrf.releases in config/sources_local.yaml:\n" + "\n".join(yaml_lines))
    print(f"\nlog: {log_path}")
    return log_path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--period", required=True, help="download month, e.g. 2026-11")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--only", default="")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--timeout", type=int, default=300)
    a = ap.parse_args(argv)
    run(a.period, a.data_root, [c.strip() for c in a.only.split(",") if c.strip()] or None, a.delay, a.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
