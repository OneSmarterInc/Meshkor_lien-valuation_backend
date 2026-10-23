"""Guide 2.3 step 4: older versions (2024, 2025) of a hospital's price file from the Internet Archive.

Asks the Wayback CDX API for every capture of the hospital's mrf_url (and of the
source page, to find older file names), lists the captures by month, and downloads one
capture per requested month into <raw>/MRF/<yyyy-mm>/<ccn>/ with `source=archive` in the
folder's ARCHIVE.txt. The Internet Archive is not an official source: the report must say so,
and the lineage keeps the archive URL (it contains the capture timestamp).

Run:  python -m pipeline.hpt.archive --ccn 360085 [--months 2024-01,2024-07,2025-01,2025-07] [--list-only]
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import polars as pl

from ..common import config
from .download import filename_from

CDX = "https://web.archive.org/cdx/search/cdx?url={url}&output=json&fl=timestamp,original,statuscode,mimetype,length&filter=statuscode:200&collapse=timestamp:6"


def captures(url: str, timeout: int = 60) -> list[dict]:
    import requests
    r = requests.get(CDX.format(url=quote(url, safe="")), timeout=timeout)
    r.raise_for_status()
    rows = r.json()
    if not rows:
        return []
    hdr, out = rows[0], []
    for row in rows[1:]:
        d = dict(zip(hdr, row))
        d["month"] = d["timestamp"][:4] + "-" + d["timestamp"][4:6]
        d["archive_url"] = f"https://web.archive.org/web/{d['timestamp']}id_/{d['original']}"
        out.append(d)
    return out


def run(ccn: str, months: list[str] | None, data_root: str | None = None, list_only: bool = False) -> None:
    import requests
    paths = config.data_paths(data_root)
    cat = pl.read_parquet(paths.ref / "hpt_catalog.parquet").filter((pl.col("ccn") == ccn) & pl.col("mrf_url").is_not_null())
    if cat.height == 0:
        raise SystemExit(f"{ccn}: no mrf_url in hpt_catalog; run discover first or add it by hand")
    urls = [cat["mrf_url"][0]]
    # older files often sit under the same folder with another name: ask for the folder too
    folder = urls[0].rsplit("/", 1)[0] + "/*"
    found = []
    for u in (urls[0], folder):
        try:
            found += captures(u)
        except requests.RequestException as e:
            print(f"CDX error for {u}: {e}")
    found = [c for c in found if "standardcharges" in c["original"].lower()]
    by_month: dict[str, dict] = {}
    for c in sorted(found, key=lambda c: c["timestamp"]):
        by_month.setdefault(c["month"], c)
    rep = paths.root / "reports" / f"hpt_archive_{ccn}.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"ccn": ccn, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "captures_by_month": by_month}, indent=2))
    print(f"{ccn}: {len(found)} captures in {len(by_month)} months -> {rep}")
    for m, c in sorted(by_month.items()):
        print(f"  {m}  {c['original']}  ({c.get('length')} bytes)")
    if list_only or not by_month:
        return
    wanted = months or sorted(by_month)
    for m in wanted:
        c = by_month.get(m) or next((by_month[k] for k in sorted(by_month) if k >= m), None)
        if not c:
            print(f"  {m}: no capture at or after this month"); continue
        dest_dir = paths.raw / "MRF" / c["month"] / ccn
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename_from(c["original"])
        if dest.exists():
            print(f"  {c['month']}: already present"); continue
        print(f"  {c['month']}: downloading {c['archive_url']}")
        h = hashlib.sha256(); n = 0
        with requests.get(c["archive_url"], stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(8 << 20):
                    f.write(chunk); h.update(chunk); n += len(chunk)
        (dest_dir / "ARCHIVE.txt").write_text(
            f"source=archive\narchive_url={c['archive_url']}\noriginal_url={c['original']}\n"
            f"capture_timestamp={c['timestamp']}\nsha256={h.hexdigest()}\nbytes={n}\n")
        (dest_dir / "SHA256SUMS.txt").write_text(f"{h.hexdigest()}  {dest.name}\n")
        print(f"    {n/1e6:.1f} MB -> {dest}")
    print("Add each downloaded month as a release in config/sources_local.yaml with "
          "effective_start = the file's last_updated_on and effective_end = the day before the next file.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ccn", required=True)
    ap.add_argument("--months", default="", help="comma-separated yyyy-mm; default: every month found")
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--list-only", action="store_true")
    a = ap.parse_args(argv)
    run(a.ccn, [m.strip() for m in a.months.split(",") if m.strip()] or None, a.data_root, a.list_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
