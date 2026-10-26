"""A tiny meshkor.duckdb for the pricing tests. Invented numbers, real table layouts.

Hospital 360085 (OSU) has a price file from 2026-07-01; 360242 (James) has none.
The macros come from sql/views.sql, so the tests use the same SQL as production.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from pipeline import duckdb_build

MRF_FILE = "MRF/2026-10/360085/31-1340739_OHIO-STATE-UNIVERSITY-HOSPITALS_standardcharges.csv"
SHA = "a" * 64
WAGE = 0.95
CCR = 0.21

# (code or None, ms_drg or None, setting, payer_group, payer_name, plan, dollar, percentage, cash)
MRF = [
    ("99285", None, "Outpatient", "Anthem", "Anthem", "Anthem PPO", 1400.0, None, None),
    ("99285", None, "Outpatient", "Anthem", "Anthem", "Anthem HMO", 1500.0, None, None),
    ("99285", None, "Outpatient", "UnitedHealthcare", "UHC", "UHC Choice", 1300.0, None, None),
    ("99285", None, "Outpatient", "Aetna", "Aetna", "Aetna Open", 1700.0, None, None),
    ("99285", None, "Inpatient", "Anthem", "Anthem", "Anthem PPO", 9999.0, None, None),     # wrong setting, never used
    ("70450", None, "Both", "Anthem", "Anthem", "Anthem PPO", None, 40.0, None),           # percentage only
    ("70450", None, "Both", "Aetna", "Aetna", "Aetna Open", 700.0, None, None),
    ("70450", None, "Both", "UnitedHealthcare", "UHC", "UHC Choice", 800.0, None, None),
    ("70450", None, "Both", "Cigna", "Cigna", "Cigna OAP", 0.62, None, None),           # a factor in the dollar column
    ("85025", None, "Both", "Anthem", "Anthem", "Anthem PPO", 20.0, None, 15.0),
    # OSU style: "fee schedule" row whose dollar column holds a factor; the real term is in the notes
    ("71046", None, "Outpatient", "Anthem", "Anthem", "Anthem - Blue Access", 2.18, None, None, "226.10% of Medicare"),
    ("71046", None, "Outpatient", "Anthem", "Anthem", "Anthem - Traditional", 200.0, None, None),
    (None, "481", "Inpatient", "UnitedHealthcare", "UHC", "UHC Choice", 22000.0, None, None),
    (None, "481", "Inpatient", "Anthem", "Anthem", "Anthem PPO", 26000.0, None, None),
    (None, "481", "Inpatient", "Aetna", "Aetna", "Aetna Open", None, 55.0, None),
    (None, "470", "Inpatient", "UnitedHealthcare", "UHC", "UHC Choice", 18000.0, None, None),
]

# hcpcs, si, apc, national
OPPS = [("99285", "V", "5025", 600.0), ("70450", "S", "5522", 110.0), ("71046", "S", "5521", 70.0),
        ("72125", "S", "5522", 110.0), ("36415", "Q4", None, None), ("85025", "Q4", None, None),
        ("80053", "Q4", None, None), ("96374", "S", "5693", 200.0), ("J2270", "N", None, None),
        ("J2405", "N", None, None), ("J7030", "N", None, None), ("25607", "J1", "5114", 6800.0),
        ("29125", "S", "5101", 150.0), ("72131", "S", "5522", 110.0), ("73030", "S", "5521", 70.0)]
CLFS = [("36415", 3.0), ("85025", 7.5), ("80053", 10.0)]


def build(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / "meshkor.duckdb"
    p.unlink(missing_ok=True)
    con = duckdb.connect(str(p))
    x = con.execute
    x("""CREATE TABLE ref_hospital_mrf (ccn VARCHAR, hospital_name VARCHAR, type2_npis VARCHAR, last_updated_on DATE,
         description VARCHAR, modifiers VARCHAR, setting VARCHAR, gross_charge DOUBLE, discounted_cash DOUBLE,
         payer_name VARCHAR, plan_name VARCHAR, negotiated_dollar DOUBLE, negotiated_percentage DOUBLE,
         negotiated_algorithm VARCHAR, notes VARCHAR, estimated_amount DOUBLE, median_amount DOUBLE, pct_10 DOUBLE, pct_90 DOUBLE,
         rate_count INTEGER, methodology VARCHAR, charge_min DOUBLE, charge_max DOUBLE, hcpcs VARCHAR, ms_drg VARCHAR,
         rc VARCHAR, ndc VARCHAR, cdm VARCHAR, drug_unit VARCHAR, drug_type VARCHAR, payer_group VARCHAR,
         source_layout VARCHAR, effective_start DATE, effective_end DATE, source_file VARCHAR, source_sha256 VARCHAR, period VARCHAR)""")
    for code, drg, setting, grp, payer, plan, dollar, pct, cash, *notes in MRF:
        x("""INSERT INTO ref_hospital_mrf (ccn, hospital_name, type2_npis, last_updated_on, setting, payer_group, payer_name,
             plan_name, negotiated_dollar, negotiated_percentage, discounted_cash, hcpcs, ms_drg, notes, gross_charge, source_layout,
             effective_start, effective_end, source_file, source_sha256, period)
             VALUES ('360085', 'Ohio State University Hospitals', '1447359997|1831389550', DATE '2026-07-01', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                     'tall', DATE '2026-07-01', DATE '9999-12-31', ?, ?, '2026-10')""",
          [setting, grp, payer, plan, dollar, pct, cash, code, drg, notes[0] if notes else None, 2064.0 if code == "70450" else None, MRF_FILE, SHA])
    x("""CREATE TABLE ref_opps (hcpcs VARCHAR, description VARCHAR, status_indicator VARCHAR, apc VARCHAR, relative_weight DOUBLE,
         payment_rate_national DOUBLE, national_unadjusted_copay DOUBLE, minimum_unadjusted_copay DOUBLE, source_file VARCHAR,
         source_sha256 VARCHAR, effective_start DATE, effective_end DATE, period VARCHAR)""")
    for per, es, ee in (("2026Q3", "2026-07-01", "2026-09-30"), ("2026Q4", "2026-10-01", "2026-12-31")):
        for code, si, apc, nat in OPPS:
            x("INSERT INTO ref_opps (hcpcs, status_indicator, apc, payment_rate_national, source_file, source_sha256, effective_start, effective_end, period) "
              "VALUES (?, ?, ?, ?, ?, ?, CAST(? AS DATE), CAST(? AS DATE), ?)", [code, si, apc, nat, f"opps/{per}/addendum_b.csv", SHA, es, ee, per])
    x("""CREATE TABLE ref_clfs (hcpcs VARCHAR, modifier VARCHAR, rate DOUBLE, indicator VARCHAR, code_effective_date DATE,
         description VARCHAR, source_file VARCHAR, source_sha256 VARCHAR, effective_start DATE, effective_end DATE, period VARCHAR)""")
    for code, rate in CLFS:
        x("INSERT INTO ref_clfs (hcpcs, modifier, rate, source_file, source_sha256, effective_start, effective_end, period) "
          "VALUES (?, '', ?, 'clfs/2026Q3/clfs.csv', ?, DATE '2026-07-01', DATE '2026-12-31', '2026Q3')", [code, rate, SHA])
    x("""CREATE TABLE ref_mpfs (hcpcs VARCHAR, modifier VARCHAR, carrier VARCHAR, locality VARCHAR, status_code VARCHAR,
         rate_nonfacility DOUBLE, rate_facility DOUBLE, opps_cap_applied BOOLEAN, effective_start DATE, effective_end DATE,
         period VARCHAR, source_file VARCHAR, source_sha256 VARCHAR)""")
    x("INSERT INTO ref_mpfs VALUES ('97110', '', '15202', '00', 'A', 28.0, 25.0, false, DATE '2026-01-01', DATE '2026-12-31', '2026D', 'mpfs/rvu26d.csv', ?)", [SHA])
    x("""CREATE TABLE ref_asp (hcpcs VARCHAR, description VARCHAR, dosage VARCHAR, payment_limit DOUBLE, coinsurance_pct DOUBLE,
         notes VARCHAR, price_type VARCHAR, period VARCHAR, effective_start DATE, effective_end DATE, source_file VARCHAR, source_sha256 VARCHAR)""")
    x("""CREATE TABLE ref_ipps_hospital (ccn VARCHAR, hospital_name VARCHAR, state VARCHAR, wage_index DOUBLE, operating_base_rate DOUBLE,
         capital_base_rate DOUBLE, ime_operating DOUBLE, dsh_operating DOUBLE, ucp_per_claim DOUBLE, vbp_factor DOUBLE, hrrp_factor DOUBLE,
         low_volume_factor DOUBLE, ime_capital DOUBLE, dsh_capital DOUBLE, provider_type VARCHAR, operating_ccr DOUBLE, capital_ccr DOUBLE,
         fiscal_year VARCHAR, effective_start DATE, effective_end DATE, source_file VARCHAR, source_sha256 VARCHAR, period VARCHAR)""")
    for fy, es, ee in (("FY2026", "2025-10-01", "2026-09-30"), ("FY2027", "2026-10-01", "2027-09-30")):
        x("INSERT INTO ref_ipps_hospital VALUES ('360085', 'OHIO STATE UNIVERSITY HOSPITALS', 'OH', ?, 6000, 500, 0.10, 0.05, 1000, 1.0, 1.0, 1.0, "
          "0.02, 0.01, '0', 0.19, 0.02, ?, CAST(? AS DATE), CAST(? AS DATE), 'ipps/impact.txt', ?, ?)", [WAGE, fy, es, ee, SHA, fy])
    x("""CREATE TABLE ref_ipps_drg (ms_drg VARCHAR, ms_drg_title VARCHAR, relative_weight DOUBLE, fiscal_year VARCHAR,
         effective_start DATE, effective_end DATE, source_file VARCHAR, source_sha256 VARCHAR, period VARCHAR)""")
    for drg, title, w in (("481", "HIP AND FEMUR PROCEDURES EXCEPT MAJOR JOINT WITH CC", 2.0),
                          ("480", "HIP AND FEMUR PROCEDURES EXCEPT MAJOR JOINT WITH MCC", 3.0)):
        x("INSERT INTO ref_ipps_drg VALUES (?, ?, ?, 'FY2026', DATE '2025-10-01', DATE '2026-09-30', 'ipps/table5.txt', ?, 'FY2026')", [drg, title, w, SHA])
    x("""CREATE TABLE ref_hcris (ccn VARCHAR, fy_end DATE, cost_to_charge_ratio DOUBLE, is_primary BOOLEAN,
         source_file VARCHAR, source_sha256 VARCHAR)""")
    x("INSERT INTO ref_hcris VALUES ('360085', DATE '2024-06-30', ?, true, 'hcris/HOSP10FY2024.zip', ?)", [CCR, SHA])
    x("""CREATE TABLE ref_ccn_npi (ccn VARCHAR, npi BIGINT, organization_name VARCHAR, dba_name VARCHAR, state VARCHAR)""")
    x("INSERT INTO ref_ccn_npi VALUES ('360085', 1447359997, 'OHIO STATE UNIVERSITY HOSPITALS', NULL, 'OH'), "
      "('360242', 1124127683, 'ARTHUR G JAMES CANCER HOSPITAL', NULL, 'OH')")
    want = {"mpfs_rate", "clfs_rate", "v_hcris_latest", "opps_wage_adjusted", "ipps_payment", "asp_price"}
    for name, sql in duckdb_build.statements():
        if name in want:
            x(sql)
    con.close()
    return p


def opps_adjusted(national: float) -> float:
    return round(national * (0.60 * WAGE + 0.40), 2)


def ipps_total(weight: float) -> float:
    op = 6000 * weight
    return round((op * (1.0 + 1.0 - 1) + op * 0.10 + op * 0.05) * 1.0 + 1000 + 500 * weight * (1 + 0.02 + 0.01), 2)
