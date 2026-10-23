"""Read a hospital bill (PDF with a text layer) into header fields and lines.

Works on itemized statements and UB-04 style line lists that a hospital
billing system prints to PDF. Each line must show, in this order:
    [line no]  date  revenue code  [HCPCS/CPT]  units  description  charge
A scanned bill (an image, or a PDF with no text layer) raises BillNotReadable;
reading scans needs OCR, which is a separate decision (PHI leaves the server
with most OCR services).

Nothing here touches Django or the database, so it can be tested alone.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


class BillNotReadable(Exception):
    """The file has no text we can read (scan, image, password, broken PDF)."""


@dataclass
class BillLine:
    line_no: int
    service_date: date | None
    revenue_code: str
    hcpcs: str
    modifiers: str
    units: Decimal
    description: str
    charge: Decimal
    confidence: float


@dataclass
class Bill:
    facility_name: str = ""
    ccn: str = ""
    npi: str = ""
    type_of_bill: str = ""
    ms_drg: str = ""
    date_from: date | None = None
    date_to: date | None = None
    payer: str = ""
    reason: str = ""
    stated_total: Decimal | None = None
    lines: list[BillLine] = field(default_factory=list)
    diagnoses: list[str] = field(default_factory=list)
    pages: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def lines_total(self) -> Decimal:
        return sum((ln.charge for ln in self.lines), Decimal("0"))

    @property
    def inpatient(self) -> bool:
        tob = self.type_of_bill.lstrip("0")
        return tob[:2] in ("11", "12") or bool(self.ms_drg)


# ----------------------------------------------------------------------------- text

def pdf_text(data: bytes) -> tuple[list[str], int]:
    """Text lines of every page. Large characters (watermarks, logos) are dropped."""
    import pdfplumber
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001 — pdfminer raises many kinds
        raise BillNotReadable(f"The file is not a readable PDF ({type(e).__name__}).") from e
    lines: list[str] = []
    with pdf:
        n = len(pdf.pages)
        for page in pdf.pages:
            page = page.filter(lambda o: o.get("object_type") != "char" or (o.get("size") or 0) < 20)
            text = page.extract_text() or ""
            lines += [ln.strip() for ln in text.splitlines() if ln.strip()]
    if sum(len(x) for x in lines) < 40:
        raise BillNotReadable("The PDF has no text layer (it is a scan or a photo). Reading scans is not set up yet.")
    return lines, n


# ----------------------------------------------------------------------------- parsing

DATE = r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
MONEY = r"\(?-?\$?\s?-?[\d,]+\.\d{2}\)?"
LINE_RX = re.compile(
    rf"^(?:(?P<no>\d{{1,4}})\s+)?(?P<date>{DATE})\s+(?P<rev>\d{{3,4}})\s+"
    rf"(?:(?P<code>[A-Z]?\d{{4}}[A-Z0-9]?|\d{{5}})(?:[\s-]+(?P<mods>(?:[A-Z0-9]{{2}}\s?){{1,4}}))?\s+)?"
    rf"(?P<units>\d{{1,5}}(?:\.\d{{1,2}})?)\s+(?P<desc>.+?)\s+(?P<charge>{MONEY})$")
TOTAL_RX = re.compile(rf"^(?:TOTAL CHARGES|TOTAL BILLED|TOTAL|GRAND TOTAL|TOTALS)\b[:\s]*(?P<amt>{MONEY})$", re.I)
HEADER_RX = re.compile(r"^#?\s*(?:line\s+)?date\b.*\b(rev|revenue)\b", re.I)

LABELS = {
    "facility_name": r"(?:Facility|Hospital|Provider)(?: name)?",
    "ccn": r"(?:CCN|Medicare (?:provider )?(?:number|no\.?)|Provider number)",
    "npi": r"(?:Facility NPI|Billing NPI|NPI)",
    "type_of_bill": r"(?:Type of bill|TOB|Bill type)",
    "ms_drg": r"(?:MS-DRG|DRG)",
    "payer": r"(?:Primary payer|Payer|Insurance|Primary insurance|Plan)",
    "reason": r"(?:Reason for visit|Reason|Visit reason)",
    "dates": r"(?:Service dates|Statement covers period|Dates of service|Service period|From)",
}
STOP = r"(?=\s+(?:Statement no\.|Account no\.|(?:Facility NPI|NPI|MS-DRG|DRG|Primary payer|Payer|Patient)\b)|$)"


def _date(s: str | None) -> date | None:
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _money(s: str) -> Decimal:
    neg = s.strip().startswith("(") or "-" in s
    v = Decimal(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


def _field(text: str, label: str) -> str:
    m = re.search(rf"(?:^|\s){label}[:#]?\s+(.+?){STOP}", text, re.I)
    return m.group(1).strip() if m else ""


def parse_header(lines: list[str], bill: Bill) -> None:
    head = []
    for ln in lines:
        if HEADER_RX.match(ln) or LINE_RX.match(ln):
            break
        head.append(ln)
    for ln in head:
        if not bill.facility_name:
            bill.facility_name = _field(ln, LABELS["facility_name"])
        if not bill.ccn:
            m = re.search(rf"{LABELS['ccn']}[:#]?\s+(\d{{2}}[0-9A-Z]\d{{3}})\b", ln, re.I)
            bill.ccn = m.group(1) if m else ""
        if not bill.npi:
            m = re.search(rf"{LABELS['npi']}[:#]?\s+(\d{{10}})\b", ln, re.I)
            bill.npi = m.group(1) if m else ""
        if not bill.type_of_bill:
            m = re.search(rf"{LABELS['type_of_bill']}[:#]?\s+(0?\d{{3}})\b", ln, re.I)
            bill.type_of_bill = m.group(1).zfill(4) if m else ""
        if not bill.ms_drg:
            m = re.search(rf"{LABELS['ms_drg']}[:#]?\s+(\d{{3}})\b", ln, re.I)
            bill.ms_drg = m.group(1) if m else ""
        if not bill.payer:
            bill.payer = _field(ln, LABELS["payer"])
        if not bill.reason:
            bill.reason = _field(ln, LABELS["reason"])
        if not bill.date_from:
            m = re.search(rf"{LABELS['dates']}[:#]?\s+{DATE}(?:\s*(?:to|-|through|thru)\s*{DATE})?", ln, re.I)
            if m:
                bill.date_from, bill.date_to = _date(m.group(1)), _date(m.group(2) or m.group(1))
        for code in re.findall(r"\b(?:Dx|Diagnosis|ICD-10)[^:]*:\s*([A-Z]\d{2}\.?[0-9A-Z]{0,4})", ln, re.I):
            bill.diagnoses.append(code.replace(".", "").upper())
    if bill.facility_name.startswith("("):
        bill.facility_name = ""


def parse_lines(lines: list[str], bill: Bill) -> None:
    n = 0
    in_table = False
    for ln in lines:
        if HEADER_RX.match(ln):
            in_table = True
            continue
        m = LINE_RX.match(ln)
        if m:
            in_table = True
            n += 1
            code = (m.group("code") or "").upper()
            rev = m.group("rev").zfill(4)
            conf = 0.98
            try:
                units = Decimal(m.group("units"))
                charge = _money(m.group("charge"))
            except InvalidOperation:
                units, charge, conf = Decimal("1"), Decimal("0"), 0.4
            if units <= 0 or units > 999:
                conf = min(conf, 0.7)
            if m.group("no") and int(m.group("no")) != n:
                conf = min(conf, 0.8)   # a line number was skipped: a line may be missing
            bill.lines.append(BillLine(
                line_no=n, service_date=_date(m.group("date")), revenue_code=rev, hcpcs=code,
                modifiers=" ".join((m.group("mods") or "").split()), units=units,
                description=m.group("desc").strip()[:300], charge=charge, confidence=conf))
            continue
        t = TOTAL_RX.match(ln)
        if t and in_table:
            bill.stated_total = _money(t.group("amt"))
            in_table = False
            continue
        # A wrapped description: short upper-case text right after a line
        if in_table and bill.lines and len(ln) <= 40 and not re.search(r"\d{2,}", ln) and ln.upper() == ln:
            last = bill.lines[-1]
            last.description = f"{last.description} {ln}"[:300]


def read_pdf(data: bytes) -> Bill:
    lines, pages = pdf_text(data)
    bill = Bill(pages=pages)
    parse_header(lines, bill)
    parse_lines(lines, bill)
    if not bill.lines:
        raise BillNotReadable("No bill lines were found. The layout is not one the reader knows yet.")
    dates = [ln.service_date for ln in bill.lines if ln.service_date]
    if dates:
        bill.date_from = bill.date_from or min(dates)
        bill.date_to = bill.date_to or max(dates)
    return bill


def read(data: bytes, name: str) -> Bill:
    if name.lower().endswith(".pdf") or data[:5] == b"%PDF-":
        return read_pdf(data)
    raise BillNotReadable("The bill is an image. Reading scans and photos is not set up yet; upload the PDF from the hospital.")
