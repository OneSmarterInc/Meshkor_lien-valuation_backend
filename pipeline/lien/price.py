"""Price a read bill against the reference data in meshkor.duckdb.

For each bill line (outpatient) or for the whole stay (inpatient, one MS-DRG):
  payer_rate  the hospital's own posted rate with the patient's insurer (price file)
  median, p10, p90  of every payer's posted dollar rate for the same code
  cash        the hospital's posted discounted cash price, if it posts one
  medicare    what Medicare pays this hospital (OPPS wage-adjusted, CLFS, MPFS, ASP; IPPS for a DRG)
  cost        charge x the hospital's cost-to-charge ratio (Medicare cost report)

Pure Python + DuckDB: no Django here. intake.py writes the result to the case.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from ..ref.hospital_mrf import payer_group
from .db import objects, rows
from .reader import Bill, BillLine

SELF_PAY = "Self-pay"
# Payer groups left out of the median, 10th and 90th percentile (decision of Oct 26, 2026): the median
# is the typical COMMERCIAL insurer's rate. Government plans have their own benchmark (the Medicare line).
NOT_COMMERCIAL = {"Medicare", "Medicare Advantage", "Medicaid", "Government other", "Workers Comp", SELF_PAY}
OUTPATIENT_SETTINGS = ("outpatient", "both")
INPATIENT_SETTINGS = ("inpatient", "both")


def money(x) -> Decimal | None:
    return None if x is None else Decimal(str(x)).quantize(Decimal("0.01"), ROUND_HALF_UP)


def _median(v: list[float]) -> float | None:
    return statistics.median(v) if v else None


def _quantile(v: list[float], q: float) -> float | None:
    if not v:
        return None
    s = sorted(v)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


@dataclass
class PriceFile:
    period: str
    file_name: str
    sha256: str
    last_updated_on: str | None
    effective_start: date | None
    effective_end: date | None
    covers_service_date: bool

    def as_json(self) -> dict:
        return {"file_name": self.file_name, "period": self.period, "last_updated_on": self.last_updated_on,
                "covers_service_date": self.covers_service_date, "sha256": self.sha256}

    def source(self) -> dict:
        return {"label": "Hospital price file", "file_name": self.file_name, "sha256": self.sha256,
                "dated": self.last_updated_on}


@dataclass
class Priced:
    payer_group: str
    price_file: PriceFile | None
    ccr: float | None
    ccr_source: dict | None
    lines: dict[str, list[dict]] = field(default_factory=dict)      # basis -> lines
    totals: dict = field(default_factory=dict)
    stay: dict | None = None
    flags: list[dict] = field(default_factory=list)


# ----------------------------------------------------------------------------- reference lookups

class Ref:
    def __init__(self, con, ccn: str):
        self.con, self.ccn = con, ccn
        self.have = objects(con)
        self.mrf_cols = ({r[0] for r in con.execute("DESCRIBE ref_hospital_mrf").fetchall()}
                         if "ref_hospital_mrf" in self.have else set())

    def _grp(self) -> str:
        # Files loaded with the first load_mrf.py have no payer_group column: work it out here.
        return "payer_group" if "payer_group" in self.mrf_cols else "NULL AS payer_group"

    def _terms(self) -> str:
        """One text column with the contract terms (algorithm, notes, methodology): used to find "% of Medicare"."""
        cols = [c for c in ("negotiated_algorithm", "payer_notes", "notes", "methodology") if c in self.mrf_cols]
        return f"concat_ws(' | ', {', '.join(cols)}) AS terms" if cols else "NULL AS terms"

    def _fill_groups(self, out: list[dict]) -> list[dict]:
        # Always from config/payer_groups.yaml, so a rule change applies at once (no reload of the price files).
        for r in out:
            r["payer_group"] = payer_group(r["payer_name"], r["plan_name"])
        return out

    def q(self, sql, params=()):
        return rows(self.con, sql, params)

    # -- price file
    def price_files(self) -> list[dict]:
        if "ref_hospital_mrf" not in self.have:
            return []
        return self.q("""SELECT period, any_value(source_file) AS source_file, any_value(source_sha256) AS sha,
                                CAST(any_value(last_updated_on) AS VARCHAR) AS last_updated_on,
                                min(effective_start) AS es, max(effective_end) AS ee
                         FROM ref_hospital_mrf WHERE ccn = ? GROUP BY period ORDER BY es""", [self.ccn])

    def mrf_code_rows(self, period: str, code: str, settings: tuple) -> list[dict]:
        return self._fill_groups(self.q(f"""SELECT {self._grp()}, payer_name, plan_name, modifiers, negotiated_dollar, negotiated_percentage,
                                 estimated_amount, discounted_cash, gross_charge, {self._terms()}
                          FROM ref_hospital_mrf
                          WHERE ccn = ? AND period = ? AND hcpcs = ?
                            AND lower(coalesce(setting, 'both')) IN ({",".join("?" * len(settings))})""",
                      [self.ccn, period, code, *settings]))

    def mrf_drg_rows(self, period: str, drg: str) -> list[dict]:
        return self._fill_groups(self.q(f"""SELECT {self._grp()}, payer_name, plan_name, NULL AS modifiers, negotiated_dollar, negotiated_percentage,
                                estimated_amount, discounted_cash, gross_charge, {self._terms()}
                         FROM ref_hospital_mrf
                         WHERE ccn = ? AND period = ? AND ms_drg = ?
                           AND lower(coalesce(setting, 'inpatient')) IN ('inpatient', 'both')""",
                      [self.ccn, period, drg.zfill(3)]))

    # -- cost
    def ccr(self) -> tuple[float | None, dict | None]:
        if "v_hcris_latest" in self.have:
            r = self.q("SELECT cost_to_charge_ratio AS ccr, fy_end, source_file, source_sha256 FROM v_hcris_latest WHERE ccn = ?", [self.ccn])
            if r and r[0]["ccr"]:
                return float(r[0]["ccr"]), {"label": f"Medicare cost report, year ending {r[0]['fy_end']}",
                                             "file_name": r[0]["source_file"], "sha256": r[0]["source_sha256"]}
        if "ref_ipps_hospital" in self.have:
            r = self.q("""SELECT operating_ccr + coalesce(capital_ccr, 0) AS ccr, fiscal_year, source_file, source_sha256
                          FROM ref_ipps_hospital WHERE ccn = ? ORDER BY effective_start DESC LIMIT 1""", [self.ccn])
            if r and r[0]["ccr"]:
                return float(r[0]["ccr"]), {"label": f"IPPS impact file {r[0]['fiscal_year']} (cost-to-charge ratio)",
                                             "file_name": r[0]["source_file"], "sha256": r[0]["source_sha256"]}
        return None, None

    # -- Medicare, outpatient
    def opps(self, code: str, dos: date) -> dict | None:
        if "ref_opps" not in self.have:
            return None
        r = self.q("""SELECT status_indicator AS si, apc, payment_rate_national AS national, period, source_file, source_sha256
                      FROM ref_opps WHERE hcpcs = ? AND ? BETWEEN effective_start AND effective_end""", [code, dos])
        if not r:
            return None
        out = r[0]
        out["adjusted"] = None
        if out["national"] is not None and "opps_wage_adjusted" in self.have:
            w = self.q("SELECT payment_rate_adjusted AS a, wage_index FROM opps_wage_adjusted(?, ?, ?)", [code, dos, self.ccn])
            if w:
                out["adjusted"], out["wage_index"] = w[0]["a"], w[0]["wage_index"]
        return out

    def clfs(self, code: str, dos: date) -> dict | None:
        if "ref_clfs" not in self.have:
            return None
        r = self.q("""SELECT rate, period, source_file FROM ref_clfs
                      WHERE hcpcs = ? AND modifier = '' AND ? BETWEEN effective_start AND effective_end""", [code, dos])
        return r[0] if r and r[0]["rate"] is not None else None

    def mpfs(self, code: str, dos: date) -> dict | None:
        if "mpfs_rate" not in self.have:
            return None
        r = self.q("SELECT rate_nonfacility AS rate, period, source_file, source_sha256 FROM mpfs_rate(?, ?)", [code, dos])
        return r[0] if r and r[0]["rate"] is not None else None

    def asp(self, code: str, dos: date) -> dict | None:
        if "asp_price" not in self.have:
            return None
        r = self.q("SELECT payment_limit AS rate, period, source_file, source_sha256 FROM asp_price(?, ?)", [code, dos])
        return r[0] if r and r[0]["rate"] is not None else None

    # -- Medicare, inpatient
    def drg_title(self, drg: str, dos: date) -> str:
        if "msdrg_title" in self.have:
            r = self.q("SELECT title FROM msdrg_title(?, ?)", [drg.zfill(3), dos])
            if r:
                return r[0]["title"]
        if "ref_ipps_drg" in self.have:
            r = self.q("SELECT ms_drg_title AS t FROM ref_ipps_drg WHERE ms_drg = ? AND ? BETWEEN effective_start AND effective_end",
                       [drg.zfill(3), dos])
            if r:
                return r[0]["t"]
        return ""

    def diagnoses(self, codes: list[str], dos: date | None) -> list[dict]:
        """Name and level of each diagnosis on the date of service, from the CMS MS-DRG definitions:
        the first is the principal; a secondary one is an MCC or CC (appendix C) or "other"."""
        out = []
        for i, code in enumerate(codes):
            name, level = "", "principal" if i == 0 else "other"
            if dos and "ref_msdrg_dx" in self.have:
                r = self.q("""SELECT any_value(description) AS d FROM ref_msdrg_dx
                              WHERE icd10 = ? AND ? BETWEEN effective_start AND effective_end""", [code, dos])
                name = (r[0]["d"] if r else "") or ""
            if dos and "ref_msdrg_cc" in self.have:
                r = self.q("""SELECT cc_level, description FROM ref_msdrg_cc
                              WHERE icd10 = ? AND ? BETWEEN effective_start AND effective_end LIMIT 1""", [code, dos])
                if r:
                    name = name or (r[0]["description"] or "")
                    if i > 0 and r[0]["cc_level"] in ("CC", "MCC"):
                        level = r[0]["cc_level"].lower()
            out.append({"code": code, "description": name or "Not found in the MS-DRG code list for this date", "level": level})
        return out

    def ipps(self, drg: str, dos: date) -> dict | None:
        if "ipps_payment" not in self.have:
            return None
        r = self.q("SELECT estimated_total_payment AS total, fiscal_year FROM ipps_payment(?, ?, ?)", [drg, dos, self.ccn])
        if not (r and r[0]["total"] is not None):
            return None
        out = r[0]
        src = self.q("""SELECT source_file, source_sha256 FROM ref_ipps_hospital
                        WHERE ccn = ? AND ? BETWEEN effective_start AND effective_end LIMIT 1""", [self.ccn, dos])
        out["src"] = ({"label": f"Medicare IPPS impact file and Table 5, {out['fiscal_year']}", "file_name": src[0]["source_file"],
                       "sha256": src[0]["source_sha256"]} if src else None)
        return out


# ----------------------------------------------------------------------------- price file rows -> values

def _pick_modifier_rows(mrf: list[dict], modifiers: str) -> list[dict]:
    mods = set(modifiers.split())
    if mods:
        same = [r for r in mrf if r["modifiers"] and mods & set(str(r["modifiers"]).replace("|", " ").split())]
        if same:
            return same
    plain = [r for r in mrf if not r["modifiers"]]
    return plain or mrf


PCT_OF_MEDICARE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*of\s+(?:the\s+)?medicare", re.I)


def pct_of_medicare(r: dict) -> float | None:
    m = PCT_OF_MEDICARE.search(r.get("terms") or "")
    return float(m.group(1)) if m else None


def is_multiplier(r: dict, medicare_per_unit: float | None = None) -> bool:
    """A "dollar" rate under $5 on a charge of $50 or more is a factor the hospital put in the dollar
    column (OSU: Cigna 0.62, Medicaid 1.07 on a $238 visit), not a payment. Never use it as dollars.
    When Medicare's rate for the line is known and the posted dollars are at least half of it, the row is
    a real (cheap) price, e.g. venipuncture at $3."""
    d, g = r.get("negotiated_dollar"), r.get("gross_charge")
    if d is None or g is None or float(d) >= 5 or float(g) < 50:
        return False
    if medicare_per_unit and float(d) >= 0.5 * medicare_per_unit:
        return False
    return True


def mrf_values(mrf: list[dict], group: str, charge_per_unit: float | None, medicare_per_unit: float | None = None) -> dict:
    """Per-unit values from the price-file rows of one code (or DRG).

    A row whose terms say "N % of Medicare" is valued as N % x the Medicare rate of this line; its
    negotiated_dollar is ignored (OSU, for example, puts a fee-schedule factor there, not a price).
    A multiplier posted as dollars (is_multiplier) with no such term is left out and counted.
    """
    def value(r):
        pm = pct_of_medicare(r)
        if pm is not None:
            if medicare_per_unit:
                return pm / 100 * medicare_per_unit, True
            return None, False
        if is_multiplier(r, medicare_per_unit):
            return None, False
        if r["negotiated_dollar"] is not None:
            return float(r["negotiated_dollar"]), False
        if r["negotiated_percentage"] is not None and charge_per_unit is not None:
            return float(r["negotiated_percentage"]) / 100 * charge_per_unit, True
        if r["estimated_amount"] is not None:
            return float(r["estimated_amount"]), True
        return None, False

    every = []
    for r in mrf:
        if r["payer_group"] in NOT_COMMERCIAL:
            continue
        v, est = value(r)
        if v is not None and (not est or pct_of_medicare(r) is not None):
            every.append(v)          # dollar rates and %-of-Medicare rates; %-of-charges estimates left out
    mine_rows = [r for r in mrf if r["payer_group"] == group] if group not in (SELF_PAY, "Other") else []
    mine = [(value(r), pct_of_medicare(r) is not None) for r in mine_rows]
    # Contract rates: posted dollars and "% of Medicare" terms. Fallback: % of charges, estimated amounts.
    exact = [v for (v, est), pm in mine if v is not None and (not est or pm)]
    derived = any(v is not None and pm for (v, _), pm in mine)
    rough = [v for (v, est), pm in mine if v is not None and est and not pm]
    cash = [float(r["discounted_cash"]) for r in mrf if r["discounted_cash"] is not None]
    return {
        "payer_rate": _median(exact) if exact else _median(rough),
        "payer_rate_is_estimate": derived if exact else bool(rough),
        "payer_plans": len(mine),
        "payer_range": (min(exact or rough), max(exact or rough)) if (exact or rough) else None,
        "median": _median(every), "p10": _quantile(every, 0.10), "p90": _quantile(every, 0.90),
        "cash": max(cash) if cash else None,
        "found": bool(mrf),
        "pct_of_medicare": sorted({p for r in mrf if r["payer_group"] == group and (p := pct_of_medicare(r)) is not None}),
        "multipliers_skipped": sum(1 for r in mrf if is_multiplier(r, medicare_per_unit) and pct_of_medicare(r) is None),
        "payer_multipliers_skipped": sum(1 for r in mine_rows if is_multiplier(r, medicare_per_unit) and pct_of_medicare(r) is None),
    }


# ----------------------------------------------------------------------------- Medicare per line

PACKAGED_SI = {"N"}
COMPREHENSIVE_SI = {"J1"}
# Lines CMS never packages into a comprehensive APC (C-APC): pass-through drugs and devices (G, H),
# brachytherapy sources (U), vaccines (L, F). Lines Medicare pays under another fee schedule (labs with
# status A on the lab fee schedule, therapy on the physician fee schedule, drugs on ASP) are also paid
# outside the C-APC. Everything else on the visit's claim is packaged into the primary J1 line.
CAPC_EXCLUDED_SI = {"G", "H", "U", "L", "F"}
MULTI_PROC_SI = {"T"}           # second and later "T" procedures on a claim are paid at 50 %
VISIT_GAP_DAYS = 1              # dates further apart than this are separate visits (separate claims)


def medicare_line(ref: Ref, ln: BillLine, dos: date) -> dict:
    """amount per unit, status (priced | packaged | none), source label, si."""
    if not ln.hcpcs:
        # No code: Medicare pays this (room, supplies, anesthesia time ...) inside the coded lines of the visit.
        # The amount becomes $0 "packaged" below, once the visit is known to have a priced line.
        return {"rate": None, "status": "packaged", "label": "Revenue code only: packaged into the visit (OPPS)", "si": None, "src": None}
    o = ref.opps(ln.hcpcs, dos)
    if o and o["si"] in PACKAGED_SI:
        return {"rate": 0.0, "status": "packaged", "label": f"OPPS {o['period']}: status N, packaged", "si": o["si"],
                "src": {"label": f"Medicare OPPS Addendum B {o['period']}", "file_name": o["source_file"], "sha256": o["source_sha256"]}}
    if o and o["national"] is not None and o["si"] not in ("A", "Q4"):
        adj = o.get("adjusted")
        label = (f"OPPS {o['period']} APC {o['apc']}, wage-adjusted" if adj is not None
                 else f"OPPS {o['period']} APC {o['apc']}, national (no wage index for this hospital)")
        return {"rate": adj if adj is not None else o["national"], "status": "priced", "label": label, "si": o["si"],
                "src": {"label": f"Medicare OPPS Addendum B {o['period']}", "file_name": o["source_file"], "sha256": o["source_sha256"]}}
    for kind, hit in (("CLFS", ref.clfs), ("MPFS", ref.mpfs), ("ASP", ref.asp)):
        h = hit(ln.hcpcs, dos)
        if h:
            names = {"CLFS": "Clinical lab fee schedule", "MPFS": "Physician fee schedule, non-facility (Ohio)",
                     "ASP": "Part B drug payment limit (ASP + 6 %)"}
            return {"rate": float(h["rate"]), "status": "priced", "label": f"{kind} {h['period']}", "si": o["si"] if o else None,
                    "src": {"label": f"Medicare {names[kind]} {h['period']}", "file_name": h["source_file"], "sha256": h.get("source_sha256")}}
    return {"rate": None, "status": "none", "label": "", "si": o["si"] if o else None, "src": None}


# ----------------------------------------------------------------------------- main

def choose_price_file(ref: Ref, dos: date | None) -> tuple[PriceFile | None, PriceFile | None]:
    """(file in force on the date of service, nearest file for an estimate)."""
    files = ref.price_files()
    if not files:
        return None, None
    def pf(r, covers):
        return PriceFile(r["period"], (r["source_file"] or "").replace("\\", "/").rsplit("/", 1)[-1], r["sha"],
                         r["last_updated_on"], r["es"], r["ee"], covers)
    if dos:
        for r in reversed(files):
            if r["es"] and r["ee"] and r["es"] <= dos <= r["ee"]:
                return pf(r, True), None
        near = min(files, key=lambda r: abs((r["es"] - dos).days) if r["es"] else 10 ** 6)
        return None, pf(near, False)
    return pf(files[-1], True), None


def _line_dict(ln: BillLine) -> dict:
    return {"line_no": ln.line_no, "service_date": ln.service_date, "revenue_code": ln.revenue_code, "hcpcs": ln.hcpcs,
            "modifiers": ln.modifiers, "units": ln.units, "description": ln.description, "charge": ln.charge,
            "confidence": ln.confidence, "payer_rate": None, "payer_rate_is_estimate": False, "median": None,
            "p10": None, "p90": None, "cash": None, "medicare": None, "medicare_status": "none", "medicare_source": "",
            "cost": None, "status": "unpriced_no_code", "sources": []}


def _sum(lines: list[dict], key: str) -> float | None:
    v = [float(x[key]) for x in lines if x[key] is not None]
    return round(sum(v), 2) if v else None


def _coverage(lines: list[dict], billed: float) -> dict:
    """Billed dollars on the lines that have each value (a packaged Medicare line counts as covered),
    plus the share of the bill as a percent. The report compares each total with these dollars."""
    if not billed:
        return {}
    out = {}
    for k in ("payer_rate", "median", "cash", "medicare", "cost"):
        covered = round(sum(float(x["charge"]) for x in lines if x[k] is not None), 2)
        out[k] = round(100 * covered / billed)
        out[k + "_billed"] = covered
    out["lines"] = len(lines)
    out["lines_with"] = {k: sum(1 for x in lines if x[k] is not None) for k in ("payer_rate", "median", "cash", "medicare", "cost")}
    return out


def price_outpatient(ref: Ref, bill: Bill, group: str, pf: PriceFile | None, ccr, ccr_src, estimate: bool) -> list[dict]:
    out = []
    for ln in bill.lines:
        d = _line_dict(ln)
        dos = ln.service_date or bill.date_from
        units = float(ln.units or 1)
        sign = -1 if ln.charge < 0 else 1      # a reversal / credit line takes its rates away again
        if ccr is not None:
            d["cost"] = money(float(ln.charge) * ccr)
            d["sources"].append(ccr_src)
        m = medicare_line(ref, ln, dos) if dos else None
        d["_dos"], d["_units"], d["_sign"] = dos, units, sign
        if m:
            d["medicare_status"], d["medicare_source"] = m["status"], m["label"]
            d["medicare"] = money(m["rate"] * units * sign) if m["rate"] is not None else None
            if m["src"]:
                d["sources"].append(m["src"])
            d["_si"], d["_mrate"] = m["si"], m["rate"]
            d["_mkind"] = (m["label"] or "").split(" ", 1)[0]       # OPPS | CLFS | MPFS | ASP
        if ln.hcpcs and pf:
            base = m["rate"] if (m and m["status"] == "priced" and m["rate"]) else None
            v = mrf_values(_pick_modifier_rows(ref.mrf_code_rows(pf.period, ln.hcpcs, OUTPATIENT_SETTINGS), ln.modifiers),
                           group, float(ln.charge) / units if units else None, base)
            if v["found"]:
                for k in ("payer_rate", "median", "p10", "p90", "cash"):
                    d[k] = money(v[k] * units * sign) if v[k] is not None else None
                d["payer_rate_is_estimate"] = v["payer_rate_is_estimate"] or estimate
                d["status"] = "priced"
                d["sources"].append(pf.source())
                d["_payer_plans"] = v["payer_plans"]
                d["_pct_of_medicare"] = v["pct_of_medicare"]
                d["_multipliers"] = (v["multipliers_skipped"], v["payer_multipliers_skipped"])
            else:
                d["status"] = "unpriced_no_hospital_row"
        elif ln.hcpcs:
            d["status"] = "unpriced_no_hospital_row"
        if not ln.hcpcs:
            d["status"] = "packaged" if d["medicare_status"] == "packaged" else "unpriced_no_code"
        out.append(d)
    apply_claim_rules(out)
    return out


def visits(lines: list[dict]) -> list[list[dict]]:
    """Group bill lines into visits: one date, or dates at most VISIT_GAP_DAYS apart.
    Medicare bundles and discounts per claim, and one outpatient visit is one claim."""
    dated = sorted((d for d in lines if d.get("_dos")), key=lambda d: d["_dos"])
    groups: list[list[dict]] = []
    for d in dated:
        if groups and (d["_dos"] - groups[-1][-1]["_dos"]).days <= VISIT_GAP_DAYS:
            groups[-1].append(d)
        else:
            groups.append([d])
    undated = [d for d in lines if not d.get("_dos")]
    if undated:
        if not groups:
            groups.append([])
        groups[0].extend(undated)
    return groups


def apply_claim_rules(lines: list[dict]) -> None:
    """Medicare's outpatient claim rules, per visit (CMS OPPS):
    1. Comprehensive APC: the visit's highest-paid J1 line is the primary; the other J1 lines and every
       other OPPS line are packaged into it ($0), except the C-APC exclusions (CAPC_EXCLUDED_SI) and the
       lines paid under another fee schedule (lab status A, physician fee schedule, ASP).
    2. Multiple procedure discount: on a visit without a J1, the highest-paid "T" procedure is paid in full
       and every other T unit at 50 %.
    3. A line with only a revenue code is paid inside the coded lines of its visit ($0); with no coded
       Medicare line in the visit, it has no Medicare value.
    Lines keep their own rate otherwise. Each change is written into medicare_source."""
    groups = visits(lines)
    for vi, visit in enumerate(groups, start=1):
        tag = f" (visit {vi})" if len(groups) > 1 else ""
        j1 = [d for d in visit if d.get("_si") in COMPREHENSIVE_SI and d["medicare_status"] == "priced" and d.get("_mrate")]
        if j1:
            primary = max(j1, key=lambda d: d["_mrate"])
            primary["medicare_source"] += f"; primary comprehensive APC (J1) of this visit{tag}"
            for d in visit:
                if d is primary or d["medicare_status"] != "priced":
                    continue
                si, kind = d.get("_si"), d.get("_mkind")
                if d.get("_si") in COMPREHENSIVE_SI:
                    why = "Packaged: a second comprehensive procedure, paid inside the primary J1"
                elif si in CAPC_EXCLUDED_SI:
                    d["medicare_source"] += f"; paid separately (status {si} is never packaged into a C-APC)"
                    continue
                elif kind in ("CLFS", "MPFS", "ASP"):
                    d["medicare_source"] += "; paid separately (outside the OPPS bundle, on its own fee schedule)"
                    continue
                else:
                    why = f"Packaged into the comprehensive APC (J1, {primary['hcpcs']}) of this visit"
                d["medicare"], d["medicare_status"], d["medicare_source"] = money(0), "packaged", why
        else:
            t = [d for d in visit if d.get("_si") in MULTI_PROC_SI and d["medicare_status"] == "priced" and d.get("_mrate")]
            if len(t) > 1 or (t and t[0]["_units"] > 1):
                t.sort(key=lambda d: d["_mrate"], reverse=True)
                for i, d in enumerate(t):
                    full_units = 1 if i == 0 else 0
                    rest = max(d["_units"] - full_units, 0)
                    if rest <= 0:
                        d["medicare_source"] += "; highest procedure of the visit: paid in full"
                        continue
                    amount = d["_mrate"] * (full_units + 0.5 * rest) * d["_sign"]
                    d["medicare"] = money(amount)
                    d["medicare_source"] += ("; multiple procedure discount: " +
                                             ("first unit in full, other units at 50 %" if full_units else "paid at 50 % (not the highest procedure of the visit)"))
        priced = any(d["medicare_status"] == "priced" for d in visit)
        for d in visit:
            if d["hcpcs"] or d["medicare_status"] != "packaged":
                continue
            if priced:
                if d["medicare"] is None:
                    d["medicare"] = money(0)          # paid inside the coded lines of the visit
            else:
                d["medicare_status"], d["medicare_source"] = "none", "No coded line in this visit carries a Medicare payment"
                d["status"] = "unpriced_no_code"


def price_inpatient(ref: Ref, bill: Bill, group: str, pf: PriceFile | None, ccr, ccr_src, estimate: bool) -> tuple[list[dict], dict]:
    lines = []
    for ln in bill.lines:
        d = _line_dict(ln)
        if ccr is not None:
            d["cost"] = money(float(ln.charge) * ccr)
            d["sources"].append(ccr_src)
        d["medicare_status"], d["status"] = "packaged", "packaged"
        d["medicare_source"] = "Inpatient: paid as one MS-DRG for the stay"
        lines.append(d)
    billed = float(bill.lines_total)
    dos = bill.date_to or bill.date_from
    drg = bill.ms_drg
    values = {"billed": round(billed, 2), "payer_rate": None, "median": None, "p10": None, "p90": None, "cash": None,
              "medicare": None, "cost": round(billed * ccr, 2) if ccr is not None else None, "payer_rate_is_estimate": False}
    stay = {"ms_drg": drg, "drg_title": ref.drg_title(drg, dos) if (drg and dos) else "", "drg_source": "bill",
            "los_days": (bill.date_to - bill.date_from).days if (bill.date_from and bill.date_to) else None,
            "diagnoses": ref.diagnoses(bill.diagnoses, dos), "sources": []}
    if drg and dos:
        m = ref.ipps(drg, dos)
        if m:
            values["medicare"] = round(float(m["total"]), 2)
            stay["medicare_source"] = f"IPPS {m['fiscal_year']} for this hospital (estimate, no outlier)"
            if m.get("src"):
                stay["sources"].append(m["src"])
    if drg and pf:
        v = mrf_values(ref.mrf_drg_rows(pf.period, drg), group, billed, values["medicare"])
        for k in ("payer_rate", "median", "p10", "p90", "cash"):
            values[k] = round(v[k], 2) if v[k] is not None else None
        values["payer_rate_is_estimate"] = v["payer_rate_is_estimate"] or estimate
        stay["pct_of_medicare"] = v["pct_of_medicare"]
        if v["found"]:
            stay["sources"].append(pf.source())
    if ccr_src:
        stay["sources"].append(ccr_src)
    stay["values"] = values
    return lines, stay


def price(con, bill: Bill, ccn: str, payer: str) -> Priced:
    ref = Ref(con, ccn)
    group = SELF_PAY if not payer.strip() else payer_group(payer, None)
    in_force, nearest = choose_price_file(ref, bill.date_from)
    ccr, ccr_src = ref.ccr()
    res = Priced(payer_group=group, price_file=in_force or nearest, ccr=ccr, ccr_source=ccr_src)

    bases = [("service_date", in_force, False)]
    if in_force is None and nearest is not None:
        bases.append(("estimate", nearest, True))
    main = "estimate" if in_force is None and nearest is not None else "service_date"
    totals = {}
    for basis, pf, est in bases:
        if bill.inpatient:
            lines, stay = price_inpatient(ref, bill, group, pf, ccr, ccr_src, est)
            if basis == main:
                res.stay = stay
            t = {k: stay["values"][k] for k in ("billed", "payer_rate", "median", "cash", "medicare", "cost")}
            t["payer_rate_is_estimate"] = bool(stay["values"].get("payer_rate_is_estimate"))
        else:
            lines = price_outpatient(ref, bill, group, pf, ccr, ccr_src, est)
            t = {"billed": round(float(bill.lines_total), 2), **{k: _sum(lines, k) for k in ("payer_rate", "median", "cash", "medicare", "cost")}}
            t["coverage"] = _coverage(lines, float(bill.lines_total))
            t["payer_rate_is_estimate"] = any(d["payer_rate_is_estimate"] for d in lines if d["payer_rate"] is not None)
        res.lines[basis] = lines
        totals[basis] = t
    # The report and the totals use the basis that has the hospital's rates: the file in force on the
    # service date, or else the nearest file (every value from it is marked as an estimate).
    res.totals = dict(totals[main])
    res.totals["basis"] = main
    for other in totals:
        if other != main:
            res.totals[other] = totals[other]
    res.flags = flags(bill, res, group, in_force, nearest, ccr, main)
    return res


# ----------------------------------------------------------------------------- flags

def flags(bill: Bill, res: Priced, group: str, in_force, nearest, ccr, main: str = "service_date") -> list[dict]:
    f = []
    def add(kind, severity, title, detail="", line_no=None):
        f.append({"kind": kind, "severity": severity, "title": title, "detail": detail, "line_no": line_no})

    lines = res.lines[main]
    for d in lines:
        if d["confidence"] is not None and d["confidence"] < 0.9:
            add("low_confidence", "check", f"Line {d['line_no']} read with {round(d['confidence'] * 100)} % certainty",
                "Compare this line with the bill.", d["line_no"])
    if bill.stated_total is not None and abs(bill.stated_total - bill.lines_total) > Decimal("1.00"):
        add("other", "check", "Line charges do not add up to the bill total",
            f"Lines add up to ${bill.lines_total:,.2f}; the bill says ${bill.stated_total:,.2f}. A line may be missing.")
    if in_force is None and nearest is None:
        add("no_price_file", "check", "No price file loaded for this hospital",
            "Payer, median and cash values are empty. Load the hospital's price file, then reprocess.")
    elif in_force is None:
        add("estimate", "check", "The price file does not cover the date of service",
            f"The insurer rate, median and cash come from the hospital's file dated {nearest.last_updated_on} and are marked "
            "as estimates in the report. Medicare and cost are for the date of service.")
    if group == SELF_PAY:
        add("other", "info", "Self-pay: no insurer rate", "The bill shows no insurer. The report uses the median, cash price, Medicare and cost.")
    elif group == "Other":
        add("other", "check", f"Insurer “{bill.payer}” is not in the payer list: no insurer rate",
            "The insurer rate is left empty rather than taken from an unrelated plan. Add the name to config/payer_groups.yaml "
            "(MeshKor staff), then reprocess the case.")
    if ccr is None:
        add("other", "info", "No cost-to-charge ratio for this hospital", "The cost column is empty.")
    if bill.inpatient:
        st = res.stay or {}
        if not st.get("ms_drg"):
            add("drg_check", "check", "Inpatient bill without an MS-DRG", "Enter the MS-DRG from the UB-04 (box 71) or the grouper.")
        else:
            dx = st.get("diagnoses") or []
            mcc = [d["code"] for d in dx if d["level"] == "mcc"]
            cc = [d["code"] for d in dx if d["level"] == "cc"]
            dx_note = (f" The bill lists {len(dx)} diagnosis code(s)"
                       + (f"; MCC: {', '.join(mcc)}" if mcc else "") + (f"; CC: {', '.join(cc)}" if cc else "")
                       + ". A \"with MCC\" or \"with CC\" DRG needs such a secondary diagnosis (CMS's exclusions for the principal"
                       " diagnosis are not checked here)." if dx else " The bill lists no diagnosis codes.")
            add("drg_check", "check", f"Confirm MS-DRG {st['ms_drg']} {st.get('drg_title') or ''}".strip(),
                "The whole stay is valued as this DRG. Check it against the diagnoses and procedures." + dx_note)
        if st.get("values", {}).get("payer_rate") is None and group not in (SELF_PAY, "Other") and (in_force or nearest):
            add("no_rate", "check", f"No {group} rate posted for this DRG", "The hospital's file has no rate for this payer and DRG.")
        return f
    no_rate = [d["line_no"] for d in lines if d["hcpcs"] and d["payer_rate"] is None and group not in (SELF_PAY, "Other") and (in_force or nearest)]
    if no_rate:
        add("no_rate", "check" if len(no_rate) > len(lines) / 2 else "info",
            f"No {group} rate on {len(no_rate)} line(s)", "Lines " + ", ".join(map(str, no_rate)) + ": the price file has no rate for this payer and code.",
            no_rate[0])
    low = [d["line_no"] for d in lines if d["payer_rate"] is not None and d["medicare"] and d["payer_rate"] < d["medicare"]]
    if low:
        add("other", "check", f"Payer rate below Medicare on {len(low)} line(s)",
            "Lines " + ", ".join(map(str, low)) + ": a commercial rate under Medicare is unusual. Check the price-file rows "
            "(a factor or a percentage may be posted as dollars).", low[0])
    mult = [d for d in lines if (d.get("_multipliers") or (0, 0))[0]]
    if mult:
        mine = sum((d.get("_multipliers") or (0, 0))[1] for d in lines)
        add("other", "check" if mine else "info", f"Factors posted as dollars on {len(mult)} line(s): left out",
            "The price file shows rates under $5 on charges over $50 (a multiplier, not a payment). Those plans are left out of the "
            "median" + (f"; {mine} of them are {group} plans, so the {group} rate on those lines rests on the other plans or is empty." if mine else "."))
    pm = sorted({p for d in lines for p in d.get("_pct_of_medicare") or []})
    if pm:
        add("estimate", "info", f"Some {group} plans pay a % of Medicare ({', '.join(f'{p:g} %' for p in pm)})",
            "Those plans are valued as that % x the Medicare rate of the line (marked *).")
    vs = visits(lines)
    if len(vs) > 1:
        spans = ", ".join(f"{v[0]['_dos']}" + (f" to {v[-1]['_dos']}" if v[-1]["_dos"] != v[0]["_dos"] else "") for v in vs if v and v[0].get("_dos"))
        add("other", "info", f"Bill holds {len(vs)} visits: Medicare bundling applied per visit",
            f"Visits: {spans}. Medicare packages and discounts each visit as its own claim. If two of them were one claim "
            "(for example a stay that crossed midnight twice), tell MeshKor support.")
    packaged = [d["line_no"] for d in lines if d["medicare_status"] == "packaged"]
    if packaged:
        add("packaged", "info", f"{len(packaged)} line(s) packaged by Medicare",
            "Lines " + ", ".join(map(str, packaged)) + ": Medicare pays these inside another line, so their Medicare value is $0.")
    billed = float(bill.lines_total)
    covered = sum(float(d["charge"]) for d in lines if d["payer_rate"] is not None)
    if billed and group not in (SELF_PAY, "Other") and 0 < covered < 0.9 * billed:
        add("other", "check", f"Payer rate covers {round(100 * covered / billed)} % of billed charges",
            "The payer total leaves out lines with no posted rate. Say so in the report or add the missing values.")
    return f
