"""Step 1 tests. Run from the repo root:  python -m pytest -q

Uses tests/fixtures/raw (trimmed real CMS files + synthetic NPPES, OPPS and
HCRIS files in the documented layouts). No network, no PostgreSQL.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import duckdb
import polars as pl
import pytest

from pipeline import duckdb_build, runner, verify
from pipeline.common.lineage import LINEAGE_COLS

FIX = Path(__file__).parent / "fixtures" / "raw"


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    shutil.copytree(FIX, root / "raw")
    for t in runner.configured_tables():
        try:
            runner.run_table(t, data_root=str(root))
        except FileNotFoundError:
            pass
    duckdb_build.build(str(root))
    con = duckdb.connect(str(root / "meshkor.duckdb"), read_only=True)
    yield root, con
    con.close()


def q(con, sql):
    return con.execute(sql).fetchall()


# ------------------------------------------------------------ lineage, §3
def test_every_table_has_lineage_without_nulls(built):
    _, con = built
    tables = [r[0] for r in q(con, "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'ref_%'")]
    assert len(tables) >= 9
    for t in tables:
        cols = [r[0] for r in q(con, f"DESCRIBE {t}")]
        for c in LINEAGE_COLS:
            assert c in cols, f"{t} lacks {c}"
            assert q(con, f"SELECT count(*) FROM {t} WHERE {c} IS NULL")[0][0] == 0, f"{t}.{c} has nulls"


def test_rerun_gives_same_output(built, tmp_path):
    """Spec §3.6: same input -> same output."""
    root, _ = built
    files = lambda: sorted((root / "ref" / "ref_mpfs").glob("*.parquet"))
    a = pl.concat([pl.read_parquet(f) for f in files()])
    runner.run_table("ref_mpfs", data_root=str(root))
    b = pl.concat([pl.read_parquet(f) for f in files()])
    assert a.equals(b)


def test_no_cpt_or_cdt_descriptions(built):
    """Spec §10: only HCPCS Level II descriptions are stored."""
    _, con = built
    for t in ("ref_mpfs", "ref_asc", "ref_opps"):
        bad = q(con, f"""SELECT DISTINCT hcpcs FROM {t} WHERE description IS NOT NULL
                         AND NOT regexp_matches(hcpcs, '^[A-CE-V][0-9A-Z]{{4}}$')""")
        assert bad == [], f"{t} stores licensed descriptions for {bad}"
    assert q(con, "SELECT description FROM ref_opps WHERE hcpcs='G0463'")[0][0] == "Hospital outpt clinic visit"


# ------------------------------------------------------------ MPFS
def test_mpfs_ohio_rates_match_hand_calc(built):
    _, con = built
    r = q(con, "SELECT rate_nonfacility, rate_facility FROM mpfs_rate('99214', DATE '2026-11-15')")
    assert r == [(129.83, 83.18)]


def test_mpfs_na_setting_is_null_and_modifiers_kept(built):
    _, con = built
    assert q(con, "SELECT rate_nonfacility FROM mpfs_rate('27447', DATE '2026-11-15')") == [(None,)]
    mods = {m for (m,) in q(con, "SELECT modifier FROM ref_mpfs WHERE hcpcs='73721' AND carrier='15202'")}
    assert mods == {"", "26", "TC"}


def test_mpfs_opps_cap_never_creates_a_rate(built):
    _, con = built
    assert q(con, "SELECT count(*) FROM ref_mpfs WHERE pfs_fac IS NULL AND rate_facility IS NOT NULL")[0][0] == 0
    r = q(con, """SELECT pfs_nonfac, rate_nonfacility, opps_cap_applied FROM ref_mpfs
                  WHERE hcpcs='70473' AND modifier='' AND carrier='01112' AND locality='05'""")
    assert r and r[0][1] < r[0][0] and r[0][2]


def test_mpfs_date_of_service_outside_release_returns_nothing(built):
    _, con = built
    assert q(con, "SELECT count(*) FROM mpfs_rate('99214', DATE '2024-06-15')") == [(0,)]


# ------------------------------------------------------------ ASC, MUE, NCCI
def test_asc_rates_and_indicator_meanings(built):
    _, con = built
    r = dict(q(con, "SELECT hcpcs, payment_rate FROM ref_asc"))
    assert r["29881"] == 1644.87 and r["27447"] == 9393.16 and r["73721"] == 131.48
    assert q(con, "SELECT payment_indicator_desc IS NOT NULL FROM ref_asc WHERE hcpcs='29881'") == [(True,)]


def test_mue_both_settings_with_indicator(built):
    _, con = built
    r = q(con, "SELECT setting, mue_value, mue_adjudication_indicator FROM ref_mue WHERE hcpcs='99214' ORDER BY 1")
    assert r == [("hospital", 2, 3), ("practitioner", 2, 3)]


def test_ncci_keeps_deleted_edits_and_flags_modifier_9(built):
    _, con = built
    # Real history in the Q4 2026 hospital file for 00100/99497:
    #   2015-01-01 → 2019-12-31 (mod 1), withdrawn copy (mod 9), re-added 2020-10-01 (open).
    r = q(con, """SELECT CAST(effective_start AS VARCHAR), modifier_indicator,
                         CAST(deletion_date AS VARCHAR), is_applicable FROM ref_ncci_ptp
                  WHERE column_1='00100' AND column_2='99497' ORDER BY 1, 2""")
    assert r == [("2015-01-01", 1, "2019-12-31", True), ("2015-01-01", 9, "2015-01-01", False),
                 ("2020-10-01", 1, None, True)]

    def active(dos):
        return q(con, f"SELECT count(*) FROM ncci_pairs_on_date('99497', DATE '{dos}', p_setting := 'hospital') "
                      "WHERE column_1 = '00100'")[0][0]
    assert active("2018-01-01") == 1     # first edit in force
    assert active("2020-06-01") == 0     # gap: deleted, not yet re-added
    assert active("2021-01-01") == 1     # re-added edit
    assert active("2015-01-01") == 1     # the mod-9 copy is not counted twice


# ------------------------------------------------------------ NPPES
def test_nppes_primary_taxonomy_uses_switch_not_slot_1(built):
    _, con = built
    r = dict((n, (t, f)) for n, t, f in q(con, "SELECT npi, primary_taxonomy, primary_flag_missing FROM ref_provider"))
    assert r[1000000001] == ("207X00000X", False)     # flag on slot 3
    assert r[1000000003] == ("208600000X", True)      # no flag -> slot 1 + flag


def test_nppes_deactivations_kept_with_dates(built):
    _, con = built
    r = {n: (str(d), x, str(e)) for n, d, x, e in
         q(con, "SELECT npi, deactivation_date, is_deactivated, effective_end FROM ref_provider")}
    assert r[1000000004] == ("2025-07-15", True, "2025-07-15")   # in main file
    assert r[1000000006] == ("2026-09-30", True, "2026-09-30")   # only in deactivation report
    assert r[1000000005][1] is False and r[1000000005][2] == "9999-12-31"  # reactivated


def test_nppes_ccn_from_other_identifiers_and_market_view(built):
    _, con = built
    assert q(con, "SELECT medicare_oscar_ids FROM ref_provider WHERE npi=1000000002") == [(["360001"],)]
    parts = dict(q(con, "SELECT npi, market_part FROM v_provider_first_market"))
    assert parts[1000000003] == "border" and parts[1000000001] == "ohio"
    assert 1000000004 not in parts


def test_nppes_stops_on_missing_column():
    from pipeline.ref.nppes import resolve_columns
    _, _, missing = resolve_columns(["NPI", "Entity Type Code"])
    assert "Provider Business Practice Location Address State Name" in missing


# ------------------------------------------------------------ OPPS, HCRIS
def test_opps_parses_money_and_si(built):
    _, con = built
    assert q(con, "SELECT status_indicator, apc, payment_rate_national FROM ref_opps WHERE hcpcs='45378'") == [("J1", "5312", 1300.0)]


def test_hcris_ccr_state_type_and_primary(built):
    _, con = built
    r = {(c, str(b)): (ccr, st, ft, p) for c, b, ccr, st, ft, p in
         q(con, "SELECT ccn, fy_begin, cost_to_charge_ratio, state, facility_type, is_primary FROM ref_hcris")}
    assert r[("360001", "2024-01-01")] == (0.25, "OH", "short_term_acute", True)
    # FY change: two different periods in one year -> both primary
    assert r[("360002", "2023-07-01")][3] and r[("360002", "2024-07-01")][3]
    # zero charges -> no ratio; CCN 1300 range = critical access
    assert r[("361300", "2024-01-01")][:3] == (None, "OH", "critical_access")


# ------------------------------------------------------------ §8 report
def test_verify_report_golden_values_pass(built):
    root, _ = built
    rep = verify.run(str(root), rehash=True)
    golden = [c for c in rep.checks if c.section == "golden"]
    assert golden and all(c.status == "PASS" for c in golden), [c for c in golden if c.status != "PASS"]
    assert next(c for c in rep.checks if c.section == "§8.3").status == "PASS"
    md = verify.to_markdown(rep)
    assert "1000000001" not in md   # report carries counts only, no provider rows


# ------------------------------------------------------------ IPPS (table 4)
def test_ipps_drg_470_wage_adjusted_payment(built):
    _, con = built
    r = q(con, "SELECT relative_weight FROM ref_ipps_drg WHERE ms_drg = '470' AND fiscal_year = 'FY2027'")
    assert r == [(1.9563,)]
    # Miami Valley: wage index 0.9182 <= 1 -> Table 1B full update
    r = q(con, "SELECT operating_labor_rate, operating_nonlabor_rate, operating_base_rate "
               "FROM ref_ipps_hospital WHERE ccn = '360051' AND fiscal_year = 'FY2027'")
    assert r == [(4245.76, 2602.24, 6500.70)]
    r = q(con, "SELECT wage_adjusted_operating FROM ipps_payment('470', DATE '2026-11-15', '360051')")
    assert r == [(12717.32,)]
    # FY2026 has no fixture -> nothing on 2026-09-30
    assert q(con, "SELECT count(*) FROM ipps_payment('470', DATE '2026-09-30', '360051')") == [(0,)]


def test_ipps_fy2025_history_headers(built):
    """FY2025 IFC: 'FY 2025 Wage Index', CMIV42, multi-line CN Table 5 header."""
    _, con = built
    r = q(con, "SELECT case_mix_index, wage_index, operating_labor_rate, operating_base_rate, "
               "capital_federal_rate FROM ref_ipps_hospital WHERE fiscal_year = 'FY2025'")
    assert r == [(1.8, 0.95, 4107.12, 6419.03, 512.14)]
    r = q(con, "SELECT relative_weight, post_acute_transfer FROM ref_ipps_drg WHERE fiscal_year = 'FY2025'")
    assert r == [(1.9, True)]
    r = q(con, "SELECT wage_adjusted_operating FROM ipps_payment('470', DATE '2025-06-15', '360051')")
    assert r == [(12196.16,)]


def test_opps_wage_adjusted_uses_hospital_wage_index(built):
    _, con = built
    r = q(con, "SELECT payment_rate_adjusted FROM opps_wage_adjusted('29881', DATE '2026-11-15', '360051')")
    # synthetic OPPS 29881 = 4000.00; 4000 x (0.60 x 0.9182 + 0.40)
    assert r == [(round(4000 * (0.6 * 0.9182 + 0.4), 2),)]


# ------------------------------------------------------------ Table 8 CCN–NPI
def test_ccn_npi_pairs_from_enrollments_additional_and_nppes(built):
    _, con = built
    r = q(con, "SELECT ccn, npi, match_source FROM ref_ccn_npi ORDER BY ccn, npi, match_source")
    assert ("360051", 1000000002, "enrollment") in r
    assert ("360051", 1000000009, "enrollment_additional") in r     # Additional NPIs file
    assert ("360001", 1000000002, "nppes_other_id") in r            # NPPES fills the gap
    assert ("050001", 1000000007, "enrollment") in r                # lost leading zero restored
    assert all(n != 1000000010 for _, n, _ in r)                    # orphan enrollment ID dropped
    assert len(r) == len(set(r))


def test_ccn_npi_ohio_match_report(built):
    root, _ = built
    rep = verify.run(str(root), rehash=False)
    c = next(c for c in rep.checks if c.name.startswith("Ohio acute-care hospital NPIs"))
    # hospital category: 1000000002 (enrollment), 1000000012 (name_zip), 1000000017 (name_city) match;
    # 1000000013 has no enrollment. VA, person and stale records are left out of the target.
    assert c.status == "FAIL" and c.detail.startswith("1 of 4")
    assert "1000000013" in rep.files["ccn_npi_ohio_unmatched.csv"]
    assert "1000000013" not in verify.to_markdown(rep)


# ------------------------------------------------------------ Table 9 specialty filter
def test_code_specialty_share_rank_and_plausible(built):
    _, con = built
    r = {s: (rank, share, p) for _, s, rank, share, _, p, _ in q(con, "SELECT * FROM specialty_plausible('27447')")}
    assert r["Orthopedic Surgery"][0] == 1 and r["Orthopedic Surgery"][2]
    assert r["Dermatology"][2] is False and r["Dermatology"][0] == 13       # < 1 % and outside the top 10
    assert r["Specialty K"][2]                                             # >= 1 %
    tax = q(con, "SELECT taxonomies FROM specialty_plausible('27447') WHERE medicare_specialty='Orthopedic Surgery'")
    assert tax == [(["207X00000X", "208600000X"],)]                        # mapped through NPPES
    # Spec §10: no CPT descriptions stored
    assert "description" not in [c for (c, *_) in q(con, "DESCRIBE ref_code_specialty")]


def test_code_specialty_spot_check_27447(built):
    root, _ = built
    rep = verify.run(str(root), rehash=False)
    c = next(c for c in rep.checks if c.name.startswith("spot check 27447"))
    assert c.status == "PASS"


def test_mpfs_reads_2024_2025_layout_without_pric_ind(tmp_path):
    """RVU24/25 files have no PRIC IND column, so CONV FACTOR sits one column
    earlier. Columns are found by header name, so the rate must not change."""
    import csv, io, zipfile
    from pipeline.common.raw import RawFile
    from pipeline.ref.mpfs import read_rvu
    src = FIX / "mpfs" / "2026D" / "rvu26d_0.zip"
    with zipfile.ZipFile(src) as zf:
        name = next(n for n in zf.namelist() if n.startswith("PPRRVU") and "nonQPP" in n)
        rows = list(csv.reader(io.StringIO(zf.read(name).decode("utf-8-sig"))))
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows([r[:23] + r[24:] if len(r) > 24 else r for r in rows])
    d = tmp_path / "old"
    d.mkdir()
    (d / "PPRRVU24_JUL.csv").write_text(out.getvalue(), encoding="utf-8")
    old = read_rvu(RawFile(tmp_path, "old").member("PPRRVU24*.csv"))
    new = read_rvu(RawFile(FIX, "mpfs/2026D/rvu26d_0.zip").member("PPRRVU*_nonQPP.csv"))
    assert old.equals(new)


def test_ccn_npi_address_and_name_matches(built):
    _, con = built
    r = {(c, n): s for c, n, s in q(con, "SELECT ccn, npi, match_source FROM ref_ccn_npi")}
    assert r.get(("360051", 1000000011)) == "address_zip"   # '1 Main Street, Suite 200' = '1 MAIN ST'
    assert r.get(("360051", 1000000012)) == "name_zip"      # 'Test Hospital, Inc.' = 'TEST HOSPITAL'
    assert not any(n == 1000000013 for _, n in r)          # no enrollment: stays unmatched
    assert not any(n == 1000000011 and c == "050001" for c, n in r)


def test_ccn_npi_report_categories_and_city_match(built):
    _, con = built
    cat = dict(q(con, "SELECT npi, npi_category FROM v_ccn_npi_ohio_report"))
    assert cat[1000000014] == "federal" and cat[1000000015] == "not_hospital"
    assert cat[1000000016] == "stale" and cat[1000000013] == "hospital"
    assert q(con, "SELECT match_source FROM ref_ccn_npi WHERE npi = 1000000017") == [("name_city",)]


def test_ccn_npi_manual_pairs_only_approved(tmp_path):
    from datetime import date
    from pipeline.ref.ccn_npi import add_manual_pairs
    base = pl.DataFrame({"ccn": ["360051"], "npi": [1000000002], "match_source": ["enrollment"],
                         "organization_name": ["TEST HOSPITAL"], "state": ["OH"]})
    f = tmp_path / "ccn_npi_manual.csv"
    f.write_text("npi,ccn,approved,note\n1000000013,360051,Y,same campus\n1000000016,360051,,not sure\n")

    class Ctx:
        warnings = []
        def warn(self, m): self.warnings.append(m)
    out = add_manual_pairs(base, f, date(2026, 7, 31), "2026-07", Ctx())
    man = out.filter(pl.col("match_source") == "manual")
    assert man["npi"].to_list() == [1000000013]
    assert man["organization_name"].to_list() == ["TEST HOSPITAL"]
    assert man["source_file"].to_list() == ["config/ccn_npi_manual.csv"]


def test_ccn_npi_suggestions_file(built):
    root, _ = built
    rep = verify.run(str(root), rehash=False)
    s = rep.files["ccn_npi_ohio_suggestions.csv"]
    assert s.startswith("approved,npi,")


# ------------------------------------------------------------ Tables 11-14 (real CMS lines + 2 Ohio rows)
def test_clfs_rate_and_no_cpt_descriptions(built):
    _, con = built
    assert q(con, "SELECT rate FROM clfs_rate('0001U', DATE '2026-11-15')") == [(720.0,)]
    assert q(con, "SELECT description FROM ref_clfs WHERE hcpcs='0001U'") == [(None,)]     # PLA code: AMA text dropped
    assert q(con, "SELECT description FROM ref_clfs WHERE hcpcs='G0306'") == [("Complete cbc w/auto diff wbc",)]


def test_dmepos_state_fees_and_rural_zip(built):
    _, con = built
    assert q(con, "SELECT count(DISTINCT state) FROM ref_dmepos") == [(53,)]   # 49 + DC + AK, HI, PR, VI
    r = q(con, "SELECT fee, zip_is_rural FROM dmepos_fee('A4221', DATE '2026-11-15', 'OH', p_zip := '45389')")
    assert r == [(29.07, True)]
    r = q(con, "SELECT fee, zip_is_rural FROM dmepos_fee('A4221', DATE '2026-11-15', 'OH', p_zip := '45409')")
    assert r == [(25.87, False)]
    # no separate rural fee (0.00 in the file) -> the non-rural fee applies
    r = q(con, "SELECT fee, fee_nonrural, fee_rural FROM dmepos_fee('A4216', DATE '2026-11-15', 'OH', p_zip := '45389')")
    assert r[0][2] is None and r[0][0] == r[0][1] == 0.54
    assert q(con, "SELECT fee_nonrural FROM dmepos_fee('A4217', DATE '2026-11-15', 'OH', p_modifier := 'AU')")


def test_ambulance_rate_by_zip_rural_indicator(built):
    _, con = built
    rate = lambda z: q(con, f"SELECT rural_indicator, rate FROM ambulance_rate('A0427', DATE '2026-11-15', '{z}')")
    assert rate("45409") == [("U", 600.0)]      # urban
    assert rate("45389") == [("R", 606.0)]      # rural
    assert rate("45780") == [("B", 742.0)]      # super rural (lowest quartile)
    assert q(con, "SELECT is_mileage FROM ref_ambulance WHERE hcpcs='A0425' LIMIT 1") == [(True,)]


def test_anesthesia_payment_base_plus_time(built):
    _, con = built
    r = q(con, "SELECT base_units, time_units, payment FROM anesthesia_payment('01402', 60, DATE '2026-11-15')")
    cf = q(con, "SELECT anesthesia_cf FROM ref_anesthesia_cf WHERE carrier='15202' AND locality='00'")[0][0]
    assert r == [(7, 4.0, round(11 * cf, 2))]


def test_ambulance_2025_csv_with_bom(built):
    """CY2025 508 file is a comma CSV with a BOM; the loader reads it like the 2026 .txt."""
    _, con = built
    r = q(con, "SELECT rate_urban FROM ref_ambulance WHERE period='CY2025' AND carrier='01112' "
               "AND locality='05' AND hcpcs='A0427'")
    assert r == [(700.0,)]
    r = q(con, "SELECT rate_urban FROM ref_ambulance WHERE period='CY2026' AND carrier='01112' "
               "AND locality='05' AND hcpcs='A0427'")
    assert r == [(709.75,)]
    # CY2024: 2024 column order, carrier without the leading 0 (Excel)
    r = q(con, "SELECT rate_urban FROM ref_ambulance WHERE period='CY2024' AND carrier='01112' "
               "AND locality='05' AND hcpcs='A0427'")
    assert r == [(690.0,)]
    assert q(con, "SELECT count(DISTINCT period) FROM ref_ambulance") == [(3,)]
    assert q(con, "SELECT count(DISTINCT period) FROM ref_zip_locality") == [(3,)]
    # a date in each year finds that year's rate for an urban zip
    # a date in each year finds that year's rate (zip that maps to a loaded locality)
    z, car, loc = q(con, "SELECT z.zip5, z.carrier, z.locality FROM ref_zip_locality z JOIN ref_ambulance a "
                         "USING (carrier, locality) WHERE z.period='2026Q4' AND a.hcpcs='A0427' "
                         "ORDER BY z.zip5 LIMIT 1")[0]
    for dos, per in (("2024-06-15", "CY2024"), ("2025-06-15", "CY2025"), ("2026-11-15", "CY2026")):
        got = q(con, f"SELECT period FROM ambulance_rate('A0427', DATE '{dos}', '{z}')")
        assert got == [(per,)], dos


def test_anesthesia_cf_columns_single_and_split():
    from pipeline.ref.anesthesia_cf import cf_columns
    # CY2024 / CY2025: one factor
    assert cf_columns(["Contractor", "Locality", "Locality Name", "Anesthesia Conversion Factor"]) == \
        ("Anesthesia Conversion Factor", None)
    # CY2026: qualifying APM participant and non-qualifying
    assert cf_columns(["Contractor", "Locality", "Locality Name", "Qualifying APM Participant CF",
                       "Non-Qualifying APM Participant CF"]) == \
        ("Non-Qualifying APM Participant CF", "Qualifying APM Participant CF")


def test_ccn_npi_reclass_file_rules(tmp_path, monkeypatch):
    """config/ccn_npi_reclass.csv: category must be known and a reason is required."""
    import pytest
    from pipeline import duckdb_build
    monkeypatch.setenv("MESHKOR_CONFIG_DIR", str(tmp_path))
    assert duckdb_build._reclass_rows() == []
    (tmp_path / "ccn_npi_reclass.csv").write_text("npi,category,reason,source\n1,closed,closed in 2019,news\n")
    assert duckdb_build._reclass_rows() == [("1", "closed", "closed in 2019", "news")]
    (tmp_path / "ccn_npi_reclass.csv").write_text("npi,category,reason,source\n1,gone,x,y\n")
    with pytest.raises(ValueError):
        duckdb_build._reclass_rows()
    (tmp_path / "ccn_npi_reclass.csv").write_text("npi,category,reason,source\n1,closed,,y\n")
    with pytest.raises(ValueError):
        duckdb_build._reclass_rows()


def test_guess_delimiter_tab_txt_and_csv():
    """ASC Jan/Jul 2024 come as tab-separated .txt; the rest are .csv."""
    from pipeline.common.tabular import guess_delimiter

    class M:
        def __init__(self, name, data):
            self.name, self._d = name, data

        def read_bytes(self):
            return self._d

    assert guess_delimiter(M("January 2024 ASC AA.txt", b"HCPCS Code\tShort Descriptor\n0001\tX, Y\n")) == "\t"
    assert guess_delimiter(M("ASC-AA.csv", b"HCPCS Code\tA\n")) == ","
    assert guess_delimiter(M("comma.txt", b"HCPCS Code,Short Descriptor,Rate\n")) == ","


def test_member_rows_bare_cr_line_ends():
    """Some CMS CSVs end lines with a bare carriage return."""
    from pipeline.common.tabular import member_rows

    class M:
        name = "x.csv"

        def read_bytes(self):
            return b"HCPCS,RATE\r99214,1.00\r99213,2.00\r"

    assert member_rows(M()) == [["HCPCS", "RATE"], ["99214", "1.00"], ["99213", "2.00"]]


def test_members_match_file_name_in_windows_subfolder(tmp_path):
    """On Windows a file in a subfolder is listed as 'sub\\\\file.csv'; match on the file name."""
    from pipeline.common.raw import RawFile
    d = tmp_path / "MUE2024B" / "hospital" / "Facility-04-01-2024"
    d.mkdir(parents=True)
    (d / "MCR_MUE_OutpatientHospitalServices_Eff_04-01-2024.csv").write_text("x")
    rf = RawFile(tmp_path, "MUE2024B/hospital")
    assert len(rf.members("MCR_MUE_*.csv")) == 1


def test_clfs_accepts_rate_year_column(tmp_path):
    """CLFS CY2024 Q1-Q3 name the rate column RATE2024."""
    from pipeline.ref import clfs

    class M:
        name = "CLFS 2024 Q1V1.csv"
        lineage_name = name

        def read_bytes(self):
            return (b"title line\nYEAR,HCPCS,MOD,EFF_DATE,INDICATOR,RATE2024,SHORTDESC\n"
                    b"2024,0001U,,20240101,N,720.00,Rbc dna hea 35 ag\n")

    class Raw:
        rel_path = "CLFS/2024Q1"

        def member(self, pattern):
            return M()

    class Ctx:
        def raw(self, f):
            return Raw()

        def warn(self, msg):
            pass

    import pipeline.ref.clfs as mod
    orig = mod.add_lineage
    mod.add_lineage = lambda df, m, **k: df
    try:
        out = clfs.load_release({"file": "x", "members": {"clfs": "*"}, "period": "2024Q1",
                                 "effective_start": "2024-01-01", "effective_end": "2024-03-31"}, Ctx())
    finally:
        mod.add_lineage = orig
    assert out.df.select("hcpcs", "rate").rows() == [("0001U", 720.0)]


# ------------------------------------------------------------ Spec §11 (tables 17, 19, 20, 21)
def test_s11_geo_hud_and_census(built):
    _, con = built
    assert q(con, "SELECT geoid, round(res_ratio, 3) FROM zip_geo('00601', DATE '2026-05-01') "
                  "WHERE geo_type = 'county'") == [("72001", 0.997), ("72081", 0.003)]
    assert q(con, "SELECT geoid FROM zip_geo('45402', DATE '2026-05-01') WHERE geo_type = 'cbsa'") == [("19430",)]
    assert q(con, "SELECT count(*) FROM zip_geo('45402', DATE '2025-05-01')") == [(0,)]   # other quarter
    # Census: empty ZCTA rows (county parts outside any ZCTA) are left out; 45449 is split over 2 counties
    assert q(con, "SELECT county_fips, round(land_share, 2) FROM ref_geo_zcta_county WHERE zcta5 = '45449' "
                  "ORDER BY 1") == [("39057", 0.2), ("39113", 0.8)]
    assert q(con, "SELECT count(*) FROM ref_geo_zcta_county WHERE zcta5 IS NULL OR zcta5 = ''") == [(0,)]


def test_s11_quality(built):
    _, con = built
    assert q(con, "SELECT ccn, overall_star_rating, emergency_services FROM ref_quality_hospital ORDER BY 1") == \
        [("010005", None, True), ("360051", 4, True)]
    r = dict(q(con, "SELECT measure_group, count(*) FROM ref_quality_measure WHERE ccn = '360051' GROUP BY 1"))
    assert r == {"complications": 1, "unplanned": 1, "infections": 1, "timely": 1}   # REH file not read
    assert q(con, "SELECT score_value, denominator FROM ref_quality_measure WHERE measure_id = 'OP_18b'") == [(182.0, 1204.0)]
    assert q(con, "SELECT measure_id, score_value, performance_category FROM ref_quality_asc ORDER BY 1") == \
        [("ASC-1", None, None), ("ASC-12", 11.9, "No Different Than the National Rate"), ("ASC-2", 0.033, None)]


def test_s11_ownership(built):
    _, con = built
    rows = q(con, "SELECT dataset, owner_name, owner_type, percentage_ownership, llc_owner FROM ref_ownership ORDER BY 1")
    assert rows == [("all_owners", "LIFEPOINT HOLDINGS 2 LLC", "O", 80.0, True),
                    ("chow_owners", "KEVIN HAMMONS", "I", None, None)]
    assert q(con, "SELECT ccn_buyer, ccn_seller, chow_effective_date::VARCHAR FROM ref_chow") == \
        [("150056", "150161", "2025-12-28")]
    assert q(con, "SELECT count(*) FROM ref_chow_npi") == [(2,)]      # SNF file not read


def test_s11_drug_prices(built):
    _, con = built
    # weekly repeats collapse to 1 row per price; the 2025 price ends the day before the 2026 price
    assert q(con, "SELECT nadac_per_unit, effective_start::VARCHAR, effective_end::VARCHAR FROM ref_nadac "
                  "WHERE ndc = '00002015201' ORDER BY 2") == \
        [(2.0, "2025-01-15", "2026-03-03"), (2.5, "2026-03-04", "9999-12-31")]
    assert q(con, "SELECT ndc11 FROM ref_ndc_package") == [("00002015201",)]
    assert q(con, "SELECT nadac_per_unit, proprietary_name FROM drug_price('00002015201', DATE '2025-06-01')") == \
        [(2.0, "Zepbound")]


def test_ownership_snake_case_names():
    from pipeline.ref.ownership import snake
    assert snake("PERCENTAGE OWNERSHIP") == "percentage_ownership"
    assert snake("CCN - SELLER") == "ccn_seller"


# ------------------------------------------------------------ Table 10, ASP
def test_asp_payment_limits(built):
    _, con = built
    # trimmed real CMS 508 CSVs (Windows-1252, 8-12 note lines above the header)
    assert q(con, "SELECT payment_limit, dosage, period FROM asp_price('J9271', DATE '2026-11-15')") == \
        [(62.253, "1 MG", "2026Q4")]
    assert q(con, "SELECT payment_limit FROM asp_price('j9271', DATE '2025-11-15')") == [(60.291,)]
    assert q(con, "SELECT count(*) FROM asp_price('J9271', DATE '2025-06-15')") == [(0,)]   # quarter not loaded
    # NOC drugs: no HCPCS code, money with $ stripped; no NOC file in 2026
    assert q(con, "SELECT description, payment_limit, period FROM ref_asp WHERE price_type = 'NOC'") == \
        [("Vasopressin (Long Grove)", 2.462, "2025Q4")]
    assert q(con, "SELECT ndc11, bill_units_pkg FROM ref_ndc_hcpcs WHERE crosswalk_type = 'NOC' ORDER BY 1") == \
        [("81298855203", 200.0), ("81298855403", 400.0)]
    assert q(con, "SELECT count(*) FROM ref_asp WHERE hcpcs IS NULL AND price_type = 'ASP'") == [(0,)]


def test_asp_crosswalk(built):
    _, con = built
    # NDC2 (2025) and NDC (2026) headers, _2025_CODE / _2026_CODE code columns
    assert q(con, "SELECT DISTINCT period FROM ref_ndc_hcpcs WHERE hcpcs = 'J9271' AND crosswalk_type = 'ASP' "
                  "ORDER BY 1") == [("2025Q4",), ("2026Q4",)]
    assert q(con, "SELECT hcpcs, bill_units_pkg, payment_per_package FROM ndc_asp('00006302602', DATE '2026-11-15')") == \
        [("J9271", 100.0, 6225.3)]
    assert q(con, "SELECT ndc11 FROM ref_ndc_hcpcs WHERE ndc = '00006-3026-02' LIMIT 1") == [("00006302602",)]


def test_asp_rules():
    from pipeline.ref._asp_common import norm, quarter_dates
    from datetime import date
    assert norm("_2026_CODE") == "HCPCSCODE" and norm("NDC or ALTERNATE ID") == "NDCORALTERNATEID"
    assert quarter_dates("2024Q1") == (date(2024, 1, 1), date(2024, 3, 31))
    assert quarter_dates("2026Q4") == (date(2026, 10, 1), date(2026, 12, 31))


def test_asp_wrong_folder_is_refused(tmp_path):
    """A file put in the wrong quarter folder stops the load."""
    import shutil as sh
    from pipeline.ref import asp
    from pipeline.common.raw import RawFile
    d = tmp_path / "ASP" / "2026Q3"
    d.mkdir(parents=True)
    for f in (FIX / "asp" / "2026Q4").glob("*Payment Limit*"):
        sh.copy(f, d / f.name)
    class Ctx:
        def raw(self, p):
            return RawFile(tmp_path, p)
    with pytest.raises(ValueError, match="file says 2026Q4, folder says 2026Q3"):
        asp.load_release({"period": "2026Q3", "file": "ASP/2026Q3",
                          "members": {"pricing": "*508*Payment Limit File*.csv"}}, Ctx())


def test_hcpcs_code_file(built):
    _, con = built
    # the Transaction Report in the same folder is skipped
    assert q(con, "SELECT short_description, dose_from_description, period FROM hcpcs_info('J9271', DATE '2026-11-15')") == \
        [("Inj pembrolizumab", "1 mg", "2026Q4")]
    assert q(con, "SELECT dose_from_description FROM hcpcs_info('J0725', DATE '2026-11-15')") == [("per 1,000 usp units",)]
    assert q(con, "SELECT count(*) FROM ref_hcpcs_code WHERE record_type = 'modifier' AND hcpcs = 'A1'") == [(1,)]
    assert q(con, "SELECT added_date::VARCHAR FROM ref_hcpcs_code WHERE hcpcs = 'A0021'") == [("1985-01-01",)]
