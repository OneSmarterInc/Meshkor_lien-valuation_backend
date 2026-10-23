"""Report data, CSV appendix and PDF for a case (contract §3)."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from .models import Case
from .serializers import LineSerializer

METHOD = ("Each billed line is matched by HCPCS/CPT code (or revenue code) to the hospital's own published "
          "price file for the date of service, to the Medicare rate for this hospital, and to the hospital's "
          "cost from its Medicare cost report. An inpatient stay is valued as one MS-DRG.")
LIMITS = ("Percentile amounts exist only for codes the hospital posts with the 2026 template. A cash price is "
          "shown only when the hospital posts one. Rates posted as multipliers or percentages are not shown as dollars.")

LINE_COLS = ["line_no", "service_date", "revenue_code", "hcpcs", "modifiers", "units", "description", "charge",
             "payer_rate", "payer_rate_is_estimate", "median", "p10", "p90", "cash", "medicare", "medicare_status",
             "medicare_source", "cost", "status"]


def _pct(x, billed):
    return round(100 * x / billed) if (x is not None and billed) else None


def build(case: Case, basis: str = "service_date") -> dict:
    t = case.totals_payload()
    billed = t.get("billed")
    payer = case.payer_name or "the payer"
    summary = [
        {"benchmark": "Billed charges", "total": billed, "pct_of_billed": 100 if billed else None},
        {"benchmark": f"Hospital's own rate with {payer}", "total": t.get("payer_rate"), "pct_of_billed": _pct(t.get("payer_rate"), billed)},
        {"benchmark": "Hospital's median negotiated rate", "total": t.get("median"), "pct_of_billed": _pct(t.get("median"), billed)},
        {"benchmark": "Hospital's cost (cost report)", "total": t.get("cost"), "pct_of_billed": _pct(t.get("cost"), billed)},
        {"benchmark": "Medicare rate for this hospital", "total": t.get("medicare"), "pct_of_billed": _pct(t.get("medicare"), billed)},
    ]
    if t.get("cash") is not None:
        summary.insert(3, {"benchmark": "Hospital's cash price", "total": t["cash"], "pct_of_billed": _pct(t["cash"], billed)})
    cov = (case.totals or {}).get("coverage") or {}
    keys = {"Hospital's own rate": "payer_rate", "Hospital's median": "median", "Hospital's cash": "cash",
            "Hospital's cost": "cost", "Medicare rate": "medicare"}
    for s in summary:
        k = next((v for p, v in keys.items() if s["benchmark"].startswith(p)), None)
        c = cov.get(k) if k else None
        s["coverage_pct"] = c if c is not None else (100 if s["total"] is not None else None)
        if s["total"] is not None and c is not None and c < 100:
            # The total leaves out lines with no value: compare it with the billed amount of the same lines.
            s["pct_of_billed"] = round(100 * s["total"] / (billed * c / 100)) if (billed and c) else None
            s["benchmark"] += f" (lines = {c} % of billed)"
    lines = LineSerializer(case.lines.filter(basis=basis), many=True).data
    sources, seen = [], set()
    if case.price_file:
        pf = case.price_file
        sources.append({"data": "Hospital price file", "file_name": pf.get("file_name"), "dated": pf.get("last_updated_on"), "sha256": pf.get("sha256")})
        seen.add(("Hospital price file", pf.get("file_name")))
    for ln in lines:
        for s in ln.get("sources") or []:
            k = (s.get("label"), s.get("file_name"))
            if k not in seen:
                seen.add(k)
                sources.append({"data": s.get("label"), "file_name": s.get("file_name"), "dated": s.get("dated"), "sha256": s.get("sha256")})
    if billed:
        text = f"The hospital billed ${billed:,.2f}."
        if t.get("payer_rate") is not None:
            text += f" Its own negotiated rate with {payer} for the same services is ${t['payer_rate']:,.2f} ({_pct(t['payer_rate'], billed)} % of billed)."
        if t.get("median") is not None:
            text += f" The median of all its negotiated rates is ${t['median']:,.2f}."
        if t.get("medicare") is not None:
            text += f" Medicare would pay this hospital ${t['medicare']:,.2f}."
    else:
        text = "This case has not been priced yet."
    return {
        "title": "Reasonable value of hospital charges",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "case_number": case.case_number, "matter_ref": case.matter_ref, "hospital_name": case.hospital_name or None,
        "service_date_from": case.service_date_from, "service_date_to": case.service_date_to, "setting": case.setting,
        "summary": summary, "summary_text": text, "lines": lines, "sources": sources,
        "method": METHOD, "limits": LIMITS,
        "reviewer": {"name": ((case.approved_by.get_full_name() or case.approved_by.email) if case.approved_by else None),
                     "approved_at": case.sent_at},
    }


def csv_bytes(case: Case) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["case_number", case.case_number, "hospital", case.hospital_name, "ccn", case.ccn,
                "service_dates", f"{case.service_date_from or ''}..{case.service_date_to or ''}"])
    w.writerow(LINE_COLS + ["source_files"])
    for ln in LineSerializer(case.lines.filter(basis="service_date"), many=True).data:
        w.writerow([ln.get(c) for c in LINE_COLS] + ["; ".join(f"{s.get('label')}: {s.get('file_name')}" for s in ln.get("sources") or [])])
    return buf.getvalue().encode("utf-8-sig")


def pdf_bytes(case: Case, draft: bool) -> bytes:
    """Simple one-column PDF (reportlab). The designed layout comes with the report patch."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    r = build(case)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=0.7 * inch, rightMargin=0.7 * inch, topMargin=0.7 * inch, bottomMargin=0.7 * inch,
                            title=f"{case.case_number} valuation report")
    st = getSampleStyleSheet()
    money = lambda v: f"${v:,.2f}" if v is not None else "—"
    story = [Paragraph(r["title"] + (" — DRAFT" if draft else ""), st["Title"]),
             Paragraph(f"Case {case.case_number} · Matter {case.matter_ref or '—'} · {case.hospital_name or 'Hospital not matched'} "
                       f"· Service {case.service_date_from or '—'} to {case.service_date_to or '—'}", st["Normal"]),
             Spacer(1, 10), Paragraph(r["summary_text"], st["BodyText"]), Spacer(1, 10)]
    tbl = [["Benchmark", "Total", "% of billed"]] + [[s["benchmark"], money(s["total"]), f"{s['pct_of_billed']} %" if s["pct_of_billed"] is not None else "—"] for s in r["summary"]]
    t = Table(tbl, colWidths=[3.8 * inch, 1.4 * inch, 1.1 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story += [t, Spacer(1, 14), Paragraph("Lines", st["Heading3"])]
    rows = [["#", "Date", "Rev", "Code", "Description", "Charge", "Payer", "Median", "Medicare", "Cost"]]
    for ln in r["lines"]:
        rows.append([ln["line_no"], ln["service_date"] or "", ln["revenue_code"], ln["hcpcs"], (ln["description"] or "")[:34],
                     money(ln["charge"]), money(ln["payer_rate"]), money(ln["median"]), money(ln["medicare"]), money(ln["cost"])])
    if len(rows) == 1:
        rows.append(["", "", "", "", "No priced lines yet", "", "", "", "", ""])
    lt = Table(rows, repeatRows=1, colWidths=[0.3 * inch, 0.75 * inch, 0.4 * inch, 0.5 * inch, 2.1 * inch] + [0.65 * inch] * 5)
    lt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")), ("ALIGN", (5, 1), (-1, -1), "RIGHT")]))
    story += [lt, Spacer(1, 14), Paragraph("Method", st["Heading3"]), Paragraph(r["method"], st["BodyText"]),
              Paragraph("Limits", st["Heading3"]), Paragraph(r["limits"], st["BodyText"]), Paragraph("Sources", st["Heading3"])]
    for s in r["sources"] or [{"data": "No sources yet", "file_name": "", "dated": "", "sha256": ""}]:
        story.append(Paragraph(f"{s['data']}: {s.get('file_name') or ''} {('dated ' + str(s['dated'])) if s.get('dated') else ''} "
                               f"{('SHA-256 ' + s['sha256'][:16] + '…') if s.get('sha256') else ''}", st["Normal"]))
    doc.build(story)
    return buf.getvalue()
