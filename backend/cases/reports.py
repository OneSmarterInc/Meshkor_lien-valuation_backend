"""Report data, CSV appendix and PDF for a case (contract §3)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .models import Case
from .serializers import LineSerializer

METHOD = ("Each billed line is matched by its HCPCS/CPT code to the hospital's own published price file for the "
          "date of service, to the Medicare rate for this hospital, and to the hospital's cost from its Medicare "
          "cost report. A line with a revenue code but no HCPCS/CPT code is valued at cost only; Medicare pays it "
          "inside the coded lines of the visit. An inpatient stay is valued as one MS-DRG. The median and the "
          "10th and 90th percentiles use the hospital's rates with commercial insurers only (employer, individual "
          "and ACA exchange plans, and PPO networks); Medicare, Medicare Advantage, Medicaid and other government "
          "plans are left out because Medicare is shown as its own benchmark.")
LIMITS = ("Values marked as estimates come from a contract posted as a percentage (of billed charges, or of "
          "Medicare) rather than as dollars, or from a price file that does not cover the date of service. A cash "
          "price is shown only when the hospital posts one. A benchmark total adds up only the lines that have a "
          "value; its percentage compares it with the billed charges of those same lines. For a contract posted as a "
          "percentage of billed charges, the hospital's own dollar estimate is used, which follows its list prices. "
          "The Medicare inpatient "
          "amount is the IPPS estimate without outlier, transfer or new-technology payments. Allowed and paid amounts "
          "marked EOB are read from the insurer's Explanation of Benefits uploaded with the case and checked by a reviewer "
          "against that document.")

LINE_COLS = ["line_no", "service_date", "revenue_code", "hcpcs", "modifiers", "units", "description", "charge",
             "payer_rate", "payer_rate_is_estimate", "median", "p10", "p90", "cash", "medicare", "medicare_status",
             "medicare_source", "cost", "eob_allowed", "eob_paid", "eob_patient", "status"]


def _eob_rows(case: Case, billed) -> list[dict]:
    """Allowed and paid from the insurer's EOB: the insurer's own amounts for this claim."""
    e = case.eob or {}
    t = e.get("totals") or {}
    if not e or (t.get("allowed") is None and t.get("paid") is None):
        return []
    who = e.get("payer") or case.payer_name or "the insurer"
    eb = t.get("billed")
    whole = eb is None or not billed or abs(eb - billed) <= 0.5
    base = billed if whole else eb
    note_base = "" if whole else f"the EOB covers ${eb:,.2f} of billed charges; the % compares with that"
    out = []
    if t.get("allowed") is not None:
        out.append({"key": "eob_allowed", "benchmark": f"Allowed by {who} for this claim (EOB)", "total": t["allowed"],
                    "pct_of_billed": _pct(t["allowed"], base), "coverage_pct": 100 if whole else (round(100 * eb / billed) if billed else None),
                    "note": "; ".join(x for x in ["the insurer's contract amount, from the EOB", note_base] if x)})
    if t.get("paid") is not None:
        pt = t.get("patient")
        out.append({"key": "eob_paid", "benchmark": f"Paid by {who} (EOB)", "total": t["paid"], "pct_of_billed": _pct(t["paid"], base),
                    "coverage_pct": 100 if whole else (round(100 * eb / billed) if billed else None),
                    "note": (f"plus the patient's share ${pt:,.2f} (deductible, copay, coinsurance)" if pt is not None else "")})
    return out


def _pct(x, billed):
    return round(100 * x / billed) if (x is not None and billed) else None


MIN_COVERAGE = 50   # a benchmark total covering less of the bill than this is listed, but not compared with the bill


def _summary(case: Case, t: dict, billed, payer: str, stay: dict | None) -> list[dict]:
    """Benchmark rows. Every % is the total ÷ the billed charges of the SAME lines, so a total that
    leaves out lines (no posted rate) is never compared with the whole bill."""
    cov = (case.totals or {}).get("coverage") or {}
    self_pay = (case.payer_group or "") == "Self-pay" or not case.payer_name or case.payer_name == "Self-pay"
    est = bool(t.get("payer_rate_is_estimate") or (stay or {}).get("payer_rate_is_estimate"))
    rows = [("billed", "Billed charges", billed),
            ("payer_rate", "No insurer on the bill" if self_pay else f"Hospital's own rate with {payer}" + (" (estimate)" if est else ""), t.get("payer_rate")),
            ("median", "Median of the hospital's commercial insurer rates", t.get("median")),
            ("cash", "Hospital's cash price", t.get("cash")),
            ("cost", "Hospital's cost (cost report)", t.get("cost")),
            ("medicare", "Medicare rate for this hospital", t.get("medicare"))]
    out = []
    for key, label, total in rows:
        if key == "payer_rate":
            out += _eob_rows(case, billed)
        if key == "cash" and total is None:
            continue
        row = {"key": key, "benchmark": label, "total": total, "pct_of_billed": None, "coverage_pct": None, "note": ""}
        if key == "billed":
            row["pct_of_billed"], row["coverage_pct"] = (100 if billed else None), 100
        elif total is not None:
            c = cov.get(key)
            covered = cov.get(key + "_billed")
            if c is None or c >= 100:
                row["pct_of_billed"], row["coverage_pct"] = _pct(total, billed), 100
            elif covered is None:
                # totals stored before coverage carried dollars: fall back to the percent
                row["pct_of_billed"], row["coverage_pct"] = (round(100 * total / (billed * c / 100)) if (billed and c) else None), c
                row["note"] = f"{c} % of billed charges; the % compares those lines only"
            elif c >= MIN_COVERAGE:
                row["pct_of_billed"], row["coverage_pct"] = _pct(total, covered), c
                n, m = (cov.get("lines_with") or {}).get(key), cov.get("lines")
                row["note"] = f"{n} of {m} lines, {c} % of billed charges; the % compares those lines only" if n else f"{c} % of billed charges"
            else:
                row["coverage_pct"] = c
                n, m = (cov.get("lines_with") or {}).get(key), cov.get("lines")
                row["note"] = f"posted on only {n} of {m} lines ({c} % of billed charges): not comparable with the bill"
        elif key == "payer_rate" and self_pay:
            row["note"] = "The bill names no insurer, so there is no insurer rate. Use the median, cash, Medicare and cost."
        out.append(row)
    return out


def _eob_public(e: dict | None) -> dict | None:
    if not e:
        return None
    keep = ("payer", "plan", "claim_number", "date_from", "date_to", "ms_drg", "level", "totals", "lines", "lines_matched", "bill_lines", "vs_price_file")
    return {k: e.get(k) for k in keep}


def report_basis(case: Case) -> str:
    """The basis the totals were built on: the file in force, or the nearest file (estimates)."""
    return (case.totals or {}).get("basis") or "service_date"


def build(case: Case, basis: str | None = None) -> dict:
    basis = basis or report_basis(case)
    t = case.totals_payload()
    billed = t.get("billed")
    payer = case.payer_name or "the payer"
    st = getattr(case, "stay", None) if case.setting == Case.Setting.INPATIENT else None
    stay = None
    if st is not None:
        v = st.values or {}
        stay = {"ms_drg": st.ms_drg or None, "drg_title": st.drg_title, "drg_source": st.drg_source, "drg_confirmed": st.drg_confirmed,
                "los_days": st.los_days, "medicare_source": v.get("medicare_source", ""),
                "payer_rate_is_estimate": bool(v.get("payer_rate_is_estimate")), "p10": v.get("p10"), "p90": v.get("p90")}
    summary = _summary(case, t, billed, payer, stay)
    lines = LineSerializer(case.lines.filter(basis=basis), many=True).data
    sources, seen = [], set()
    if case.price_file:
        pf = case.price_file
        sources.append({"data": "Hospital price file", "file_name": pf.get("file_name"), "dated": pf.get("last_updated_on"), "sha256": pf.get("sha256")})
        seen.add(("Hospital price file", pf.get("file_name")))
    if case.eob and case.eob.get("file_name"):
        sources.append({"data": "Insurer EOB uploaded with the case", "file_name": case.eob.get("file_name"),
                        "dated": None, "sha256": case.eob.get("sha256")})
    extra = ((st.values or {}).get("sources") if st is not None else None) or []
    for src in list(extra) + [s for ln in lines for s in (ln.get("sources") or [])]:
        k = (src.get("label"), src.get("file_name"))
        if k not in seen:
            seen.add(k)
            sources.append({"data": src.get("label"), "file_name": src.get("file_name"), "dated": src.get("dated"), "sha256": src.get("sha256")})
    by_key = {r["key"]: r for r in summary}
    if billed:
        text = f"The hospital billed ${billed:,.2f}."
        ea, ep = by_key.get("eob_allowed"), by_key.get("eob_paid")
        if ea or ep:
            who = (case.eob or {}).get("payer") or payer
            parts = []
            if ea:
                parts.append(f"allowed ${ea['total']:,.2f}" + (f" ({ea['pct_of_billed']} % of billed)" if ea["pct_of_billed"] is not None else ""))
            if ep:
                parts.append(f"paid ${ep['total']:,.2f}")
            pt = ((case.eob or {}).get("totals") or {}).get("patient")
            text += f" The insurer's EOB for this claim shows that {who} " + " and ".join(parts) + (f"; the patient's share was ${pt:,.2f}." if pt is not None else ".")
        if stay and stay["ms_drg"]:
            text += f" The stay is valued as MS-DRG {stay['ms_drg']} ({stay['drg_title']}){f', {stay['los_days']} days' if stay['los_days'] is not None else ''}."
        pr = by_key.get("payer_rate")
        if pr and pr["total"] is not None:
            text += f" Its own negotiated rate with {payer} for the same services is ${pr['total']:,.2f}"
            if pr["pct_of_billed"] is None:
                text += f" ({pr['note']})."
            elif pr["coverage_pct"] == 100:
                text += f" ({pr['pct_of_billed']} % of billed)."
            else:
                text += f" ({pr['pct_of_billed']} % of the billed charges on those {pr['coverage_pct']} % of lines)."
            if stay is None and (t.get("payer_rate_is_estimate")):
                text += " Part of this rate is an estimate (a percentage contract)."
        md = by_key.get("median")
        if md and md["total"] is not None:
            text += f" The median of its rates with commercial insurers is ${md['total']:,.2f}" + (f" ({md['pct_of_billed']} %)." if md["pct_of_billed"] is not None else ".")
        mc = by_key.get("medicare")
        if mc and mc["total"] is not None:
            text += f" Medicare would pay this hospital ${mc['total']:,.2f}" + (f" ({mc['pct_of_billed']} %)." if mc["pct_of_billed"] is not None else ".")
        co = by_key.get("cost")
        if co and co["total"] is not None:
            text += f" The hospital's own cost for these charges is ${co['total']:,.2f} ({co['pct_of_billed']} %)."
    else:
        text = "This case has not been priced yet."
    return {
        "title": "Reasonable value of hospital charges",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_number": case.case_number, "matter_ref": case.matter_ref, "hospital_name": case.hospital_name or None,
        "service_date_from": case.service_date_from, "service_date_to": case.service_date_to, "setting": case.setting,
        "summary": summary, "summary_text": text, "lines": lines, "sources": sources, "stay": stay,
        "eob": _eob_public(case.eob),
        "method": METHOD, "limits": LIMITS,
        "reviewer": {"name": ((case.approved_by.get_full_name() or case.approved_by.email) if case.approved_by else None),
                     "approved_at": case.sent_at},
    }


def csv_bytes(case: Case) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    basis = report_basis(case)
    w.writerow(["case_number", case.case_number, "hospital", case.hospital_name, "ccn", case.ccn,
                "service_dates", f"{case.service_date_from or ''}..{case.service_date_to or ''}", "basis", basis])
    st = getattr(case, "stay", None) if case.setting == Case.Setting.INPATIENT else None
    if st is not None:
        v = st.values or {}
        w.writerow(["ms_drg", st.ms_drg, "drg_title", st.drg_title, "los_days", st.los_days, "drg_confirmed", st.drg_confirmed,
                    "stay_payer_rate", v.get("payer_rate"), "stay_median", v.get("median"), "stay_p10", v.get("p10"), "stay_p90", v.get("p90"),
                    "stay_cash", v.get("cash"), "stay_medicare", v.get("medicare"), "stay_cost", v.get("cost")])
    if case.eob:
        et = case.eob.get("totals") or {}
        w.writerow(["eob_payer", case.eob.get("payer"), "eob_claim", case.eob.get("claim_number"), "eob_ms_drg", case.eob.get("ms_drg"),
                    "eob_billed", et.get("billed"), "eob_allowed", et.get("allowed"), "eob_paid", et.get("paid"), "eob_patient", et.get("patient")])
    w.writerow(LINE_COLS + ["source_files"])
    for ln in LineSerializer(case.lines.filter(basis=basis), many=True).data:
        w.writerow([ln.get(c) for c in LINE_COLS] + ["; ".join(f"{s.get('label')}: {s.get('file_name')}" for s in ln.get("sources") or [])])
    return buf.getvalue().encode("utf-8-sig")


def pdf_bytes(case: Case, draft: bool) -> bytes:
    """The designed PDF (layout in report_pdf.py); the data is build(), the same as the on-screen report."""
    from .report_pdf import build_pdf
    return build_pdf(case, build(case), draft)
