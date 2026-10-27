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
        expected = int(r.headers.get("Content-Length") or 0) if r.headers.get("Content-Encoding") in (None, "identity") else 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(CHUNK):
                if chunk:
                    f.write(chunk); h.update(chunk); n += len(chunk)
    if expected and n != expected:
        tmp.unlink(missing_ok=True)
        raise requests.ConnectionError(f"download cut off: {n:,} of {expected:,} bytes")
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


def with_extension(path: Path) -> Path:
    """A URL like .../download/weston gives a file with no extension: look at the first bytes
    and rename to .zip / .json / .csv / .xlsx so the loader's member pattern finds it."""
    if path.suffix.lower() in (".csv", ".json", ".zip", ".xlsx", ".txt", ".xml"):
        return path
    with open(path, "rb") as f:
        head = f.read(512)
    if head.startswith(b"PK"):
        ext = ".zip"
    else:
        txt = head.lstrip(b"\xef\xbb\xbf \r\n\t")
        ext = ".json" if txt[:1] in (b"{", b"[") else ".csv"
    new = path.with_name(path.name + ext)
    path.rename(new)
    return new


def sniff_extension(path: Path) -> str:
    """'.json' / '.csv' / '.zip' / '.xlsx' from the first bytes, or '.html' for a web page, else ''."""
    with open(path, "rb") as f:
        head = f.read(4096)
    if head[:2] == b"PK":
        return ".xlsx" if b"[Content_Types].xml" in head or b"xl/" in head else ".zip"
    t = head.lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if t[:1] in (b"{", b"["):
        return ".json"
    if t[:1] == b"<" or b"<html" in t or b"<!doctype" in t:
        return ".html"
    if b"," in head or b"|" in head or b"\t" in head:
        return ".csv"
    return ""


def fix_extension(dest: Path) -> tuple[Path, str]:
    """Give an extension-less download its real one; return (path, error). A web page is an error."""
    ext = sniff_extension(dest)
    if ext == ".html":
        return dest, "server sent a web page, not a data file (login / block / wrong link)"
    if dest.suffix.lower() in (".csv", ".json", ".zip", ".xlsx", ".txt"):
        return dest, ""
    if ext:
        new = dest.with_name(dest.name + ext)
        if new.exists():
            new.unlink()
        dest.rename(new)
        return new, ""
    return dest, "cannot tell the file type (not CSV, JSON, ZIP or XLSX)"


def filename_from(url: str) -> str:
    name = Path(urlparse(url).path).name or "standardcharges"
    return re.sub(r"[^A-Za-z0-9._\-]+", "_", name)


