"""Case intake: read the bill, match the hospital, price it, write the result.

Called by backend/cases/processing.py (the only place the API calls the pipeline).
Ends in one of:
  needs_review   priced; a person checks the flags and approves
  no_price_file  hospital found, but no price file loaded (Medicare and cost still filled)
  error          bill not readable, hospital not found, or reference data missing
"""
from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from . import match, price, reader
from .db import ReferenceDataMissing, connect

log = logging.getLogger("meshkor.lien")


def _summary(bill: reader.Bill) -> str:
    if bill.reason:
        return bill.reason[:200]
    if bill.inpatient:
        days = (bill.date_to - bill.date_from).days if (bill.date_from and bill.date_to) else None
        return f"Inpatient stay{f', {days} days' if days is not None else ''}"
    if any(ln.revenue_code.startswith("045") for ln in bill.lines):
        return "Emergency room visit"
    return (bill.lines[0].description if bill.lines else "Outpatient visit")[:200]


def _fail(case, detail: str, user=None):
    from cases.audit import log as audit
    case.status, case.status_detail = case.Status.ERROR, detail
    case.save(update_fields=["status", "status_detail", "updated_at"])
    audit(user, "Processing stopped", detail, case)


def process(case, drg_override: str | None = None, user=None) -> None:
    """Price one case. Safe to run again: lines, stay and open flags are replaced."""
    from cases import storage
    from cases.audit import log as audit
    from cases.models import CaseLine, Flag, Stay

    bill_file = case.files.filter(kind="bill").first()
    if bill_file is None:
        return _fail(case, "No bill file on this case.", user)
    case.status, case.status_detail = case.Status.PROCESSING, ""
    case.save(update_fields=["status", "status_detail", "updated_at"])
    try:
        bill = reader.read(storage.read(bill_file), bill_file.name)
    except reader.BillNotReadable as e:
        return _fail(case, f"The bill could not be read: {e}", user)
    if drg_override:
        bill.ms_drg = drg_override
    try:
        con = connect()
    except ReferenceDataMissing as e:
        return _fail(case, str(e), user)
    try:
        hosp = match.find(con, ccn=bill.ccn, npi=bill.npi, name=bill.facility_name)
        if hosp is None:
            return _fail(case, f"Hospital not found (name “{bill.facility_name or '—'}”, CCN {bill.ccn or '—'}, "
                               f"NPI {bill.npi or '—'}). Add the CCN on the bill or in config/ccn_npi_manual.csv.", user)
        res = price.price(con, bill, hosp.ccn, bill.payer)
    except Exception as e:  # noqa: BLE001 — record every failure on the case; the traceback goes to the log only
        log.exception("pricing failed for %s", case.case_number)
        return _fail(case, f"Pricing failed: {type(e).__name__}: {str(e)[:300]}. See the server log.", user)
    finally:
        con.close()

    if not hosp.certain:
        res.flags.insert(0, {"kind": "other", "severity": "check", "line_no": None,
                             "title": f"Hospital matched by name: {hosp.name} (CCN {hosp.ccn})",
                             "detail": f"The bill shows “{bill.facility_name}” and no CCN or known NPI. Confirm the match."})
    if case.files.filter(kind="eob").count() == 0 and res.payer_group != price.SELF_PAY:
        res.flags.append({"kind": "no_eob", "severity": "info", "line_no": None, "title": "No EOB uploaded",
                          "detail": "With the insurer's EOB, the report can show what was actually allowed and paid."})

    with transaction.atomic():
        kept = {(f.kind, f.line_no, f.title): f for f in case.flags.filter(resolved=True)}
        case.flags.all().delete()
        case.lines.all().delete()
        for basis, lines in res.lines.items():
            CaseLine.objects.bulk_create([CaseLine(case=case, basis=basis, **{k: v for k, v in d.items() if not k.startswith("_")})
                                          for d in lines])
        for fl in res.flags:
            old = kept.get((fl["kind"], fl["line_no"], fl["title"]))
            Flag.objects.create(case=case, **fl, **({"resolved": True, "resolved_by": old.resolved_by, "resolved_at": old.resolved_at,
                                                     "note": old.note} if old else {}))
        Stay.objects.filter(case=case).delete()
        if res.stay is not None:
            st = res.stay
            Stay.objects.create(case=case, ms_drg=st["ms_drg"] or "", drg_title=st["drg_title"] or "",
                                drg_source="reviewer" if drg_override else "bill", drg_confirmed=bool(drg_override),
                                los_days=st["los_days"], diagnoses=st["diagnoses"],
                                values={**st["values"], "sources": st["sources"], "medicare_source": st.get("medicare_source", "")})
        case.bill_type = "UB-04" if bill.type_of_bill else "itemized"
        case.visit_summary = _summary(bill)
        case.hospital_name, case.ccn, case.npi = hosp.name[:200], hosp.ccn, (bill.npi or hosp.npi or "")[:10]
        case.setting = case.Setting.INPATIENT if bill.inpatient else case.Setting.OUTPATIENT
        case.service_date_from, case.service_date_to = bill.date_from, bill.date_to
        case.payer_name, case.payer_group = (bill.payer or "Self-pay")[:200], res.payer_group
        case.billed_total = bill.lines_total
        case.price_file = res.price_file.as_json() if res.price_file else None
        case.totals = res.totals
        if res.price_file is None:
            case.status, case.status_detail = case.Status.NO_PRICE_FILE, "No price file loaded for this hospital."
        elif res.totals.get("basis") == "estimate":
            case.status, case.status_detail = case.Status.NEEDS_REVIEW, "Price file does not cover the service date: insurer rate, median and cash are estimates."
        else:
            case.status, case.status_detail = case.Status.NEEDS_REVIEW, ""
        case.updated_at = timezone.now()
        case.save()
    open_checks = sum(1 for f in res.flags if f["severity"] == "check")
    audit(user, "Bill priced", f"{len(bill.lines)} lines · {hosp.name} (CCN {hosp.ccn}) · payer group {res.payer_group} · "
                               f"{open_checks} flag(s) to check", case)
