"""Contract §5: GET /api/data-sources/ — what reference data is loaded and verified."""
from __future__ import annotations

import logging

from django.core.cache import cache
from rest_framework.response import Response
from rest_framework.views import APIView

from cases.permissions import IsStaffRole
from pipeline.common import config
from .models import LoadRun, VerifyRun

log = logging.getLogger("meshkor.api")

LABELS = {
    "ref_provider": "Hospitals and providers (CMS enrollment)", "ref_ccn_npi": "CCN ⇄ NPI crosswalk",
    "ref_mpfs": "Medicare physician fee schedule (MPFS)", "ref_mpfs_locality": "MPFS localities (GPCI)",
    "ref_opps": "Medicare outpatient (OPPS)", "ref_asc": "Ambulatory surgery centers (ASC)",
    "ref_clfs": "Clinical lab fee schedule", "ref_dmepos": "DMEPOS fee schedule", "ref_ambulance": "Ambulance fee schedule",
    "ref_anesthesia_cf": "Anesthesia conversion factors", "ref_anesthesia_base_units": "Anesthesia base units",
    "ref_ipps_drg": "Inpatient DRG weights (IPPS)", "ref_ipps_hospital": "IPPS hospital factors (wage index)",
    "ref_hcris": "Hospital cost reports (HCRIS, cost-to-charge)", "ref_ncci_ptp": "NCCI edits (PTP)", "ref_mue": "NCCI MUE limits",
    "ref_hcpcs_code": "HCPCS codes", "ref_code_specialty": "Code ⇄ specialty", "ref_zip_locality": "ZIP ⇄ MPFS locality",
    "ref_geo": "ZIP ⇄ county / CBSA (HUD)", "ref_geo_zcta_county": "ZCTA ⇄ county (Census)",
    "ref_quality_hospital": "Hospital quality (Care Compare)", "ref_quality_measure": "Quality measures", "ref_quality_asc": "ASC quality",
    "ref_ownership": "Hospital ownership", "ref_chow": "Changes of ownership", "ref_chow_npi": "Change of ownership ⇄ NPI",
    "ref_nadac": "Drug acquisition cost (NADAC)", "ref_ndc_product": "NDC products", "ref_ndc_package": "NDC packages",
    "ref_asp": "Drug ASP pricing", "ref_ndc_hcpcs": "NDC ⇄ HCPCS crosswalk", "ref_dmepos_rural_zip": "DMEPOS rural ZIPs",
    "ref_msdrg": "MS-DRG definitions", "ref_340b_entity": "340B covered entities",
}


def _covers(periods: list[str]) -> str:
    p = sorted(str(x) for x in periods if x)
    return "" if not p else (p[0] if len(p) == 1 else f"{p[0]}–{p[-1]}")


def _manifests() -> dict:
    """Latest manifest per table from data/ref/_manifest (what is really on disk)."""
    import json
    out = {}
    folder = config.data_paths().manifests
    for p in folder.glob("*.json"):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if m.get("table"):
            out[m["table"]] = m
    return out


def reference_rows() -> list[dict]:
    tables = list(config.sources().keys())
    for extra in ("ref_msdrg", "ref_340b_entity"):
        if extra not in tables:
            tables.append(extra)
    latest = {}
    for run in LoadRun.objects.filter(status=LoadRun.Status.SUCCESS).order_by("table", "-started_at"):
        latest.setdefault(run.table, run)
    manifests = _manifests()
    rows = []
    for t in tables:
        if t == "ref_hospital_mrf":
            continue
        run, man = latest.get(t), manifests.get(t)
        if man is not None:
            # The manifest is written by the loader with the Parquet file: it is the truth about what is loaded,
            # also on a PC that copied data/ without the PostgreSQL load history.
            n = man.get("rows") or 0
            periods = [src.get("period") for src in man.get("sources") or []]
            st = "ok" if n > 0 else "partial"
            if any("skipped" in str(w).lower() for w in man.get("warnings") or []):
                st = "partial"
            rows.append({"name": LABELS.get(t, t), "rows": n, "covers": _covers(periods), "status": st})
        elif run is None:
            rows.append({"name": LABELS.get(t, t), "rows": 0, "covers": "", "status": "missing"})
        else:
            st = "ok" if (run.rows or 0) > 0 else "partial"
            if run.warnings:
                st = "partial" if st == "ok" and any("skipped" in str(w).lower() for w in run.warnings) else st
            rows.append({"name": LABELS.get(t, t), "rows": run.rows or 0, "covers": _covers(run.periods), "status": st})
    return rows


def verify_summary() -> dict | None:
    v = VerifyRun.objects.order_by("-created_at").first()
    if v:
        return {"pass": v.passed, "fail": v.failed, "run_at": v.created_at}
    # No run recorded in this database: read the report file the verify step wrote.
    import re
    p = config.data_paths().root / "reports" / "verify_latest.md"
    if p.exists():
        head = p.read_text(encoding="utf-8", errors="replace")[:600]
        m = re.search(r"\*\*(\d[\d,]*) pass · (\d[\d,]*) fail", head)
        c = re.search(r"Created (\S+)", head)
        if m:
            return {"pass": int(m.group(1).replace(",", "")), "fail": int(m.group(2).replace(",", "")), "run_at": c.group(1) if c else None}
    return None


def price_file_rows() -> list[dict]:
    import duckdb
    paths = config.data_paths()
    folder = paths.ref / "ref_hospital_mrf"
    if not folder.exists() or not any(folder.rglob("*.parquet")):
        return []
    try:
        con = duckdb.connect()
        rows = con.execute(f"""
            SELECT ccn, any_value(hospital_name), max(last_updated_on), count(*)
            FROM read_parquet('{folder.as_posix()}/**/*.parquet', union_by_name=true)
            GROUP BY ccn ORDER BY ccn""").fetchall()
        return [{"ccn": c, "hospital_name": h, "last_updated_on": str(d) if d else None, "rows": n, "status": "loaded"} for c, h, d, n in rows]
    except Exception as e:  # noqa: BLE001
        log.warning("price file summary failed: %s", e)
        return [{"ccn": "", "hospital_name": "price files", "last_updated_on": None, "rows": 0, "status": "error"}]


class DataSourcesView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        data = cache.get("data_sources")
        if data is None:
            data = {
                "verify": verify_summary(),
                "reference": reference_rows(),
                "price_files": price_file_rows(),
            }
            cache.set("data_sources", data, 300)
        return Response(data)
