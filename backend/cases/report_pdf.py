"""The designed PDF report (reportlab). The data comes from reports.build(); this file is only the layout.

Page 1   header band, case facts, the key number, benchmark chart, summary table, summary text
Next     EOB and inpatient stay (when present), line-by-line table, sources, method, limits, sign-off
Every page: footer with case number, "Page x of y", and a PHI notice. A draft has a DRAFT watermark.

Fonts are the PDF base fonts (Helvetica, Courier), so nothing has to be installed on the server.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (CondPageBreak, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

# Portal colours (frontend src/styles.css)
INK = colors.HexColor("#17232b")
MUTED = colors.HexColor("#5b6b73")
LINE = colors.HexColor("#d9e0e2")
SOFT = colors.HexColor("#eaf0f0")
ACCENT = colors.HexColor("#0d6b6e")
ACCENT_SOFT = colors.HexColor("#d8ecec")
BILLED = colors.HexColor("#5b6b73")
WARN = colors.HexColor("#9a6a00")

W, H = letter
M = 0.65 * inch
CW = W - 2 * M                      # content width

S = {
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=INK),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=ACCENT, spaceBefore=12, spaceAfter=6),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, leading=13.5, textColor=INK),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.6, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.6, leading=11, textColor=INK),
    "num": ParagraphStyle("num", fontName="Courier", fontSize=8.6, leading=11, textColor=INK, alignment=TA_RIGHT),
    "numb": ParagraphStyle("numb", fontName="Courier-Bold", fontSize=8.6, leading=11, textColor=INK, alignment=TA_RIGHT),
    "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=6.8, leading=9, textColor=MUTED),
    "fact": ParagraphStyle("fact", fontName="Helvetica", fontSize=9, leading=11.5, textColor=INK),
    "big": ParagraphStyle("big", fontName="Helvetica-Bold", fontSize=22, leading=26, textColor=ACCENT),
    "line": ParagraphStyle("line", fontName="Helvetica", fontSize=7, leading=8.6, textColor=INK),
    "linen": ParagraphStyle("linen", fontName="Courier", fontSize=6.7, leading=8.6, textColor=INK, alignment=TA_RIGHT),
    "lineh": ParagraphStyle("lineh", fontName="Helvetica-Bold", fontSize=6.6, leading=8, textColor=MUTED),
    "linehr": ParagraphStyle("linehr", fontName="Helvetica-Bold", fontSize=6.6, leading=8, textColor=MUTED, alignment=TA_RIGHT),
}
REPORT_FOR = {"plaintiff": "Plaintiff", "defense": "Defense", "lien_resolution": "Lien resolution"}


def money(v) -> str:
    return "—" if v is None else f"${v:,.2f}"


def amt(v) -> str:
    """Line-table amounts: no $ (the column header says $), so long amounts stay on one line."""
    return "—" if v is None else f"{v:,.2f}"


def _esc(s) -> str:
    return (str(s or "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class NumberedCanvas(rl_canvas.Canvas):
    """Draws the footer after the last page is known, so it can say "Page x of y"."""

    def __init__(self, *a, case_number="", draft=False, **kw):
        super().__init__(*a, **kw)
        self._pages, self.case_number, self.draft = [], case_number, draft

    def showPage(self):
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._pages)
        for st in self._pages:
            self.__dict__.update(st)
            self._decorate(n)
            super().showPage()
        super().save()

    def _decorate(self, total):
        self.saveState()
        if self.draft:
            self.setFillColor(colors.Color(0.69, 0.23, 0.18, alpha=0.10))
            self.setFont("Helvetica-Bold", 92)
            self.translate(W / 2, H / 2)
            self.rotate(35)
            self.drawCentredString(0, -30, "DRAFT")
            self.rotate(-35)
            self.translate(-W / 2, -H / 2)
        if self._pageNumber > 1:                       # slim header on the next pages
            self.setFillColor(ACCENT)
            self.rect(M, H - 0.42 * inch, 0.16 * inch, 0.16 * inch, fill=1, stroke=0)
            self.setFillColor(INK)
            self.setFont("Helvetica-Bold", 8)
            self.drawString(M + 0.24 * inch, H - 0.39 * inch, "MeshKor Lien Valuation")
            self.setFont("Helvetica", 8)
            self.setFillColor(MUTED)
            self.drawRightString(W - M, H - 0.39 * inch, f"Case {self.case_number}" + ("  ·  DRAFT" if self.draft else ""))
            self.setStrokeColor(LINE)
            self.line(M, H - 0.5 * inch, W - M, H - 0.5 * inch)
        self.setStrokeColor(LINE)
        self.line(M, 0.55 * inch, W - M, 0.55 * inch)
        self.setFont("Helvetica", 7)
        self.setFillColor(MUTED)
        self.drawString(M, 0.4 * inch, f"Case {self.case_number}  ·  Confidential: contains protected health information. Share only with the parties to the matter.")
        self.drawRightString(W - M, 0.4 * inch, f"Page {self._pageNumber} of {total}")
        self.restoreState()


def _band(story, r, case, draft):
    """Page 1 header: brand band, title and case facts."""
    mark = Table([["MK"]], colWidths=[0.42 * inch], rowHeights=[0.42 * inch])
    mark.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                              ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 12),
                              ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    brand = Paragraph("<b>MeshKor Lien Valuation</b><br/><font color='#5b6b73' size='8'>Hospital bill benchmarks for injury cases</font>",
                      ParagraphStyle("b", fontName="Helvetica", fontSize=11, leading=13, textColor=INK))
    status = Paragraph(("<font color='#b03a2e'><b>DRAFT</b></font> · not yet approved" if draft else
                        f"<b>Final</b> · approved {_esc(_d(r['reviewer'].get('approved_at')))}"),
                       ParagraphStyle("st", parent=S["small"], alignment=TA_RIGHT, fontSize=8.5))
    top = Table([[mark, brand, status]], colWidths=[0.55 * inch, CW - 2.55 * inch, 2.0 * inch])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story += [top, Spacer(1, 14), Paragraph(_esc(r["title"]), S["h1"]),
              Paragraph(f"Case {_esc(case.case_number)}" + (f" · Matter {_esc(case.matter_ref)}" if case.matter_ref else ""),
                        ParagraphStyle("sub", parent=S["body"], textColor=MUTED, fontSize=10.5, leading=15)), Spacer(1, 10)]

    def fact(label, value):
        return [Paragraph(label.upper(), S["label"]), Paragraph(_esc(value) or "—", S["fact"])]

    svc = _d(case.service_date_from) + ("" if case.service_date_to in (None, case.service_date_from) else f" to {_d(case.service_date_to)}")
    cells = [fact("Hospital", f"{case.hospital_name or 'Not matched'}" + (f" (CCN {case.ccn})" if case.ccn else "")),
             fact("Service dates", f"{svc} · {case.setting}"),
             fact("Insurer on the bill", case.payer_name or "None (self-pay)"),
             fact("Prepared for", f"{case.firm.name} · {REPORT_FOR.get(case.report_for, case.report_for)}")]
    t = Table([[c[0] for c in cells], [c[1] for c in cells]], colWidths=[CW * 0.31, CW * 0.23, CW * 0.2, CW * 0.26])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("LINEBELOW", (0, -1), (-1, -1), 1.2, ACCENT)]))
    story.append(t)


def _d(v) -> str:
    if not v:
        return "—"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return str(v)[:10]


def _key_number(story, r):
    """The number a reader looks for first: the strongest benchmark for a fair value."""
    rows = {x["key"]: x for x in r["summary"]}
    billed = rows.get("billed", {}).get("total")
    pick = next((rows[k] for k in ("eob_allowed", "payer_rate", "median") if k in rows and rows[k]["total"] is not None
                 and (k == "eob_allowed" or (rows[k].get("coverage_pct") or 0) >= 50)), None)
    if not billed or not pick:
        return
    label = {"eob_allowed": "Allowed by the insurer for this claim (EOB)", "payer_rate": "The hospital's own rate with this insurer",
             "median": "Median of the hospital's commercial insurer rates"}[pick["key"]]
    left = [Paragraph("BILLED", S["label"]), Paragraph(money(billed), ParagraphStyle("bb", parent=S["big"], textColor=BILLED))]
    right = [Paragraph(label.upper(), S["label"]), Paragraph(money(pick["total"]), S["big"]),
             Paragraph(f"{pick['pct_of_billed']} % of the billed charges" + (" on the same lines" if (pick.get("coverage_pct") or 100) < 100 else ""),
                       S["small"]) if pick.get("pct_of_billed") is not None else Spacer(1, 1)]
    t = Table([[left, right]], colWidths=[CW * 0.38, CW * 0.62])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 10),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 10), ("LINEAFTER", (0, 0), (0, 0), 0.6, LINE),
                           ("BOX", (0, 0), (-1, -1), 0.6, LINE)]))
    story += [Spacer(1, 12), t]


def _chart(r) -> Drawing | None:
    """Horizontal bars: each benchmark total against the billed charges."""
    rows = [x for x in r["summary"] if x["total"] is not None and (x["key"] == "billed" or x.get("pct_of_billed") is not None)]
    if len(rows) < 2:
        return None
    short = {"billed": "Billed", "eob_allowed": "Allowed (EOB)", "eob_paid": "Paid (EOB)", "payer_rate": "Insurer rate",
             "median": "Median (commercial)", "cash": "Cash price", "cost": "Hospital cost", "medicare": "Medicare"}
    bar_h, gap, lab_w, val_w = 12, 7, 118, 80
    h = len(rows) * (bar_h + gap) + 6
    d = Drawing(CW, h)
    track = CW - lab_w - val_w - 8
    for i, x in enumerate(rows):
        y = h - (i + 1) * (bar_h + gap)
        pct = 100 if x["key"] == "billed" else x["pct_of_billed"]
        frac = max(0.004, min(1.0, (pct or 0) / 100))
        d.add(String(0, y + 3, short.get(x["key"], x["key"]), fontName="Helvetica", fontSize=8, fillColor=INK))
        d.add(Rect(lab_w, y, track, bar_h, fillColor=SOFT, strokeColor=None))
        d.add(Rect(lab_w, y, track * frac, bar_h, fillColor=BILLED if x["key"] == "billed" else ACCENT, strokeColor=None))
        part = x["key"] != "billed" and (x.get("coverage_pct") or 100) < 100
        d.add(String(CW, y + 3, f"{money(x['total'])}  {pct} %" + ("*" if part else ""), fontName="Courier", fontSize=7.6,
                     fillColor=INK, textAnchor="end"))
    d.add(Line(lab_w, 0, lab_w, h - gap, strokeColor=LINE, strokeWidth=0.5))
    return d


def _summary_table(r):
    head = [Paragraph("BENCHMARK", S["lineh"]), Paragraph("TOTAL", S["linehr"]), Paragraph("% OF BILLED", S["linehr"])]
    rows = [head]
    for x in r["summary"]:
        strong = x["key"] in ("billed", "eob_allowed")
        rows.append([Paragraph(_esc(x["benchmark"]) + (f"<br/><font size='7.4' color='#5b6b73'>{_esc(x['note'])}</font>" if x.get("note") else ""),
                               S["cellb"] if strong else S["cell"]),
                     Paragraph(money(x["total"]), S["numb"] if strong else S["num"]),
                     Paragraph("—" if x["pct_of_billed"] is None else f"{x['pct_of_billed']} %", S["num"])])
    t = Table(rows, colWidths=[CW * 0.64, CW * 0.2, CW * 0.16], repeatRows=1)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 4.5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5), ("LEFTPADDING", (0, 0), (-1, -1), 4)]))
    return t


def _eob_block(story, r):
    e = r.get("eob")
    if not e:
        return
    t = e.get("totals") or {}
    items = [("Billed (on the EOB)", t.get("billed")), ("Network discount", t.get("discount")), ("Not covered", t.get("not_covered")),
             ("Allowed by the insurer", t.get("allowed")), ("Deductible", t.get("deductible")), ("Copay", t.get("copay")),
             ("Coinsurance", t.get("coinsurance")), ("Patient share", t.get("patient")), ("Paid by the insurer", t.get("paid"))]
    rows = [[Paragraph(k, S["cellb"] if k.startswith(("Allowed", "Paid")) else S["cell"]),
             Paragraph(money(v), S["numb"] if k.startswith(("Allowed", "Paid")) else S["num"])] for k, v in items if v is not None]
    who = _esc(e.get("payer") or "The insurer") + (f", claim {_esc(e['claim_number'])}" if e.get("claim_number") else "")
    how = (f"The EOB shows the stay as one line{(' (MS-DRG ' + e['ms_drg'] + ')') if e.get('ms_drg') else ''}." if e.get("level") == "stay"
           else f"{e.get('lines_matched')} of {e.get('bill_lines')} bill lines matched to the EOB.")
    tb = Table(rows, colWidths=[CW * 0.45, CW * 0.2])
    tb.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story.append(KeepTogether([Paragraph("Insurer's Explanation of Benefits", S["h2"]),
                               Paragraph(f"{who}. {how}", S["body"]), Spacer(1, 6), tb]))


def _stay_block(story, r):
    st = r.get("stay")
    if not (st and st.get("ms_drg")):
        return
    txt = (f"Valued as one MS-DRG: <b>{_esc(st['ms_drg'])}</b> {_esc(st.get('drg_title'))}"
           f"{(', ' + str(st['los_days']) + ' days') if st.get('los_days') is not None else ''}. "
           f"DRG {'confirmed by the reviewer' if st.get('drg_confirmed') else 'as shown on the bill, not yet confirmed'}."
           + (f" Medicare: {_esc(st['medicare_source'])}." if st.get("medicare_source") else "")
           + (f" Posted rates for this DRG range from {money(st['p10'])} (10th percentile) to {money(st['p90'])} (90th)." if st.get("p10") is not None else ""))
    story.append(KeepTogether([Paragraph("Inpatient stay", S["h2"]), Paragraph(txt, S["body"])]))


def _lines_table(r):
    lines = r["lines"]
    has_eob = any(ln.get("eob_allowed") is not None for ln in lines)
    cols = [("#", 0.03, False), ("Date", 0.088, False), ("Rev", 0.045, False), ("Code", 0.062, False), ("Qty", 0.035, True),
            ("Description", 0.0, False), ("Billed $", 0.083, True)] + ([("Allowed $ (EOB)", 0.083, True)] if has_eob else []) + \
           [("Insurer $", 0.083, True), ("Median $", 0.083, True), ("Medicare $", 0.083, True), ("Cost $", 0.083, True)]
    fixed = sum(w for _, w, _ in cols)
    widths = [(w if w else 1 - fixed) * CW for _, w, _ in cols]
    rows = [[Paragraph(c.upper(), S["linehr"] if right else S["lineh"]) for c, _, right in cols]]
    for ln in lines:
        pay = amt(ln["payer_rate"]) + ("*" if ln["payer_rate"] is not None and ln.get("payer_rate_is_estimate") else "")
        med = "pkg" if ln.get("medicare_status") == "packaged" and not ln["medicare"] else amt(ln["medicare"])
        vals = [str(ln["line_no"]), _d(ln["service_date"]), ln["revenue_code"] or "", (ln["hcpcs"] or "") + (f"-{ln['modifiers']}" if ln.get("modifiers") else ""),
                f"{ln['units']:g}" if ln.get("units") is not None else "", _esc(ln["description"]), amt(ln["charge"])] \
               + ([amt(ln.get("eob_allowed"))] if has_eob else []) + [pay, amt(ln["median"]), med, amt(ln["cost"])]
        rows.append([Paragraph(v, S["linen"] if cols[i][2] else S["line"]) for i, v in enumerate(vals)])
    if len(rows) == 1:
        rows.append([Paragraph("No priced lines yet.", S["line"])] + [""] * (len(cols) - 1))
    tot = lambda k: sum(ln[k] or 0 for ln in lines if ln.get(k) is not None) if any(ln.get(k) is not None for ln in lines) else None  # noqa: E731
    if lines:
        foot = ["", "", "", "", "", f"Total ({len(lines)} lines)", amt(tot("charge"))] + ([amt(tot("eob_allowed"))] if has_eob else []) \
               + [amt(tot("payer_rate")), amt(tot("median")), amt(tot("medicare")), amt(tot("cost"))]
        rows.append([Paragraph(f"<b>{v}</b>", S["linen"] if cols[i][2] else S["line"]) for i, v in enumerate(foot)])
    t = Table(rows, colWidths=widths, repeatRows=1)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK), ("TOPPADDING", (0, 0), (-1, -1), 2.6),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6), ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
    for i in range(2, len(rows) - (1 if lines else 0), 2):
        style.append(("BACKGROUND", (0, i), (-1, i), SOFT))
    if lines:
        style.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, INK))
    t.setStyle(TableStyle(style))
    return t


def _sources(r):
    rows = [[Paragraph("DATA", S["lineh"]), Paragraph("FILE", S["lineh"]), Paragraph("DATED", S["lineh"]), Paragraph("SHA-256 (first 16)", S["lineh"])]]
    for s in r["sources"] or [{"data": "No sources yet"}]:
        rows.append([Paragraph(_esc(s.get("data")), S["line"]), Paragraph(_esc(s.get("file_name") or ""), S["line"]),
                     Paragraph(_d(s.get("dated")) if s.get("dated") else "—", S["line"]),
                     Paragraph((s.get("sha256") or "")[:16] or "—", ParagraphStyle("h", parent=S["line"], fontName="Courier"))])
    t = Table(rows, colWidths=[CW * 0.3, CW * 0.38, CW * 0.11, CW * 0.21], repeatRows=1)
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK),
                           ("LINEBELOW", (0, 1), (-1, -1), 0.3, LINE), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    return t


def _signoff(story, r, draft):
    rv = r.get("reviewer") or {}
    if draft or not rv.get("approved_at"):
        txt = "<b>Draft.</b> This report has not been approved by a MeshKor reviewer. Do not rely on it or share it."
    else:
        txt = (f"<b>Reviewed and approved</b> by {_esc(rv.get('name'))}, MeshKor, on {_esc(_d(rv.get('approved_at')))}. "
               "The reviewer compared the bill lines, the hospital match and every flagged item with the documents uploaded for this case.")
    t = Table([[Paragraph(txt, S["body"])]], colWidths=[CW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT if not draft else colors.HexColor("#f6dfdb")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
    story += [Spacer(1, 14), t]


def build_pdf(case, r: dict, draft: bool) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=M, rightMargin=M, topMargin=0.7 * inch, bottomMargin=0.8 * inch,
                            title=f"{case.case_number} valuation report" + (" (draft)" if draft else ""), author="MeshKor",
                            subject="Reasonable value of hospital charges")
    story: list = []
    _band(story, r, case, draft)
    _key_number(story, r)
    story.append(Paragraph("1. Summary", S["h2"]))
    ch = _chart(r)
    if ch is not None:
        story += [ch, Paragraph("Each bar is the benchmark total as a share of the billed charges. * = the % compares only the lines "
                                "that have this benchmark (see the table).", S["small"]), Spacer(1, 8)]
    story += [_summary_table(r), Spacer(1, 8), Paragraph(_esc(r["summary_text"]), S["body"])]
    _eob_block(story, r)
    _stay_block(story, r)
    story += [CondPageBreak(2.2 * inch), Paragraph("2. Line by line", S["h2"]), _lines_table(r),
              Paragraph(("A hospital stay is valued as one MS-DRG (section 1); the line values are for reference. " if (r.get("stay") or {}).get("ms_drg") else "")
                        + "* estimate (percentage contract, or price file outside the date of service) · pkg = packaged into another "
                        "Medicare payment · — = no value", S["small"]),
              CondPageBreak(1.8 * inch), Paragraph("3. Sources", S["h2"]), _sources(r),
              KeepTogether([Paragraph("4. Method", S["h2"]), Paragraph(_esc(r["method"]), S["body"])]),
              KeepTogether([Paragraph("5. Limits", S["h2"]), Paragraph(_esc(r["limits"]), S["body"])])]
    _signoff(story, r, draft)
    story.append(Paragraph(f"Generated {_esc(r['generated_at'][:19].replace('T', ' '))} UTC by MeshKor Lien Valuation.", S["small"]))
    doc.build(story, canvasmaker=lambda *a, **kw: NumberedCanvas(*a, case_number=case.case_number, draft=draft, **kw))
    return buf.getvalue()

