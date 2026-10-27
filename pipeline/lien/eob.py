"""Read the insurer's EOB (Explanation of Benefits) and match it to the bill.

An EOB says, per service: what the hospital billed, what the insurer ALLOWED (its contract amount),
what the insurer PAID, and what the patient owes (deductible, copay, coinsurance). For a lien, the
allowed amount is the strongest fact: the insurer's own price for this very claim.

Accepted files: the same as bills (text PDF, scanned PDF, JPG/PNG/TIFF by local OCR, Word).

How a page is read:
  1. The column header line names the money columns ("Billed  Allowed  Deductible ... Plan paid  You owe").
     Insurers print them in different orders; the order on the page decides which amount is which.
  2. A service line starts with a date (or a date range), may show a revenue code, a CPT/HCPCS code
     or "DRG nnn", then a description, then one amount per money column, then remark codes.
  3. A "Total" line gives the insurer's own totals, used as a check.
  4. Header fields: insurer, claim number, provider, dates of service. Member name and ID are NOT kept.

Matching to the bill: the same date and the same code (CPT/HCPCS, else revenue code), the same charge
breaking ties; then the same date and the same charge. An inpatient EOB often shows the stay as one
line (DRG): then only the totals are compared.

Nothing here touches Django or the database, so it can be tested alone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from . import reader
from .reader import DATE, BillNotReadable, _date

ZERO = Decimal("0")


class EobNotReadable(Exception):
    pass


# The money columns an EOB can have. The patterns are tried longest first, so "plan paid" wins over "paid".
COLUMNS = {
    "billed": r"amount billed|billed amount|amount charged|total charges?|provider charges?|charges?|charged|billed|submitted",
    "discount": r"network discount|network savings|plan discount|discount|savings|amount saved|provider adjustment",
    "allowed": r"amount allowed|allowed amount|allowable|allowed|approved amount|approved|eligible amount|eligible",
    "not_covered": r"not covered|non-covered|noncovered|amount not covered|ineligible|not allowed",
    "deductible": r"deductible",
    "copay": r"co-?payments?|co-?pays?",
    "coinsurance": r"co-?insurance",
    "paid": r"plan paid|amount paid|insurer paid|we paid|plan payment|benefit paid|payment amount|paid amount|paid|payment",
    "patient": r"patient responsibility|patient resp\.?|patient owes|patient share|member responsibility|member resp\.?|"
               r"your responsibility|you owe|what you owe|your share|amount you owe",
}
_ALT = sorted(((p, k) for k, pats in COLUMNS.items() for p in pats.split("|")), key=lambda x: -len(x[0]))
HEAD_RX = re.compile("|".join(f"(?P<c{i}>\\b{p}\\b)" for i, (p, _k) in enumerate(_ALT)), re.I)
AMOUNT = r"\(?-?\$?\s?\d[\d,]*\.\d{2}\)?"
AMOUNT_RX = re.compile(AMOUNT)
LINE_RX = re.compile(rf"^(?P<d1>{DATE})(?:\s*(?:-|to|thru|through)\s*(?P<d2>{DATE}))?\s+(?P<rest>.*?{AMOUNT}.*)$", re.I)
TOTAL_RX = re.compile(rf"^[\W_]*(?:claim\s+)?totals?\b(?:\s+for\s+this\s+claim)?[:\s]*(?P<rest>.*{AMOUNT}.*)$", re.I)
DRG_RX = re.compile(r"\b(?:MS-)?DRG[:#]?\s*(\d{3})\b", re.I)
REV_RX = re.compile(r"^0\d{3}$")
CODE_RX = re.compile(r"^(?:[A-Z]\d{4}|\d{4}[A-Z0-9])$")


@dataclass
class EobLine:
    line_no: int
    date_from: date | None
    date_to: date | None
    revenue_code: str
    hcpcs: str
    ms_drg: str
    description: str
    amounts: dict                  # column -> Decimal (billed, allowed, paid, patient, ...)
    confidence: float
    remark: str = ""

    def get(self, k):
        return self.amounts.get(k)


@dataclass
class Eob:
    payer: str = ""
    plan: str = ""
    claim_number: str = ""
    provider: str = ""
    date_from: date | None = None
    date_to: date | None = None
    ms_drg: str = ""
    columns: list[str] = field(default_factory=list)
    lines: list[EobLine] = field(default_factory=list)
    stated_totals: dict = field(default_factory=dict)
    looks_like_eob: bool = False
    method: str = "text"
    ocr_score: float | None = None
    notes: list[str] = field(default_factory=list)

    def total(self, k) -> Decimal | None:
        vals = [ln.get(k) for ln in self.lines]
        if not any(v is not None for v in vals):
            return self.stated_totals.get(k)
        return sum((v for v in vals if v is not None), ZERO)


# ----------------------------------------------------------------------------- parsing

def _amount(s: str) -> Decimal:
    neg = s.strip().startswith("(") or "-" in s
    v = Decimal(re.sub(r"[^\d.]", "", s))
    return -v if neg else v


def header_columns(line: str) -> list[str]:
    """The money columns named on a header line, in page order (each once)."""
    cols = []
    for m in HEAD_RX.finditer(line):
        i = int(next(k for k, v in m.groupdict().items() if v)[1:])
        k = _ALT[i][1]
        if k not in cols:
            cols.append(k)
    return cols


LABELS = {
    "payer": r"(?:Insurer|Insurance company|Health plan|Plan name|Payer|Insurance carrier|Carrier)",
    "plan": r"(?:Plan|Group plan|Product)",
    "claim": r"(?:Claim (?:number|no\.?|#|ID)|Claim)",
    "provider": r"(?:Provider|Facility|Hospital|Billed by|Provider name|Service provider)",
    "dates": r"(?:Dates? of service|Service dates?|Service period|Date\(s\) of service)",
}
STOP = (r"(?=\s+(?:Member|Patient|Claim|Provider|Facility|Plan|Health plan|Group|Network|Processed|Claim processed|Dates?|"
        r"Service dates?|ID|Account)\b|$)")


def _field(text: str, label: str) -> str:
    m = re.search(rf"(?:^|\s){label}[:#]?\s+(.+?){STOP}", text, re.I)
    return m.group(1).strip(" :#") if m else ""


def parse(lines: list[str], scores: list[float] | None = None) -> Eob:
    eob = Eob()
    text = "\n".join(lines)
    eob.looks_like_eob = bool(re.search(r"explanation of benefits|this is not a bill|\bEOB\b|remittance|claim (?:number|#|no)", text, re.I))
    cols: list[str] = []
    head_done = False
    n = 0
    for idx, ln in enumerate(lines):
        sc = scores[idx] if scores else None
        hc = header_columns(ln)
        if len(hc) >= 3 and not AMOUNT_RX.search(ln) and not LINE_RX.match(ln):
            cols, head_done = hc, True
            continue
        if not head_done:
            for k, key in (("payer", "payer"), ("plan", "plan"), ("claim", "claim_number"), ("provider", "provider")):
                if not getattr(eob, key):
                    v = _field(ln, LABELS[k])
                    if key == "claim_number":
                        v = (re.match(r"[A-Z0-9][A-Z0-9-]{3,}", v, re.I) or [""])[0]
                    setattr(eob, key, v[:200])
            if not eob.date_from:
                m = re.search(rf"{LABELS['dates']}[:#]?\s+{DATE}(?:\s*(?:-|to|thru|through)\s*{DATE})?", ln, re.I)
                if m:
                    eob.date_from, eob.date_to = _date(m.group(1)), _date(m.group(2) or m.group(1))
        t = TOTAL_RX.match(ln)
        if t and cols:
            amts = [_amount(a) for a in AMOUNT_RX.findall(t.group("rest"))]
            eob.stated_totals = _map(amts, cols)[0]
            continue
        m = LINE_RX.match(ln)
        if not m:
            continue
        rest = m.group("rest")
        first = AMOUNT_RX.search(rest)
        lead, tail = rest[:first.start()].strip(), rest[first.start():]
        amts = [_amount(a) for a in AMOUNT_RX.findall(tail)]
        remark = AMOUNT_RX.sub(" ", tail).strip()
        rev = code = drg = ""
        d = DRG_RX.search(lead)
        if d:
            drg = d.group(1)
            lead = (lead[:d.start()] + lead[d.end():]).strip()
        toks = lead.split()
        while toks and (REV_RX.match(toks[0]) or CODE_RX.match(toks[0].upper())):
            tk = toks.pop(0).upper()
            if REV_RX.match(tk) and not rev:
                rev = tk
            elif not code:
                code = tk
        n += 1
        mapped, ok = _map(amts, cols)
        conf = 0.98 if ok else 0.5
        if sc is not None:
            conf = min(conf, sc, 0.95)
        if not ok:
            eob.notes.append(f"EOB line {n}: {len(amts)} amounts for {len(cols) or 'no'} named columns")
        eob.lines.append(EobLine(line_no=n, date_from=_date(m.group("d1")), date_to=_date(m.group("d2") or m.group("d1")),
                                 revenue_code=rev, hcpcs=code, ms_drg=drg, description=" ".join(toks)[:200],
                                 amounts=mapped, confidence=round(conf, 2), remark=remark[:40]))
    eob.columns = cols
    drgs = {ln.ms_drg for ln in eob.lines if ln.ms_drg}
    m = DRG_RX.search(text)
    eob.ms_drg = (drgs.pop() if len(drgs) == 1 else "") or (m.group(1) if m else "")
    dates = [d for ln in eob.lines for d in (ln.date_from, ln.date_to) if d]
    if dates:
        eob.date_from, eob.date_to = eob.date_from or min(dates), eob.date_to or max(dates)
    if not eob.payer:
        eob.payer = _payer_from_top(lines)
    if scores is not None and eob.lines:
        eob.ocr_score = min(ln.confidence for ln in eob.lines)
    return eob


def _map(amts: list[Decimal], cols: list[str]) -> tuple[dict, bool]:
    """Amounts to columns, in page order. With no header, or a count that does not fit, only the safe
    reading is kept: the first amount is the billed charge."""
    if cols and len(amts) == len(cols):
        out = dict(zip(cols, amts))
    elif cols and len(amts) > len(cols):
        out = dict(zip(cols, amts[:len(cols)]))          # extra amounts (e.g. a remark with cents) are dropped
        return _derive(out), False
    else:
        return ({"billed": amts[0]} if amts else {}), False
    return _derive(out), True


def _derive(a: dict) -> dict:
    if "patient" not in a and any(k in a for k in ("deductible", "copay", "coinsurance")):
        a["patient"] = sum((a.get(k) or ZERO for k in ("deductible", "copay", "coinsurance")), ZERO)
    return a


def _payer_from_top(lines: list[str]) -> str:
    """No "Insurer:" label: the first top line that names a known insurer (config/payer_groups.yaml)."""
    from ..ref.hospital_mrf import payer_group
    for ln in lines[:12]:
        if AMOUNT_RX.search(ln) or len(ln) > 80 or re.search(r"test data|not a real|explanation of benefits", ln, re.I):
            continue
        if payer_group(ln, "") not in ("Other", "Self-pay"):
            return ln.strip()[:200]
    return ""


# ----------------------------------------------------------------------------- files

def read(data: bytes, name: str = "") -> Eob:
    k = reader.kind_of(data, name)
    try:
        if k == "pdf":
            lines, _pages = reader.pdf_text(data)
            if sum(len(x) for x in lines) >= 40:
                eob = parse(lines)
                if eob.lines:
                    return _check(eob)
            from . import ocr
            ol, _n = ocr.pdf_lines(data)
            eob = parse([o.text for o in ol], [o.score for o in ol])
            eob.method = "ocr"
            return _check(eob)
        if k in ("png", "jpg", "tiff"):
            from . import ocr
            ol = ocr.image_bytes_lines(data)
            eob = parse([o.text for o in ol], [o.score for o in ol])
            eob.method = "ocr"
            return _check(eob)
        if k == "docx":
            lines, pics = reader.docx_text(data)
            eob = parse(lines)
            eob.method = "docx"
            if not eob.lines and pics:
                from . import ocr
                ol = [o for p in pics for o in ocr.image_bytes_lines(p)]
                eob = parse(lines + [o.text for o in ol], [1.0] * len(lines) + [o.score for o in ol])
                eob.method = "docx+ocr"
            return _check(eob)
    except (BillNotReadable, EobNotReadable) as e:
        raise EobNotReadable(str(e)) from e
    except ImportError:
        raise
    except Exception as e:  # noqa: BLE001 — PDF and image libraries raise many kinds
        raise EobNotReadable(f"the file could not be opened ({type(e).__name__})") from e
    raise EobNotReadable("the file is not a PDF, JPG, PNG, TIFF or Word (.docx) file")


def _check(eob: Eob) -> Eob:
    if not eob.lines:
        raise EobNotReadable("no service lines were found" + ("" if eob.looks_like_eob else "; the file does not look like an EOB"))
    if "allowed" not in eob.columns and "paid" not in eob.columns:
        raise EobNotReadable("no Allowed or Paid column was found" + ("" if eob.looks_like_eob else "; the file does not look like an EOB"))
    return eob


# ----------------------------------------------------------------------------- matching

def match(eob: Eob, bill_lines) -> dict[int, EobLine]:
    """bill line_no -> EOB line. One to one. Lines of a DRG-level EOB match nothing."""
    out: dict[int, EobLine] = {}
    used: set[int] = set()
    items = [e for e in eob.lines if not e.ms_drg]

    def same_day(e, b):
        return b.service_date is None or e.date_from is None or (e.date_from <= b.service_date <= (e.date_to or e.date_from))

    def same_code(e, b):
        if e.hcpcs and b.hcpcs:
            return e.hcpcs == b.hcpcs
        if e.revenue_code and b.revenue_code:
            return e.revenue_code == b.revenue_code and (not e.hcpcs or not b.hcpcs)
        return e.hcpcs == b.revenue_code or e.revenue_code == b.hcpcs

    def charge(e):
        return e.get("billed")

    for rule in (lambda e, b: same_day(e, b) and same_code(e, b) and charge(e) == b.charge,
                 lambda e, b: same_day(e, b) and same_code(e, b),
                 lambda e, b: same_day(e, b) and charge(e) is not None and charge(e) == b.charge and not (e.hcpcs and b.hcpcs)):
        for b in bill_lines:
            if b.line_no in out:
                continue
            for e in items:
                if e.line_no not in used and rule(e, b):
                    out[b.line_no] = e
                    used.add(e.line_no)
                    break
    return out


# ----------------------------------------------------------------------------- result for the case

def compare(eob: Eob, bill, payer_group_of_bill: str, payer_rate_by_line: dict[int, float | None] | None = None,
            payer_rate_total: float | None = None) -> tuple[dict, dict[int, dict], list[dict]]:
    """Returns (summary for Case.eob, per bill line {eob_allowed, eob_paid, eob_patient}, flags)."""
    from ..ref.hospital_mrf import payer_group
    f = lambda v: float(v) if v is not None else None   # noqa: E731
    m = match(eob, bill.lines)
    per_line = {no: {"eob_allowed": f(e.get("allowed")), "eob_paid": f(e.get("paid")), "eob_patient": f(e.get("patient"))}
                for no, e in m.items()}
    totals = {k: f(eob.total(k)) for k in ("billed", "discount", "allowed", "not_covered", "deductible", "copay", "coinsurance", "paid", "patient")}
    group = payer_group(eob.payer, eob.plan) if (eob.payer or eob.plan) else ""
    drg_level = bool(eob.lines) and all(ln.ms_drg for ln in eob.lines)
    summary = {
        "payer": eob.payer or None, "plan": eob.plan or None, "payer_group": group or None,
        "claim_number": eob.claim_number or None, "provider": eob.provider or None,
        "date_from": eob.date_from.isoformat() if eob.date_from else None, "date_to": eob.date_to.isoformat() if eob.date_to else None,
        "ms_drg": eob.ms_drg or None, "level": "stay" if drg_level else "line",
        "columns": eob.columns, "method": eob.method, "ocr_score": eob.ocr_score,
        "totals": totals, "lines": len(eob.lines), "lines_matched": len(m), "bill_lines": len(bill.lines),
    }
    flags: list[dict] = []
    who = eob.payer or "the insurer"
    a, p, pt, b = totals["allowed"], totals["paid"], totals["patient"], totals["billed"]
    flags.append({"kind": "eob", "severity": "info", "line_no": None,
                  "title": f"EOB read: {who} allowed {_m(a)}, paid {_m(p)}" + (f", patient share {_m(pt)}" if pt is not None else ""),
                  "detail": (f"Claim {eob.claim_number}. " if eob.claim_number else "")
                            + (f"The EOB shows the stay as one line (MS-DRG {eob.ms_drg}); totals compared only. " if drg_level
                               else f"{len(m)} of {len(bill.lines)} bill lines matched to the EOB. ")
                            + "Member name and ID are not stored."})
    if eob.method != "text":
        flags.append({"kind": "eob", "severity": "check" if "ocr" in eob.method else "info", "line_no": None,
                      "title": "EOB read " + ("by OCR: compare the amounts with the EOB" if "ocr" in eob.method else "from a Word file"),
                      "detail": (f"Lowest line certainty {round((eob.ocr_score or 0) * 100)} %. " if eob.ocr_score is not None else "")
                                + "Check the allowed and paid totals."})
    if eob.notes:
        flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": "Some EOB lines were not read in full",
                      "detail": " ".join(eob.notes[:6]) + ". Only the billed amount is kept on those lines."})
    st = eob.stated_totals
    for k in ("allowed", "paid"):
        if st.get(k) is not None and totals[k] is not None and abs(Decimal(str(totals[k])) - st[k]) > Decimal("0.05"):
            flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": f"EOB lines do not add up to its own {k} total",
                          "detail": f"Lines: {_m(totals[k])}; total line: {_m(st[k])}. A line may be missing or misread."})
    bill_total = float(bill.lines_total)
    if b is not None and abs(b - bill_total) > 0.5:
        flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": "The EOB billed total differs from the bill",
                      "detail": f"EOB billed {_m(b)}; bill {_m(bill_total)}. The EOB may cover only part of the bill, or a different claim."})
    if group and payer_group_of_bill and group != payer_group_of_bill and group not in ("Other",) and payer_group_of_bill not in ("Other",):
        flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": f"EOB is from {eob.payer}, the bill names {payer_group_of_bill}",
                      "detail": "Check that the EOB belongs to this bill (secondary insurer, or the wrong file)."})
    if bill.date_from and eob.date_from and (eob.date_from > (bill.date_to or bill.date_from) or (eob.date_to or eob.date_from) < bill.date_from):
        flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": "EOB dates of service do not overlap the bill",
                      "detail": f"EOB {eob.date_from} to {eob.date_to}; bill {bill.date_from} to {bill.date_to}."})
    if eob.ms_drg and bill.ms_drg and eob.ms_drg != bill.ms_drg:
        flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": f"EOB paid MS-DRG {eob.ms_drg}, the bill shows {bill.ms_drg}",
                      "detail": "The insurer grouped the stay differently. Check which DRG the report should use."})
    if not drg_level:
        missing = [b_.line_no for b_ in bill.lines if b_.line_no not in m]
        extra = [e.line_no for e in eob.lines if e not in m.values() and not e.ms_drg]
        if missing:
            flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": f"{len(missing)} bill line(s) not found on the EOB",
                          "detail": f"Bill lines {', '.join(map(str, missing[:20]))}. The EOB may group them, or they were not sent to the insurer."})
        if extra:
            flags.append({"kind": "eob", "severity": "check", "line_no": None, "title": f"{len(extra)} EOB line(s) not found on the bill",
                          "detail": f"EOB lines {', '.join(map(str, extra[:20]))}."})
        denied = [no for no, e in m.items() if (e.get("allowed") == 0 and (e.get("billed") or 0) > 0)]
        if denied:
            flags.append({"kind": "eob", "severity": "info", "line_no": None, "title": f"Insurer allowed $0 on {len(denied)} line(s)",
                          "detail": f"Bill lines {', '.join(map(str, denied))}: not covered, or included in another service (see the EOB remark codes)."})
    # The insurer's allowed amount against the hospital's posted rate with that insurer, on the SAME lines.
    same = None
    if group and group == payer_group_of_bill:
        if drg_level and a is not None and payer_rate_total:
            same = (a, float(payer_rate_total), "the stay")
        elif payer_rate_by_line:
            pairs = [(float(e.get("allowed")), float(payer_rate_by_line[no])) for no, e in m.items()
                     if e.get("allowed") is not None and payer_rate_by_line.get(no) is not None]
            if pairs:
                same = (sum(x for x, _ in pairs), sum(y for _, y in pairs), f"the {len(pairs)} line(s) with a posted rate")
    if same and same[1]:
        diff = (same[0] - same[1]) / same[1]
        summary["vs_price_file"] = {"allowed": round(same[0], 2), "posted": round(same[1], 2), "pct": round(100 * diff)}
        if abs(diff) >= 0.10:
            flags.append({"kind": "eob", "severity": "info", "line_no": None,
                          "title": f"EOB allowed is {abs(round(100 * diff))} % {'above' if diff > 0 else 'below'} the hospital's posted rate",
                          "detail": f"On {same[2]}: EOB allowed {_m(same[0])}; posted rate with {payer_group_of_bill} {_m(same[1])}. "
                                    "The EOB may apply other contract terms (bundling, a different plan, a newer contract)."})
    return summary, per_line, flags


def _m(v) -> str:
    return "—" if v is None else f"${float(v):,.2f}"
