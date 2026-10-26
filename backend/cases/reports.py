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
          "amount is the IPPS estimate without outlier, transfer or new-technology payments.")

LINE_COLS = ["line_no", "service_date", "revenue_code", "hcpcs", "modifiers", "units", "description", "charge",
             "payer_rate", "payer_rate_is_estimate", "median", "p10", "p90", "cash", "medicare", "medicare_status",
             "medicare_source", "cost", "status"]


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
    extra = ((st.values or {}).get("sources") if st is not None else None) or []
    for src in list(extra) + [s for ln in lines for s in (ln.get("sources") or [])]:
        k = (src.get("label"), src.get("file_name"))
        if k not in seen:
            seen.add(k)
            sources.append({"data": src.get("label"), "file_name": src.get("file_name"), "dated": src.get("dated"), "sha256": src.get("sha256")})
    by_key = {r["key"]: r for r in summary}
    if billed:
        text = f"The hospital billed ${billed:,.2f}."
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
    w.writerow(LINE_COLS + ["source_files"])
    for ln in LineSerializer(case.lines.filter(basis=basis), many=True).data:
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
    small = st["BodyText"].clone("small", fontSize=7, leading=9)
    tbl = [["Benchmark", "Total", "% of billed"]] + [
        [Paragraph(s["benchmark"] + (f"<br/><font color='#555555'>{s['note']}</font>" if s.get("note") else ""), small),
         money(s["total"]), f"{s['pct_of_billed']} %" if s["pct_of_billed"] is not None else "—"] for s in r["summary"]]
    t = Table(tbl, colWidths=[4.2 * inch, 1.3 * inch, 1.0 * inch])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f3a5f")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("FONTSIZE", (0, 0), (-1, -1), 9)]))
    story += [t, Spacer(1, 10)]
    stay = r.get("stay")
    if stay and stay.get("ms_drg"):
        story += [Paragraph("Inpatient stay", st["Heading3"]),
                  Paragraph(f"Valued as one MS-DRG: <b>{stay['ms_drg']}</b> {stay.get('drg_title') or ''}"
                            f"{(', ' + str(stay['los_days']) + ' days') if stay.get('los_days') is not None else ''}. "
                            f"DRG {'confirmed by the reviewer' if stay.get('drg_confirmed') else 'as shown on the bill, not yet confirmed'}. "
                            f"{('Medicare: ' + stay['medicare_source'] + '.') if stay.get('medicare_source') else ''} "
                            f"{('Posted rates for this DRG range from ' + money(stay['p10']) + ' (10th percentile) to ' + money(stay['p90']) + ' (90th).') if stay.get('p10') is not None else ''}",
                            st["BodyText"]), Spacer(1, 10)]
    story += [Paragraph("Lines", st["Heading3"])]
    rows = [["#", "Date", "Rev", "Code", "Units", "Description", "Charge", "Payer", "Median", "Medicare", "Cost"]]
    for ln in r["lines"]:
        pay = money(ln["payer_rate"]) + ("*" if (ln["payer_rate"] is not None and ln.get("payer_rate_is_estimate")) else "")
        med = "pkg" if ln.get("medicare_status") == "packaged" and not ln["medicare"] else money(ln["medicare"])
        rows.append([ln["line_no"], ln["service_date"] or "", ln["revenue_code"], ln["hcpcs"], f"{ln['units']:g}" if ln.get("units") is not None else "",
                     (ln["description"] or "")[:30], money(ln["charge"]), pay, money(ln["median"]), med, money(ln["cost"])])
    if len(rows) == 1:
        rows.append(["", "", "", "", "", "No priced lines yet", "", "", "", "", ""])
    lt = Table(rows, repeatRows=1, colWidths=[0.3 * inch, 0.72 * inch, 0.38 * inch, 0.5 * inch, 0.4 * inch, 1.75 * inch] + [0.65 * inch] * 5)
    lt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("GRID", (0, 0), (-1, -1), 0.2, colors.lightgrey),
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef5")), ("ALIGN", (6, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story += [lt, Paragraph("* estimate (percentage contract or price file outside the date of service) · pkg = packaged into another Medicare payment · — = no value", small),
              Spacer(1, 14), Paragraph("Method", st["Heading3"]), Paragraph(r["method"], st["BodyText"]),
              Paragraph("Limits", st["Heading3"]), Paragraph(r["limits"], st["BodyText"]), Paragraph("Sources", st["Heading3"])]
    for s in r["sources"] or [{"data": "No sources yet", "file_name": "", "dated": "", "sha256": ""}]:
        story.append(Paragraph(f"{s['data']}: {s.get('file_name') or ''} {('dated ' + str(s['dated'])) if s.get('dated') else ''} "
                               f"{('SHA-256 ' + s['sha256'][:16] + '…') if s.get('sha256') else ''}", st["Normal"]))
    doc.build(story)
    return buf.getvalue()
