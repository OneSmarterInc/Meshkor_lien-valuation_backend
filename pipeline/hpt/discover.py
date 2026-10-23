"""Guide 2.2: find each hospital's price file.

For every hospital in data/ref/hpt_hospitals.parquet with a website, fetch
    https://<site>/cms-hpt.txt   then   https://<site>/.well-known/cms-hpt.txt
parse the blocks (location-name, source-page-url, mrf-url, contact-name, contact-email) and
match each block to a CCN by hospital name. One system file often lists many hospitals.

Output: data/ref/hpt_catalog.parquet and data/reports/hpt_catalog.csv, one row per
(ccn, mrf_url): discovery method (cms-hpt | manual | none | blocked), http status, format
guessed from the URL, checked_at. Rows from config/hospital_sites.csv with a hpt_txt_url or
source_page_url override the site root.

Run:  python -m pipeline.hpt.discover [--only 360051,360180] [--timeout 20]
Sites that block non-US traffic return 403/timeouts; run those through a US connection.
"""
from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import polars as pl

from ..common import config

UA = "MeshKor-HPT/1.0 (+price transparency research; contact via hospital_sites.csv owner)"
STOP = {"hospital", "medical", "center", "the", "of", "and", "health", "inc", "llc", "campus", "system"}


def parse_hpt_txt(text: str) -> list[dict]:
    """cms-hpt.txt is a list of key: value lines; a new location-name starts a block."""
    blocks, cur = [], {}
    for line in text.splitlines():
        line = line.strip().lstrip("﻿")
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z\-_ ]+?)\s*:\s*(.*)$", line)
        if not m:
            continue
        k, v = m.group(1).strip().lower().replace("_", "-"), m.group(2).strip()
        if k == "location-name":
            if cur:
                blocks.append(cur)
            cur = {"location_name": v}
        elif k in ("mrf-url", "source-page-url", "contact-name", "contact-email"):
            cur[k.replace("-", "_")] = v
    if cur:
        blocks.append(cur)
    return [b for b in blocks if b.get("mrf_url")]


def name_tokens(s: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in STOP and len(t) > 2}


def best_ccn(location_name: str, hospitals: pl.DataFrame) -> tuple[str | None, float]:
    """Pick the hospital whose name shares the most tokens with the location name."""
    lt = name_tokens(location_name)
    best, score = None, 0.0
    for ccn, name, dba in zip(hospitals["ccn"], hospitals["hospital_name"], hospitals["dba_name"]):
        for cand in (name, dba):
            ct = name_tokens(cand)
            if not ct or not lt:
                continue
            s = len(lt & ct) / max(len(lt), 1)
            if s > score:
                best, score = ccn, s
    return (best, score) if score >= 0.5 else (None, score)


def fetch(url: str, timeout: int) -> tuple[int, str]:
    import requests
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA}, allow_redirects=True)
        return r.status_code, (r.text if r.status_code == 200 else "")
    except requests.RequestException as e:
        return 0, str(e)[:120]


def run(data_root: str | None = None, only: list[str] | None = None, timeout: int = 20) -> Path:
    paths = config.data_paths(data_root)
    hosp = pl.read_parquet(paths.ref / "hpt_hospitals.parquet")
    if only:
        hosp = hosp.filter(pl.col("ccn").is_in(only))
    sites = pl.read_csv(config.PROJECT_ROOT / "config" / "hospital_sites.csv", infer_schema_length=0)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, seen_sites = [], {}
    for h in hosp.iter_rows(named=True):
        site = h.get("website")
        if not site:
            rows.append({**_base(h, now), "method": "none", "note": "no website in hospital_sites.csv"})
            continue
        override = sites.filter(pl.col("ccn") == h["ccn"])
        hpt_url = override["hpt_txt_url"][0] if override.height and override["hpt_txt_url"][0] else None
        candidates = [hpt_url] if hpt_url else [urljoin(site.rstrip("/") + "/", "cms-hpt.txt"),
                                                 urljoin(site.rstrip("/") + "/", ".well-known/cms-hpt.txt")]
        key = urlparse(site).netloc
        if key in seen_sites:
            status, blocks, used = seen_sites[key]
        else:
            status, blocks, used = 0, [], None
            for u in candidates:
                status, text = fetch(u, timeout)
                if status == 200 and "mrf-url" in text.lower():
                    blocks, used = parse_hpt_txt(text), u
                    break
            seen_sites[key] = (status, blocks, used)
        if not blocks:
            method = "blocked" if status in (403, 429, 0) else "none"
            rows.append({**_base(h, now), "method": method, "http_status": status, "hpt_txt_url": used,
                         "note": f"no cms-hpt.txt at {candidates[0]} (status {status})"})
            continue
        matched = False
        for b in blocks:
            ccn, score = best_ccn(b["location_name"], hosp)
            if ccn == h["ccn"]:
                matched = True
                rows.append({**_base(h, now), "method": "cms-hpt", "http_status": status, "hpt_txt_url": used,
                             "location_name": b["location_name"], "mrf_url": b["mrf_url"],
                             "source_page_url": b.get("source_page_url"), "contact_name": b.get("contact_name"),
                             "contact_email": b.get("contact_email"), "match_score": round(score, 2),
                             "file_format": guess_format(b["mrf_url"])})
        if not matched:
            rows.append({**_base(h, now), "method": "cms-hpt-unmatched", "http_status": status, "hpt_txt_url": used,
                         "note": f"{len(blocks)} blocks in cms-hpt.txt, none matched this hospital name; "
                                 f"names: {'; '.join(b['location_name'] for b in blocks[:6])}"})
    cat = pl.DataFrame(rows, infer_schema_length=None)
    out = paths.ref / "hpt_catalog.parquet"
    cat.write_parquet(out, compression="zstd")
    rep = paths.root / "reports" / "hpt_catalog.csv"
    cat.write_csv(rep)
    counts = cat.group_by("method").len().sort("method")
    print(counts)
    print(f"-> {out}\n-> {rep}")
    return out


def _base(h: dict, now: str) -> dict:
    return {"ccn": h["ccn"], "npi": h["npi"], "hospital_name": h["hospital_name"], "system": h.get("system"),
            "website": h.get("website"), "checked_at": now, "http_status": None, "hpt_txt_url": None,
            "location_name": None, "mrf_url": None, "source_page_url": None, "contact_name": None,
            "contact_email": None, "match_score": None, "file_format": None, "note": None}


def guess_format(url: str) -> str:
    u = url.lower().split("?")[0]
    for ext, fmt in ((".json", "json"), (".csv", "csv"), (".zip", "zip"), (".xlsx", "xlsx"), (".txt", "txt")):
        if u.endswith(ext):
            return fmt
    return "unknown"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--only", default="", help="comma-separated CCNs")
    ap.add_argument("--timeout", type=int, default=20)
    a = ap.parse_args(argv)
    run(a.data_root, [c.strip() for c in a.only.split(",") if c.strip()] or None, a.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
