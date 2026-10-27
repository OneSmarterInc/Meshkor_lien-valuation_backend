"""Freeze a report when MeshKor releases it.

At approval the PDF, the CSV appendix and the report data (JSON) are made once, encrypted like the bills
(storage.py, MESHKOR_FILE_KEY) and kept with their SHA-256. After that:
  - every download of a sent case gives exactly these bytes (the same SHA-256 every time), even when the
    code, the price files or the CMS tables change later;
  - the on-screen report of a sent case is the frozen data;
  - the SHA-256 is in the audit log and on the Report page, so anyone can check a copy:
        Windows:  Get-FileHash MK-2026-0001_valuation_report.pdf      (Algorithm SHA256 is the default)
A case sent before this existed is frozen the first time its report is opened or downloaded, from the data
of that moment, and says so (`note`).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from rest_framework.renderers import JSONRenderer

from . import reports, storage
from .audit import log
from .models import Case, ReleasedReport


def _put(case, name: str, data: bytes) -> tuple[str, str]:
    sha = hashlib.sha256(data).hexdigest()
    rel = Path(str(case.id)) / "released" / f"{name}-{sha[:12]}.enc"
    out = storage.upload_dir() / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(storage._fernet().encrypt(data))
    return rel.as_posix(), sha


def _get(rel: str, sha: str) -> bytes:
    data = storage._fernet().decrypt((storage.upload_dir() / rel).read_bytes())
    if hashlib.sha256(data).hexdigest() != sha:
        raise RuntimeError(f"The released file {rel} does not match its SHA-256; it was changed on disk.")
    return data


def freeze(case: Case, user=None, note: str = "") -> ReleasedReport:
    """Make and store the released PDF, CSV and data. Call once, when the case is sent."""
    data = reports.build(case)
    blob = JSONRenderer().render(data)
    pdf = reports.pdf_bytes(case, draft=False)
    csv_ = reports.csv_bytes(case)
    pdf_path, pdf_sha = _put(case, "report.pdf", pdf)
    csv_path, csv_sha = _put(case, "appendix.csv", csv_)
    data_path, data_sha = _put(case, "report.json", blob)
    rr = ReleasedReport.objects.create(case=case, released_at=case.sent_at or timezone.now(), released_by=user or case.approved_by,
                                       pdf_path=pdf_path, pdf_sha256=pdf_sha, pdf_bytes=len(pdf), csv_path=csv_path, csv_sha256=csv_sha,
                                       data_path=data_path, data_sha256=data_sha, note=note[:200])
    log(user, "Report frozen", f"PDF SHA-256 {pdf_sha} · CSV SHA-256 {csv_sha}" + (f" · {note}" if note else ""), case)
    return rr


def released(case: Case) -> ReleasedReport | None:
    """The frozen report of a sent case; a case sent before freezing existed is frozen now."""
    if case.status != Case.Status.SENT:
        return None
    rr = ReleasedReport.objects.filter(case=case).first()
    if rr is None:
        with transaction.atomic():
            Case.objects.select_for_update().filter(pk=case.pk).first()     # one freeze, even with two downloads at once
            rr = ReleasedReport.objects.filter(case=case).first() or freeze(
                case, note=f"sent {case.sent_at:%Y-%m-%d} before reports were frozen; frozen {timezone.now():%Y-%m-%d} from the data of that day")
    return rr


def pdf(rr: ReleasedReport) -> bytes:
    return _get(rr.pdf_path, rr.pdf_sha256)


def csv(rr: ReleasedReport) -> bytes:
    return _get(rr.csv_path, rr.csv_sha256)


def data(rr: ReleasedReport) -> dict:
    d = json.loads(_get(rr.data_path, rr.data_sha256))
    d["released"] = rr.public()
    return d
