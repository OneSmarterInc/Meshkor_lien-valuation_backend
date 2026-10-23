"""Step 1 verification (Spec §8). Reads only the DuckDB file and the load
manifests, and writes a short Markdown report you can paste back for review.
It contains counts, hashes and test results — no provider-level rows.

    python -m pipeline.verify            # or: manage.py verify_step1
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from .common import config
from .common.lineage import LINEAGE_COLS
from .common.output import read_manifests
from .common.raw import RawFile

# Spec §5 tables, with the Step 1 status of each.
SPEC_TABLES = [
    (1, "ref_provider", True), (2, "ref_mpfs", True), (3, "ref_opps", True),
    (4, "ref_ipps_drg", True), (4, "ref_ipps_hospital", True), (5, "ref_asc", True),
    (6, "ref_ncci_ptp", True), (6, "ref_mue", True), (7, "ref_hcris", True),
    (8, "ref_ccn_npi", True), (9, "ref_code_specialty", True), (10, "ref_asp", False), (10, "ref_ndc_hcpcs", False), (10, "ref_hcpcs_code", False),
    (11, "ref_clfs", True), (12, "ref_dmepos", True), (12, "ref_dmepos_rural_zip", True),
    (13, "ref_ambulance", True), (13, "ref_zip_locality", True),
    (14, "ref_anesthesia_cf", True), (14, "ref_anesthesia_base_units", True),
]
# Spec §11 tables (own definition of done; not part of §8)
S11_TABLES = [
    (17, "ref_geo"), (17, "ref_geo_zcta_county"), (19, "ref_quality_hospital"), (19, "ref_quality_measure"),
    (19, "ref_quality_asc"), (20, "ref_ownership"), (20, "ref_chow"), (20, "ref_chow_npi"),
    (21, "ref_nadac"), (21, "ref_ndc_product"), (21, "ref_ndc_package"),
]
# Table 9 spot checks: (code, specialty that must be plausible, specialty that must not be)
SPECIALTY_SPOT_CHECKS = [
    ("27447", "Orthopedic Surgery", "Dermatology"),       # total knee replacement
    ("29881", "Orthopedic Surgery", "Cardiology"),        # knee arthroscopy
    ("45378", "Gastroenterology", "Dermatology"),         # colonoscopy
    ("66984", "Ophthalmology", "Dermatology"),            # cataract surgery
    ("73721", "Diagnostic Radiology", "Psychiatry"),      # MRI knee
    ("93000", "Cardiology", "Ophthalmology"),             # ECG
    ("17000", "Dermatology", "Cardiology"),               # destroy skin lesion
    ("90837", "Licensed Clinical Social Worker", "Orthopedic Surgery"),  # psychotherapy 60 min
    ("88305", "Pathology", "Psychiatry"),                 # tissue exam
    ("99214", "Internal Medicine", None),                 # office visit
]
TEST_CODES = ["99214", "45378", "29881", "73721", "27447"]

# Known values from the files themselves (hand-checked), used as golden checks.
GOLDEN = [
    # (description, sql, expected)
    ("MPFS 99214 Ohio non-facility, Q4 2026 (hand calc: (1.92*1.000+2.00*0.913+0.14*1.008)*33.4009)",
     "SELECT rate_nonfacility FROM mpfs_rate('99214', DATE '2026-11-15')", 129.83),
    ("MPFS 99214 Ohio facility, Q4 2026", "SELECT rate_facility FROM mpfs_rate('99214', DATE '2026-11-15')", 83.18),
    ("MPFS 27447 non-facility is NA (null)", "SELECT rate_nonfacility FROM mpfs_rate('27447', DATE '2026-11-15')", None),
    ("ASC 29881 Oct 2026 (Addendum AA)", "SELECT payment_rate FROM ref_asc WHERE hcpcs='29881' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 1644.87),
    ("ASC 73721 Oct 2026 (Addendum BB)", "SELECT payment_rate FROM ref_asc WHERE hcpcs='73721' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 131.48),
    ("Anesthesia CF Ohio Q4 2026 (non-QP)", "SELECT anesthesia_cf FROM ref_anesthesia_cf WHERE carrier='15202' AND locality='00' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 20.25),
    ("OPPS 27447 national rate, Oct 2026 Addendum B (weight 143.4859 x CF ~91.415)",
     "SELECT payment_rate_national FROM ref_opps WHERE hcpcs='27447' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 13116.76),
    ("IPPS DRG 470 at Miami Valley Hospital (360051), FY2027: (4245.76*0.9182+2602.24)*1.9563",
     "SELECT wage_adjusted_operating FROM ipps_payment('470', DATE '2026-11-15', '360051')", 12717.32),
    ("CLFS 0001U national limit, Q4 2026 (PUF_CLFS_CY2026_Q4V1)",
     "SELECT rate FROM clfs_rate('0001U', DATE '2026-11-15')", 720.00),
    ("DMEPOS A4221 Ohio non-rural fee, Oct 2026 (DMEPOS_OCT)",
     "SELECT fee_nonrural FROM ref_dmepos WHERE hcpcs='A4221' AND modifier='' AND state='OH' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 25.87),
    ("DMEPOS A4221 Ohio rural fee, Oct 2026", "SELECT fee_rural FROM ref_dmepos WHERE hcpcs='A4221' AND modifier='' AND state='OH' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 29.07),
    ("Ambulance A0427 (ALS emergency) urban, carrier 01112 locality 05, CY2026",
     "SELECT rate_urban FROM ref_ambulance WHERE carrier='01112' AND locality='05' AND hcpcs='A0427' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 709.75),
    ("Anesthesia base units 00100", "SELECT base_units FROM ref_anesthesia_base_units WHERE hcpcs='00100' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 5),
    ("MUE 27447 practitioner Q4 2026", "SELECT mue_value FROM ref_mue WHERE hcpcs='27447' AND setting='practitioner' AND DATE '2026-11-15' BETWEEN effective_start AND effective_end", 1),
]

# Record counts CMS publishes on the NCCI PTP page for v32.3 (Q4 2026).
NCCI_PART_COUNTS = {
    "ccioph-v323r0-f1": 475_042, "ccioph-v323r0-f2": 474_962,
    "ccioph-v323r0-f3": 475_041, "ccioph-v323r0-f4": 443_837,
    "ccipra-v323r0-f1": 675_157, "ccipra-v323r0-f2": 674_914,
    "ccipra-v323r0-f3": 675_035, "ccipra-v323r0-f4": 612_539,
}


@dataclass
class Check:
    section: str
    name: str
    status: str            # PASS / FAIL / NOT RUN / INFO
    detail: str = ""


@dataclass
class Report:
    created_at: str
    checks: list[Check] = field(default_factory=list)
    tables: dict = field(default_factory=dict)
    sections: dict = field(default_factory=dict)
    files: dict = field(default_factory=dict)      # name -> CSV text (written to data/reports/)

    def add(self, *a, **k):
        self.checks.append(Check(*a, **k))

    @property
    def counts(self) -> dict:
        out = {"PASS": 0, "FAIL": 0, "NOT RUN": 0, "INFO": 0}
        for c in self.checks:
            out[c.status] = out.get(c.status, 0) + 1
        return out


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}


def _fmt(v):
    return f"{v:,}" if isinstance(v, int) else str(v)


def run(data_root: str | None = None, rehash: bool = True) -> Report:
    paths = config.data_paths(data_root)
    rep = Report(created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    manifests = read_manifests(paths)
    if not paths.duckdb.exists():
        rep.add("setup", "DuckDB file exists", "FAIL", f"{paths.duckdb} not found — run build_duckdb")
        return rep
    con = duckdb.connect(str(paths.duckdb), read_only=True)
    have = _tables(con)
    ctx_geo = config.geography()

    # §8.1 tables + lineage (then the same check for the §11 tables)
    for num, t, required, sec in ([(*x, "§8.1") for x in SPEC_TABLES]
                                  + [(n, t, False, "§11") for n, t in S11_TABLES]):
        if t not in have:
            st = "FAIL" if (required and t in manifests) else "NOT RUN"
            rep.add(sec, f"table {num} {t}", st, "not loaded yet" + ("" if required or sec == "§11" else " (optional)"))
            continue
        cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()]
        missing = [c for c in LINEAGE_COLS if c not in cols]
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        nulls = {c: con.execute(f"SELECT count(*) FROM {t} WHERE {c} IS NULL").fetchone()[0]
                 for c in LINEAGE_COLS if c in cols}
        rng = con.execute(f"SELECT min(effective_start), max(effective_end) FROM {t}").fetchone() if not missing else (None, None)
        hashes = con.execute(f"SELECT count(DISTINCT source_sha256) FROM {t}").fetchone()[0] if not missing else 0
        rep.tables[t] = {"rows": n, "effective_start_min": str(rng[0]), "effective_end_max": str(rng[1]),
                         "distinct_source_hashes": hashes}
        loaded = manifests.get(t, {}).get("rows")
        bad = missing or any(nulls.values()) or n == 0 or (loaded is not None and loaded != n)
        detail = f"{n:,} rows; dates {rng[0]} → {rng[1]}; {hashes} source hash(es)"
        if loaded is not None and loaded != n:
            detail += f"; LOAD WROTE {loaded:,} rows — rerun load_ref {t} and build_duckdb"
        if missing:
            detail += f"; MISSING lineage {missing}"
        if any(nulls.values()):
            detail += f"; nulls in {', '.join(k for k, v in nulls.items() if v)}"
        rep.add(sec, f"table {num} {t}", "FAIL" if bad else "PASS", detail)

    # Raw files unchanged since load (Spec §3.2)
    if rehash:
        seen = set()
        for t, m in manifests.items():
            for s in m["sources"]:
                if s["file"] in seen:
                    continue
                seen.add(s["file"])
                try:
                    now = RawFile(paths.raw, s["file"]).sha256
                    ok = now == s["sha256"]
                    rep.add("§3.2", f"raw file unchanged: {s['file']}", "PASS" if ok else "FAIL",
                            s["sha256"][:16] + ("" if ok else f" → now {now[:16]}"))
                except FileNotFoundError:
                    rep.add("§3.2", f"raw file present: {s['file']}", "FAIL", "file moved or deleted after load")

    # §8.7 source list from the load manifests
    rep.sections["sources"] = [
        {"table": t, "period": src.get("period"), "file": src.get("file"), "sha256": src.get("sha256", ""),
         "page": src.get("page"), "loaded": str(m.get("finished_at", ""))[:10]}
        for t, m in sorted(manifests.items()) for src in m.get("sources", [])]

    # Load warnings
    for t, m in manifests.items():
        for w in m.get("warnings", []):
            rep.add("load", f"{t} warning", "INFO", w)

    # §8.2 provider counts
    if "ref_provider" in have:
        # US states/territories and military codes are 2 letters; NPPES also has
        # free-text foreign provinces. Show the 2-letter codes, sum the rest.
        rows = con.execute("""
            SELECT CASE WHEN regexp_full_match(coalesce(practice_state,''), '[A-Z]{2}') THEN practice_state
                        WHEN practice_state IS NULL THEN '(blank)' ELSE '(other text)' END st,
                   entity_type, count(*) n
            FROM ref_provider GROUP BY ALL ORDER BY st, entity_type""").fetchall()
        rep.sections["provider_counts_by_state"] = [{"state": a, "entity_type": b, "rows": c} for a, b, c in rows]
        fm = con.execute("""SELECT market_part, metro, entity_type, count(*) FROM v_provider_first_market
                            GROUP BY ALL ORDER BY 1, 2, 3""").fetchall()
        rep.sections["provider_first_market"] = [{"part": a, "metro": b, "entity_type": c, "rows": d} for a, b, c, d in fm]
        tot = con.execute("""SELECT count(*), count(*) FILTER (is_deactivated),
                                    count(*) FILTER (primary_flag_missing),
                                    count(*) FILTER (practice_state='OH')
                             FROM ref_provider""").fetchone()
        rep.add("§8.2", "ref_provider counts reported", "PASS" if tot[3] > 0 else "FAIL",
                f"{tot[0]:,} NPIs; {tot[1]:,} deactivated; {tot[2]:,} without a primary flag; {tot[3]:,} in Ohio")
    else:
        rep.add("§8.2", "ref_provider counts reported", "NOT RUN", "ref_provider not loaded")

    # §8.3 one query for the five codes
    try:
        dos = con.execute("SELECT max(effective_start) FROM ref_mpfs").fetchone()[0]
        res = con.execute(f"""SELECT * FROM code_profile(DATE '{dos}')
                              WHERE hcpcs IN ({",".join(f"'{c}'" for c in TEST_CODES)}) ORDER BY hcpcs""").fetchall()
        cols = [d[0] for d in con.description]
        rep.sections["code_profile"] = {"date_of_service": str(dos), "rows": [dict(zip(cols, r)) for r in res]}
        parts = [p for p, tb in (("OPPS", "ref_opps"), ("ASC", "ref_asc"), ("NCCI", "ref_ncci_ptp")) if tb not in have]
        st = "PASS" if len(res) == 5 and not parts else ("FAIL" if len(res) < 5 else "NOT RUN")
        rep.add("§8.3", "5-code profile in one query", st,
                f"{len(res)} of 5 codes returned for {dos}" + (f"; missing tables: {parts}" if parts else ""))
    except duckdb.Error as e:
        rep.add("§8.3", "5-code profile in one query", "NOT RUN", str(e).splitlines()[0])

    # §8.4 DRG 470 at three named Ohio hospitals (config/geography.yaml)
    ccns = ctx_geo.get("drg470_test_ccns") or []
    if not {"ref_ipps_drg", "ref_ipps_hospital"} <= have:
        rep.add("§8.4", "DRG 470 wage-adjusted IPPS payment at 3 Ohio hospitals", "NOT RUN",
                "needs table 4 (IPPS)")
    elif len(ccns) < 3:
        rep.add("§8.4", "DRG 470 wage-adjusted IPPS payment at 3 Ohio hospitals", "NOT RUN",
                "set drg470_test_ccns in config/geography.yaml")
    else:
        dos = con.execute("SELECT max(effective_start) FROM ref_ipps_drg").fetchone()[0]
        res = []
        for c in ccns:
            r = con.execute(f"SELECT * FROM ipps_payment('470', DATE '{dos}', '{c}')").fetchall()
            cols = [d[0] for d in con.description]
            res += [dict(zip(cols, x)) for x in r]
        ok = len(res) == len(ccns) and all(x["wage_adjusted_operating"] for x in res)
        rep.sections["drg470"] = {"date_of_service": str(dos), "rows": res}
        rep.add("§8.4", "DRG 470 wage-adjusted IPPS payment at 3 Ohio hospitals", "PASS" if ok else "FAIL",
                "; ".join(f"{x['hospital_name']} ${x['wage_adjusted_operating']:,.2f}" for x in res)
                or f"no rows for {ccns}")

    # §8.5 date-of-service query. Spec example: 99214 Ohio on 2024-06-15 (RVU24B, Apr-Jun 2024).
    try:
        def r(dos):
            return con.execute(f"SELECT rate_nonfacility, period FROM mpfs_rate('99214', DATE '{dos}')").fetchall()
        fmt = lambda x: f"{x[0][0]} ({x[0][1]})" if x else "no row"
        r26 = r("2026-11-15")
        r_spec = r("2024-06-15")
        if r_spec:
            ok = len(r_spec) == 1 and r26 and r_spec[0][0] != r26[0][0] and r_spec[0][1].startswith("2024")
            rep.add("§8.5", "99214 Ohio on 2024-06-15 returns the 2024 rate (Spec example)", "PASS" if ok else "FAIL",
                    f"2024-06-15 → {fmt(r_spec)}; 2026-11-15 → {fmt(r26)}")
        else:
            rep.add("§8.5", "99214 Ohio on 2024-06-15 returns the 2024 rate (Spec example)", "NOT RUN",
                    "no MPFS release covers 2024-06-15: add RVU24B (Apr-Jun 2024) to MPFS2024B")
        extra = {d: r(d) for d in ("2024-08-15", "2025-11-15")}
        got = [x for x in [*extra.values(), r26] if x]
        if len(got) > 1:
            ok = all(len(x) == 1 for x in got) and len({x[0][0] for x in got}) == len(got)
            rep.add("§8.5", "99214 Ohio rate differs between loaded releases", "PASS" if ok else "FAIL",
                    "; ".join(f"{d} → {fmt(x)}" for d, x in extra.items()) + f"; 2026-11-15 → {fmt(r26)}")
        gap = con.execute("SELECT count(*) FROM mpfs_rate('99214', DATE '2023-06-15')").fetchone()[0]
        rep.add("§8.5", "date before every loaded release returns no rate", "PASS" if gap == 0 else "FAIL",
                f"2023-06-15 → {gap} rows")
    except duckdb.Error as e:
        rep.add("§8.5", "date-of-service query", "NOT RUN", str(e).splitlines()[0])

    # §2 history: 3 years (2024, 2025, 2026) for the quarterly / yearly tables
    for t in ("ref_mpfs", "ref_opps", "ref_asc", "ref_mue", "ref_ipps_drg", "ref_ipps_hospital",
              "ref_clfs", "ref_dmepos", "ref_dmepos_rural_zip", "ref_ambulance", "ref_zip_locality",
              "ref_anesthesia_cf"):
        if t not in have:
            continue
        yrs = sorted({str(r[0]) for r in con.execute(
            f"SELECT DISTINCT year(effective_start) FROM {t}").fetchall()})
        need = {"2024", "2025", "2026"}
        rep.add("§2", f"{t}: releases for 2024, 2025 and 2026", "PASS" if need <= set(yrs) else "INFO",
                f"years with a release: {', '.join(yrs)}" + ("" if need <= set(yrs) else
                f"; missing {', '.join(sorted(need - set(yrs)))}"))

    # Table 10: ASP payment limits + NDC-HCPCS crosswalks (meshkor-step1-asp-schema.md)
    if {"ref_asp", "ref_ndc_hcpcs"} <= have:
        want = {f"{y}Q{q}" for y in (2024, 2025, 2026) for q in (1, 2, 3, 4)}
        for t in ("ref_asp", "ref_ndc_hcpcs"):
            got = {r[0] for r in con.execute(f"SELECT DISTINCT period FROM {t}").fetchall()}
            rep.add("T10", f"{t}: 12 quarters 2024Q1-2026Q4", "PASS" if want <= got else "FAIL",
                    f"{len(got & want)} of 12" + ("" if want <= got else f"; missing {', '.join(sorted(want - got))}"))
        rows = con.execute("""SELECT period, count(*) FROM ref_asp WHERE price_type = 'ASP'
                              GROUP BY 1 ORDER BY 1""").fetchall()
        bad = [f"{p} {n}" for p, n in rows if not 700 <= n <= 1200]
        rep.add("T10", "ASP rows per quarter 700-1,200", "FAIL" if bad else "PASS",
                "; ".join(bad) or f"{min(n for _, n in rows):,}-{max(n for _, n in rows):,}")
        rows = con.execute("""SELECT period, count(*) FROM ref_ndc_hcpcs WHERE crosswalk_type = 'ASP'
                              GROUP BY 1 ORDER BY 1""").fetchall()
        bad = [f"{p} {n}" for p, n in rows if not 6000 <= n <= 9000]
        rep.add("T10", "ASP crosswalk rows per quarter 6,000-9,000", "FAIL" if bad else "PASS",
                "; ".join(bad) or f"{min(n for _, n in rows):,}-{max(n for _, n in rows):,}")
        n1 = con.execute("SELECT count(*) FROM ref_asp WHERE hcpcs IS NULL AND price_type <> 'NOC'").fetchone()[0]
        n2 = con.execute("SELECT count(*) FROM ref_ndc_hcpcs WHERE hcpcs IS NULL AND crosswalk_type <> 'NOC'").fetchone()[0]
        rep.add("T10", "HCPCS empty only on NOC rows", "PASS" if n1 + n2 == 0 else "FAIL",
                f"ref_asp {n1}, ref_ndc_hcpcs {n2}")
        d1 = con.execute("""SELECT count(*) FROM (SELECT 1 FROM ref_asp GROUP BY hcpcs, description, period,
                            price_type HAVING count(*) > 1)""").fetchone()[0]
        rep.add("T10", "ref_asp: no duplicate keys", "PASS" if d1 == 0 else "FAIL", f"{d1} duplicate keys")
        d2 = con.execute("""SELECT crosswalk_type, count(*) FROM (SELECT crosswalk_type FROM ref_ndc_hcpcs
                            GROUP BY ndc, hcpcs, description, period, crosswalk_type HAVING count(*) > 1)
                            GROUP BY 1 ORDER BY 1""").fetchall()
        rep.add("T10", "ref_ndc_hcpcs: duplicate rows in the CMS files (kept as published)", "INFO",
                "; ".join(f"{a} {b}" for a, b in d2) or "none")
        nx = con.execute("""SELECT count(*) FROM ref_asp a WHERE a.price_type = 'ASP' AND a.period = '2026Q4'
                            AND NOT EXISTS (SELECT 1 FROM ref_ndc_hcpcs x WHERE x.hcpcs = a.hcpcs
                                            AND x.period = a.period)""").fetchone()[0]
        rep.add("T10", "2026Q4 ASP codes with no crosswalk NDC (CMS prices some codes without NDCs)", "INFO",
                f"{nx:,} codes")
        g = con.execute("SELECT payment_limit FROM asp_price('J9271', DATE '2026-11-15')").fetchall()
        rep.add("T10", "golden: J9271 (pembrolizumab 1 mg) payment limit Oct 2026 = 62.253",
                "PASS" if g and abs(g[0][0] - 62.253) < 0.0005 else "FAIL", str(g[0][0]) if g else "no row")
    else:
        rep.add("T10", "ASP tables", "NOT RUN", "load_ref ref_asp ref_ndc_hcpcs, then build_duckdb")

    # HCPCS Level II quarterly file
    if "ref_hcpcs_code" in have:
        want = {f"{y}Q{q}" for y in (2024, 2025, 2026) for q in (1, 2, 3, 4)}
        got = {r[0] for r in con.execute("SELECT DISTINCT period FROM ref_hcpcs_code").fetchall()}
        rep.add("T10", "ref_hcpcs_code: 12 quarters 2024Q1-2026Q4", "PASS" if want <= got else "FAIL",
                f"{len(got & want)} of 12" + ("" if want <= got else f"; missing {', '.join(sorted(want - got))}"))
        dup = con.execute("""SELECT count(*) FROM (SELECT 1 FROM ref_hcpcs_code WHERE record_type = 'code'
                             GROUP BY hcpcs, period HAVING count(*) > 1)""").fetchone()[0]
        rep.add("T10", "ref_hcpcs_code: 1 row per code per quarter", "PASS" if dup == 0 else "FAIL", f"{dup} duplicates")
        cpt = con.execute("""SELECT count(*) FROM ref_hcpcs_code WHERE record_type = 'code'
                             AND (regexp_matches(hcpcs, '^[0-9]') OR hcpcs LIKE 'D%') AND long_description IS NOT NULL""").fetchone()[0]
        rep.add("§10", "ref_hcpcs_code: no CPT/CDT descriptions", "PASS" if cpt == 0 else "FAIL", f"{cpt} rows")
        if "ref_asp" in have:
            nx = con.execute("""SELECT count(*) FROM ref_asp a WHERE a.price_type = 'ASP' AND a.period = '2026Q4'
                                AND NOT EXISTS (SELECT 1 FROM ref_hcpcs_code h WHERE h.hcpcs = a.hcpcs
                                                AND h.period = a.period)""").fetchone()[0]
            rep.add("T10", "2026Q4 ASP codes found in the HCPCS file (CPT vaccine codes 90xxx are not in it)", "INFO",
                    f"{nx:,} ASP codes not in the HCPCS Level II file")

    # §8.6 table 8 match report: Ohio Type 2 hospital NPIs (NPPES taxonomy 282N*) with no CCN
    if not {"ref_ccn_npi", "ref_provider"} <= have:
        rep.add("§8.6", "CCN–NPI match report (Ohio hospitals)", "NOT RUN", "needs tables 1 and 8")
    else:
        rows = con.execute("""
            SELECT primary_taxonomy, (is_subpart = 'Y') AS subpart, count(*) n,
                   count(*) FILTER (WHERE ccns IS NULL) unmatched
            FROM v_ccn_npi_ohio_report GROUP BY ALL ORDER BY 1, 2""").fetchall()
        rep.sections["ccn_npi_match"] = [{"taxonomy": a, "subpart": b, "npis": c, "unmatched": d}
                                         for a, b, c, d in rows]
        acute = [x for x in rows if x[0] == "282N00000X" and not x[1]]
        n, u = sum(x[2] for x in acute), sum(x[3] for x in acute)
        rep.add("§8.6", "Ohio acute-care NPIs (282N00000X, not subparts) without a CCN, all NPPES records", "INFO",
                f"{u:,} of {n:,} unmatched ({(u / n if n else 0):.1%})")
        cats = con.execute("""
            SELECT npi_category, count(*) n, count(*) FILTER (WHERE ccns IS NULL) unmatched
            FROM v_ccn_npi_ohio_report WHERE primary_taxonomy = '282N00000X' AND is_subpart <> 'Y'
            GROUP BY 1 ORDER BY 1""").fetchall()
        rep.sections["ccn_npi_categories"] = [{"category": a, "npis": b, "unmatched": c} for a, b, c in cats]
        # Target (Spec §6: < 5 % for acute-care hospitals): NPIs that can have a CCN. A federal,
        # not-a-hospital or stale NPI counts only when it did match.
        h = {a: (b, c) for a, b, c in cats}
        hn, hu = h.get("hospital", (0, 0))
        matched_other = sum(b - c for a, (b, c) in h.items() if a != "hospital")
        den = hn + matched_other
        pct = hu / den if den else 1
        rep.add("§8.6", "Ohio acute-care hospital NPIs without a CCN (federal, not-a-hospital, stale NPPES "
                "records left out): target < 5 %", "PASS" if den and pct < 0.05 else "FAIL",
                f"{hu:,} of {den:,} unmatched ({pct:.1%}); by category: "
                + "; ".join(f"{a} {c:,}/{b:,} unmatched" for a, b, c in cats))
        n_all, u_all = sum(x[2] for x in rows), sum(x[3] for x in rows)
        rep.add("§8.6", "all Ohio 282N* hospital NPIs (incl. subparts) without a CCN", "INFO",
                f"{u_all:,} of {n_all:,} unmatched ({(u_all / n_all if n_all else 0):.1%}); "
                "list with categories in data/reports/ccn_npi_ohio_unmatched.csv")
        cov = con.execute("""
            SELECT count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM ref_ccn_npi c WHERE c.ccn = h.ccn))
            FROM ref_ipps_hospital h WHERE h.state = 'OH'
              AND h.effective_start = (SELECT max(effective_start) FROM ref_ipps_hospital)""").fetchone() if "ref_ipps_hospital" in have else None
        if cov:
            rep.add("§8.6", "Ohio IPPS hospitals (CCN) with at least 1 NPI", "PASS" if cov[0] and cov[1] == cov[0]
                    else "INFO", f"{cov[1]:,} of {cov[0]:,}")
        src = con.execute("SELECT match_source, count(*), count(DISTINCT ccn), count(DISTINCT npi) "
                          "FROM ref_ccn_npi GROUP BY 1 ORDER BY 1").fetchall()
        rep.add("§8.6", "CCN–NPI pairs by source", "INFO",
                "; ".join(f"{a}: {b:,} pairs, {c:,} CCNs, {d:,} NPIs" for a, b, c, d in src))
        miss = con.execute("""SELECT npi_category, npi, provider_name, primary_taxonomy, is_subpart, practice_address_1,
                                     practice_city, zip5, last_update_date
                              FROM v_ccn_npi_ohio_report WHERE ccns IS NULL
                              ORDER BY npi_category, is_subpart, provider_name""")
        cols = [d[0] for d in miss.description]
        lines = [",".join(cols)] + [",".join('"' + str("" if v is None else v).replace('"', "'") + '"' for v in r)
                                    for r in miss.fetchall()]
        rep.files["ccn_npi_ohio_unmatched.csv"] = "\n".join(lines) + "\n"
        # Review list: best enrolled Ohio hospital for each unmatched 'hospital' NPI (same city or zip3,
        # similar name or same house number + street). Copy approved rows to config/ccn_npi_manual.csv.
        sug = con.execute("""
            WITH u AS (
              SELECT npi, provider_name, practice_address_1, practice_city, zip5,
                     regexp_replace(upper(provider_name), '[^A-Z0-9 ]', ' ', 'g') AS nm,
                     regexp_extract(upper(practice_address_1), '^[0-9]+ +[A-Z0-9]+') AS st
              FROM v_ccn_npi_ohio_report WHERE ccns IS NULL AND npi_category = 'hospital'),
            e AS (
              SELECT DISTINCT ccn, organization_name, dba_name, address_1, city, zip5,
                     regexp_replace(upper(coalesce(organization_name, '')), '[^A-Z0-9 ]', ' ', 'g') AS nm1,
                     regexp_replace(upper(coalesce(dba_name, '')), '[^A-Z0-9 ]', ' ', 'g') AS nm2,
                     regexp_extract(upper(coalesce(address_1, '')), '^[0-9]+ +[A-Z0-9]+') AS st
              FROM ref_ccn_npi WHERE match_source = 'enrollment' AND state = 'OH'),
            c AS (
              SELECT u.npi, u.provider_name, u.practice_address_1, u.practice_city, u.zip5,
                     e.ccn, e.organization_name, e.dba_name, e.address_1 AS enrolled_address, e.city AS enrolled_city,
                     round(greatest(jaro_winkler_similarity(u.nm, e.nm1), jaro_winkler_similarity(u.nm, e.nm2)), 3) AS name_score,
                     (u.st <> '' AND u.st = e.st) AS same_street
              FROM u JOIN e ON upper(u.practice_city) = upper(e.city) OR left(u.zip5, 3) = left(e.zip5, 3))
            SELECT * EXCLUDE (rk) FROM (
              SELECT *, row_number() OVER (PARTITION BY npi ORDER BY same_street DESC, name_score DESC) rk
              FROM c WHERE same_street OR name_score >= 0.85)
            WHERE rk <= 3 ORDER BY provider_name, npi, same_street DESC, name_score DESC""")
        scols = [d[0] for d in sug.description]
        srows = sug.fetchall()
        rep.add("§8.6", "match suggestions for review", "INFO",
                f"{len({r[0] for r in srows}):,} unmatched hospital NPIs have a likely CCN; review "
                "data/reports/ccn_npi_ohio_suggestions.csv and copy approved rows to config/ccn_npi_manual.csv")
        rep.files["ccn_npi_ohio_suggestions.csv"] = "\n".join(
            [",".join(["approved"] + scols)]
            + [",".join([""] + ['"' + str("" if v is None else v).replace('"', "'") + '"' for v in r]) for r in srows]) + "\n"

    # §8.6 table 9 spot checks (Spec: 27447 -> orthopedic surgery, not dermatology)
    if "ref_code_specialty" not in have:
        rep.add("§8.6", "specialty filter spot checks", "NOT RUN", "needs table 9")
    else:
        for code, yes, no in SPECIALTY_SPOT_CHECKS:
            r = con.execute("SELECT medicare_specialty, plausible, specialty_share, specialty_rank "
                            "FROM specialty_plausible(?)", [code]).fetchall()
            if not r:
                rep.add("§8.6", f"spot check {code}", "NOT RUN", "code not in utilization data")
                continue
            def hit(pat):
                return [x for x in r if pat.lower() in (x[0] or "").lower()]
            y, n_ = hit(yes), hit(no) if no else []
            ok = any(x[1] for x in y) and not any(x[1] for x in n_)
            top = ", ".join(f"{x[0]} {x[2]:.0%}" for x in r[:3])
            rep.add("§8.6", f"spot check {code}: {yes} yes" + (f", {no} no" if no else ""), "PASS" if ok else "FAIL",
                    f"top: {top}; {sum(1 for x in r if x[1])} plausible specialties")

    # Golden values
    for desc, sql, expected in GOLDEN:
        try:
            got = con.execute(sql).fetchall()
            val = got[0][0] if got else "no row"
            ok = (val is None and expected is None) or (isinstance(val, (int, float)) and expected is not None
                                                         and abs(float(val) - expected) < 0.005)
            rep.add("golden", desc, "PASS" if ok else "FAIL", f"expected {expected}, got {val}")
        except duckdb.Error as e:
            rep.add("golden", desc, "NOT RUN", str(e).splitlines()[0])

    # NCCI completeness: each part's row count = the count CMS publishes
    if "ref_ncci_ptp" in have:
        got = dict(con.execute("SELECT source_file, count(*) FROM ref_ncci_ptp GROUP BY 1").fetchall())
        for part, want in NCCI_PART_COUNTS.items():
            n = sum(v for k, v in got.items() if part in k)
            if not n:
                rep.add("NCCI", f"part {part}", "NOT RUN", "not downloaded yet")
            else:
                rep.add("NCCI", f"part {part}", "PASS" if n == want else "FAIL", f"{n:,} rows; CMS page says {want:,}")
    con.close()
    return rep


def to_markdown(rep: Report) -> str:
    c = rep.counts
    out = [f"# MeshKor Step 1 — verification report", "",
           f"Created {rep.created_at} · Python {platform.python_version()} · DuckDB {duckdb.__version__}", "",
           f"**{c['PASS']} pass · {c['FAIL']} fail · {c['NOT RUN']} not run · {c['INFO']} info**", ""]
    sec = None
    for ch in rep.checks:
        if ch.section != sec:
            sec = ch.section
            out += ["", f"## {sec}", "", "| Status | Check | Detail |", "|---|---|---|"]
        out.append(f"| {ch.status} | {ch.name} | {ch.detail.replace('|', '/')} |")
    if "code_profile" in rep.sections:
        cp = rep.sections["code_profile"]
        out += ["", f"## §8.3 code profile (Ohio, DOS {cp['date_of_service']})", ""]
        if cp["rows"]:
            keys = list(cp["rows"][0])
            out += ["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
            out += ["| " + " | ".join("" if r[k] is None else str(r[k]) for k in keys) + " |" for r in cp["rows"]]
    if "drg470" in rep.sections:
        d = rep.sections["drg470"]
        keys = ["ccn", "hospital_name", "wage_index", "relative_weight", "operating_base_rate",
                "wage_adjusted_operating", "ime_payment", "dsh_payment", "uncompensated_care",
                "capital_payment", "estimated_total_payment"]
        out += ["", f"## §8.4 DRG 470 (DOS {d['date_of_service']})", "",
                "| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
        out += ["| " + " | ".join("" if r.get(k) is None else str(r[k]) for k in keys) + " |" for r in d["rows"]]
    if "ccn_npi_match" in rep.sections:
        out += ["", "## §8.6 CCN–NPI match, Ohio Type 2 hospital NPIs (NPPES taxonomy 282N*)", "",
                "| Taxonomy | Subpart | NPIs | No CCN | % |", "|---|---|---|---|---|"]
        out += [f"| {r['taxonomy']} | {'yes' if r['subpart'] else 'no'} | {r['npis']:,} | {r['unmatched']:,} | "
                f"{(r['unmatched'] / r['npis'] if r['npis'] else 0):.1%} |" for r in rep.sections["ccn_npi_match"]]
    if "sources" in rep.sections:
        out += ["", "## §8.7 sources (page, file, SHA-256, load date)", "",
                "| Table | Release | File | SHA-256 | Loaded | CMS page |", "|---|---|---|---|---|---|"]
        out += [f"| {r['table']} | {r['period']} | {r['file']} | {r['sha256'][:16]} | {r['loaded']} | {r['page'] or ''} |"
                for r in rep.sections["sources"]]
    if "ccn_npi_categories" in rep.sections:
        out += ["", "## §8.6 Ohio acute-care NPIs (282N00000X, not subparts) by category", "",
                "| Category | NPIs | No CCN |", "|---|---|---|"]
        out += [f"| {r['category']} | {r['npis']:,} | {r['unmatched']:,} |" for r in rep.sections["ccn_npi_categories"]]
    if "provider_first_market" in rep.sections:
        out += ["", "## §8.2 providers in the first market (Ohio + border zip3)", "",
                "| Part | Metro | Entity type | NPIs |", "|---|---|---|---|"]
        out += [f"| {r['part']} | {r['metro']} | {r['entity_type']} | {r['rows']:,} |"
                for r in rep.sections["provider_first_market"]]
    if "provider_counts_by_state" in rep.sections:
        out += ["", "## §8.2 providers by practice state and entity type", "",
                "| State | Entity type | NPIs |", "|---|---|---|"]
        out += [f"| {r['state']} | {r['entity_type']} | {r['rows']:,} |" for r in rep.sections["provider_counts_by_state"]]
    return "\n".join(out) + "\n"


def write(rep: Report, data_root: str | None = None) -> Path:
    paths = config.data_paths(data_root)
    d = paths.root / "reports"
    d.mkdir(exist_ok=True)
    stamp = rep.created_at.replace(":", "").replace("-", "")[:15]
    md = to_markdown(rep)
    (d / f"verify_{stamp}.md").write_text(md, encoding="utf-8")
    (d / "verify_latest.md").write_text(md, encoding="utf-8")
    for name, text in rep.files.items():
        (d / name).write_text(text, encoding="utf-8")
    (d / "verify_latest.json").write_text(json.dumps(
        {"created_at": rep.created_at, "counts": rep.counts, "checks": [asdict(c) for c in rep.checks],
         "tables": rep.tables, "sections": rep.sections}, indent=2, default=str), encoding="utf-8")
    return d / "verify_latest.md"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root")
    ap.add_argument("--no-rehash", action="store_true", help="skip re-hashing raw files")
    a = ap.parse_args(argv)
    rep = run(a.data_root, rehash=not a.no_rehash)
    p = write(rep, a.data_root)
    print(to_markdown(rep))
    print(f"Report written to {p}")
    return 1 if rep.counts["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
