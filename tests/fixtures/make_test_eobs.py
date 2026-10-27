r"""Make the synthetic test EOBs (insurer statements) that go with the synthetic test bills.

    python tests\fixtures\make_test_eobs.py

Every page is marked as test data. No real patient, no real claim. The allowed amounts are invented
test values. Three layouts, as insurers print them differently:
  B01  Anthem            line by line: billed, allowed, deductible, copay, coinsurance, plan paid, you owe
  B07  Medical Mutual    line by line, other column order: charges, discount, allowed, not covered, ...
  B08  UnitedHealthcare  inpatient: the whole stay on one line (DRG 481)
"""
from __future__ import annotations

import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from reportlab.lib import colors                     # noqa: E402
from reportlab.lib.pagesizes import letter, landscape  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import inch                  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from pipeline.lien import reader                      # noqa: E402

BILLS = ROOT / "tests" / "fixtures" / "test_bills"
OUT = ROOT / "tests" / "fixtures" / "test_eobs"
C = Decimal("0.01")
PAGE = landscape(letter)


def q(x) -> Decimal:
    return Decimal(x).quantize(C, ROUND_HALF_UP)


def m(x) -> str:
    return f"${q(x):,.2f}"


def mark(c, doc):
    c.saveState()
    c.setFillColor(colors.Color(0.85, 0.1, 0.1, alpha=0.18))
    c.setFont("Helvetica-Bold", 36)
    c.translate(PAGE[0] / 2, PAGE[1] / 2)
    c.rotate(25)
    c.drawCentredString(0, 0, "TEST DATA - NOT A REAL EOB")
    c.restoreState()
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.grey)
    c.drawString(0.5 * inch, 0.4 * inch, "Synthetic test EOB made by MeshKor for software testing. No real patient, no real claim.")


def share(allowed: Decimal, ded_left: Decimal, coins: Decimal, copay: Decimal = Decimal(0)):
    """Deductible first, then copay, then coinsurance on the rest."""
    ded = min(ded_left, allowed)
    cp = min(copay, allowed - ded)
    co = q((allowed - ded - cp) * coins)
    return ded, cp, co, allowed - ded - cp - co


def build(path: Path, title: str, head: list[list[str]], cols: list[str], rows: list[list[str]], total: list[str], widths):
    st = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=PAGE, leftMargin=0.5 * inch, rightMargin=0.5 * inch, topMargin=0.5 * inch,
                            bottomMargin=0.6 * inch, title=f"{path.stem} synthetic test EOB", author="MeshKor test data")
    banner = Table([["SYNTHETIC TEST DATA  -  NOT A REAL EOB"]], colWidths=[10 * inch])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#c62828")), ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    info = Table(head, colWidths=[1.4 * inch, 3.6 * inch, 1.4 * inch, 3.6 * inch])
    info.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 8.5), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                              ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold")]))
    data = [cols] + rows + [total]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7.5), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
                           ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.black), ("ALIGN", (3, 1), (-1, -1), "RIGHT")]))
    doc.build([banner, Spacer(1, 6), Paragraph(title, st["Title"]),
               Paragraph("EXPLANATION OF BENEFITS - THIS IS NOT A BILL", st["Heading4"]), info, Spacer(1, 10), t],
              onFirstPage=mark, onLaterPages=mark)


def bill(b):
    return reader.read((BILLS / f"{b}_TEST_bill.pdf").read_bytes(), f"{b}.pdf")