def _logged_file(paths, ccn: str, period: str, url: str) -> str | None:
    log = paths.root / "reports" / "hpt_downloads.csv"
    if not log.exists():
        return None
    name = None
    with open(log, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("ccn") == ccn and r.get("period") == period and r.get("mrf_url") == url and r.get("result") in ("downloaded", "manual", "skipped"):
                name = r.get("file")
    return name


def classify(status: int, note: str = "") -> str:
    """Ledger reason code for a failed fetch."""
    if status in (401, 407):
        return "AUTH"
    if status == 403:
        return "AUTH" if "login" in note.lower() else "BLOCKED"
    if status == 404 or status == 410:
        return "NOT_FOUND"
    if status in (408, 504) or "timed out" in note.lower() or "timeout" in note.lower():
        return "TIMEOUT"
    if status in (429, 503, 502, 500):
        return "BLOCKED"
    if status == 0:
        return "CONN"
    return "BLOCKED"


def download_one(row: dict, period: str, paths, timeout: int = 300, log_writer=None, now: str | None = None) -> dict:
    """Download one catalog row. Returns {result, code, note, dest, member, sha256, bytes, status}.
    result: downloaded | unchanged | skipped | error. Never raises for a network/HTTP problem."""
    import requests
    now = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
    ccn, url = str(row["ccn"]), row["mrf_url"]
    folder = paths.raw / "MRF" / period / ccn
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / filename_from(url)
    if not dest.suffix:                                   # ".../weston", ".../avon": name it after the hospital
        dest = folder / f"{ccn}_{dest.name}_standardcharges"
    out = {"result": "", "code": "", "note": "", "dest": dest, "member": dest.name, "sha256": "", "bytes": 0, "status": 0}

    def log(result, note, nbytes=0, sha=""):
        out.update(result=result, note=note, bytes=nbytes, sha256=sha)
        if log_writer:
            log_writer.writerow([now, period, ccn, row.get("hospital_name"), url, out["dest"].name, nbytes, sha, result, note])
        return out

    existing = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".json", ".zip", ".xlsx")] if folder.exists() else []
    if dest.exists():
        out.update(member=dest.name)
        return log("skipped", "already present", dest.stat().st_size)
    if existing and not dest.suffix:
        # an earlier download of THIS url was renamed by its sniffed type (.csv/.json); find it in the log
        prior = _logged_file(paths, ccn, period, url)
        got = next((p for p in existing if p.name == prior), None)
        if got is not None:
            out.update(dest=got, member=got.name)
            return log("skipped", "already present", got.stat().st_size)
    try:
        sha, nbytes, status = stream_download(url, dest, timeout)
    except requests.RequestException as e:
        out["code"] = classify(0, str(e))
        return log("error", str(e)[:200])
    except Exception as e:  # noqa: BLE001
        out["code"] = "CONN"
        return log("error", f"{type(e).__name__}: {str(e)[:160]}")
    out["status"] = status
    if status != 200:
        out["code"] = classify(status)
        dest.unlink(missing_ok=True)
        return log("error", f"http {status}")
    dest, err = fix_extension(dest)
    out.update(dest=dest, member=dest.name)
    if err:
        out["code"] = "HTML" if "web page" in err else "BAD_FORMAT"
        dest.unlink(missing_ok=True)
        return log("error", err, nbytes, sha)
    extracted = []
    if dest.suffix.lower() == ".zip" and zipfile.is_zipfile(dest):
        with zipfile.ZipFile(dest) as zf:
            for n in zf.namelist():
                if not n.endswith("/"):
                    zf.extract(n, folder); extracted.append(folder / n)
    data_file = extracted[0] if extracted else dest
    data_sha = hashlib.sha256(data_file.read_bytes()).hexdigest() if data_file != dest else sha
    out["member"] = data_file.name
    prev, prev_period = previous_hash(paths.raw, ccn, period)
    if prev and prev == data_sha:
        for p in [dest, *extracted]:
            p.unlink(missing_ok=True)
        try:
            folder.rmdir()
        except OSError:
            pass
        out["note"] = f"same as {prev_period}"
        return log("unchanged", f"same as {prev_period}", nbytes, data_sha)
    page = row.get("source_page_url")
    if page:
        try:
            r = requests.get(page, timeout=60, headers={"User-Agent": UA})
            (folder / f"source_page_{period}.html").write_text(r.text, encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest() if p.stat().st_size < 2_000_000_000 else '(large)'}  {p.name}"
             for p in sorted(folder.iterdir()) if p.is_file() and p.name != "SHA256SUMS.txt"]
    (folder / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return log("downloaded", "", nbytes, data_sha)


def run(period: str, data_root: str | None = None, only: list[str] | None = None,
        delay: float = 2.0, timeout: int = 300) -> Path:
    paths = config.data_paths(data_root)
    cat = pl.read_parquet(paths.ref / "hpt_catalog.parquet").filter(pl.col("mrf_url").is_not_null())
    if only:
        cat = cat.filter(pl.col("ccn").is_in(only))
    log_path = paths.root / "reports" / "hpt_downloads.csv"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    new_log = not log_path.exists()
    yaml_lines = []
    with open(log_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_log:
            w.writerow(["downloaded_at", "period", "ccn", "hospital_name", "mrf_url", "file", "bytes", "sha256", "result", "note"])
        for row in cat.iter_rows(named=True):
            o = download_one(row, period, paths, timeout, w)
            ccn = str(row["ccn"])
            if o["result"] == "downloaded":
                print(f"{ccn} downloaded {o['bytes']/1e6:.1f} MB {o['dest'].name}")
                yaml_lines.append(
                    f"  - period: \"{period}\"\n    ccn: \"{ccn}\"\n    effective_start: {period}-01   # set to the file's last_updated_on after loading\n"
                    f"    effective_end: 9999-12-31\n    page: {row.get('source_page_url') or row['mrf_url']}\n    file: MRF/{period}/{ccn}\n"
                    f"    members:\n      mrf: \"{o['member']}\"")
            elif o["result"] == "error":
                print(f"{ccn} ERROR {o['code']} {o['note']}")
            else:
                print(f"{ccn} {o['result']} {o['note']}")
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