def b01():
    """Anthem, line by line. Deductible $500, 20 % coinsurance."""
    bl = bill("B01")
    allowed = ["1450.00", "826.00", "872.40", "97.00", "18.00", "9.00", "12.50", "210.00", "6.50", "0.40", "0.00"]
    notes = {11: "D7"}          # D7 = included in another service
    rows, tot = [], [Decimal(0)] * 7
    left = Decimal(500)
    for ln, a in zip(bl.lines, allowed):
        a = Decimal(a)
        ded, cp, co, paid = share(a, left, Decimal("0.20"))
        left -= ded
        vals = [ln.charge, a, ded, cp, co, paid, ded + cp + co]
        tot = [x + y for x, y in zip(tot, vals)]
        rows.append([ln.service_date.strftime("%m/%d/%Y"), ln.hcpcs, ln.description[:34]] + [m(v) for v in vals] + [notes.get(ln.line_no, "")])
    build(OUT / "B01_TEST_eob.pdf", "Anthem Blue Cross and Blue Shield",
          [["Member", "TEST PATIENT B01", "Member ID", "TEST-ID-B01"],
           ["Claim number", "TEST-CLM-B01", "Claim processed", "09/02/2026"],
           ["Provider", "OHIO STATE UNIVERSITY HOSPITALS", "Dates of service", "08/14/2026 - 08/14/2026"],
           ["Plan", "Anthem Blue Access PPO", "Network", "In network"]],
          ["Date of service", "Service", "Description", "Billed", "Allowed", "Deductible", "Copay", "Coinsurance", "Plan paid", "You owe", "Notes"],
          rows, ["Total", "", ""] + [m(v) for v in tot] + [""],
          [0.95 * inch, 0.55 * inch, 2.2 * inch] + [0.8 * inch] * 7 + [0.5 * inch])


def b07():
    """Medical Mutual, another column order, with discount and not covered; 2-digit years."""
    bl = bill("B07")
    allowed = ["6200.00", "0", "0", "2900.00", "140.00", "0.40", "0"]
    rows, tot = [], [Decimal(0)] * 8
    left = Decimal(250)
    for ln, a in zip(bl.lines, allowed):
        a = Decimal(a)
        nc = ln.charge if a == 0 else Decimal(0)
        disc = ln.charge - a - nc
        ded, cp, co, paid = share(a, left, Decimal("0.10"))
        left -= ded
        vals = [ln.charge, disc, a, nc, ded, co, paid, ded + co]
        tot = [x + y for x, y in zip(tot, vals)]
        rows.append([ln.service_date.strftime("%m/%d/%y"), ln.revenue_code, ln.hcpcs] + [m(v) for v in vals] + ["N20" if nc else ""])
    build(OUT / "B07_TEST_eob.pdf", "Medical Mutual of Ohio",
          [["Patient", "TEST PATIENT B07", "Claim #", "TEST-CLM-B07"],
           ["Facility", "OHIO STATE UNIVERSITY HOSPITALS", "Service dates", "08/20/26 - 08/20/26"],
           ["Health plan", "Medical Mutual SuperMed PPO", "Processed", "09/10/26"]],
          ["Service Date", "Rev", "Proc", "Charges", "Discount", "Allowed", "Not Covered", "Deductible", "Coinsurance", "Paid", "Patient Resp", "Remark"],
          rows, ["Claim Total", "", ""] + [m(v) for v in tot] + [""],
          [0.85 * inch, 0.45 * inch, 0.5 * inch] + [0.85 * inch] * 8 + [0.5 * inch])


def b08():
    """UnitedHealthcare, inpatient: one line for the stay (DRG 481). Deductible $1,500."""
    bl = bill("B08")
    billed = bl.lines_total
    a = Decimal("47909.59")
    ded, cp, co, paid = share(a, Decimal(1500), Decimal(0))
    vals = [billed, a, ded, cp, co, paid, ded + cp + co]
    rows = [[f"{bl.date_from:%m/%d/%Y} - {bl.date_to:%m/%d/%Y}", "DRG 481", "INPATIENT HOSPITAL STAY"] + [m(v) for v in vals] + ["IP1"]]
    build(OUT / "B08_TEST_eob.pdf", "UnitedHealthcare",
          [["Member", "TEST PATIENT B08", "Member ID", "TEST-ID-B08"],
           ["Claim number", "TEST-CLM-B08", "Claim processed", "08/05/2026"],
           ["Provider", "OHIO STATE UNIVERSITY HOSPITALS", "Dates of service", f"{bl.date_from:%m/%d/%Y} - {bl.date_to:%m/%d/%Y}"],
           ["Plan", "UnitedHealthcare Choice Plus", "", ""]],
          ["Date of service", "Service", "Description", "Billed", "Allowed", "Deductible", "Copay", "Coinsurance", "Plan paid", "You owe", "Notes"],
          rows, ["Total", "", ""] + [m(v) for v in vals] + [""],
          [1.5 * inch, 0.6 * inch, 1.6 * inch] + [0.8 * inch] * 7 + [0.5 * inch])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    b01(); b07(); b08()
    print("Made:", ", ".join(p.name for p in sorted(OUT.glob("*.pdf"))))
