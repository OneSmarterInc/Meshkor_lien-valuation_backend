"""Step 2 tests: hospital price files. Run from the repo root:  python -m pytest -q tests/test_hpt.py

Fixtures (tests/fixtures/raw/MRF/2026-10/): a trimmed real OSU tall CSV with one cp1252 line,
a synthetic wide CSV (v3.0.0) and a synthetic JSON (v3.0.0). No network.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import duckdb
import polars as pl
import pytest
import yaml

from pipeline import runner
from pipeline.common.lineage import LINEAGE_COLS
from pipeline.hpt import discover, hospitals
from pipeline.ref.hospital_mrf import layout_of, payer_group, read_prefix

FIX = Path(__file__).parent / "fixtures" / "raw"
SOURCES = {
    "ref_hospital_mrf": {"loader": "hospital_mrf", "releases": [
        {"period": "2026-10", "ccn": "360085", "effective_start": "2026-07-01", "effective_end": "9999-12-31",
         "page": "https://wexnermedical.osu.edu/x", "file": "MRF/2026-10/360085", "members": {"mrf": "*standardcharges*.csv"}},
        {"period": "2026-10", "ccn": "360242", "effective_start": "2026-02-01", "effective_end": "9999-12-31",
         "page": "https://example.org/json", "file": "MRF/2026-10/360242", "members": {"mrf": "*standardcharges*.json"}},
        {"period": "2026-10", "ccn": "369999", "effective_start": "2026-01-15", "effective_end": "9999-12-31",
         "page": "https://example.org/wide", "file": "MRF/2026-10/369999", "members": {"mrf": "*standardcharges*.csv"}},
    ]}}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    shutil.copytree(FIX / "MRF", root / "raw" / "MRF")
    cfg = tmp_path_factory.mktemp("cfg")
    for p in (Path("config")).glob("*"):
        if p.is_file():
            shutil.copy(p, cfg / p.name)
    (cfg / "sources.yaml").write_text(yaml.safe_dump(SOURCES))
    old = {k: os.environ.get(k) for k in ("MESHKOR_CONFIG_DIR", "MESHKOR_SOURCES", "MESHKOR_RAW_DIR")}
    os.environ["MESHKOR_CONFIG_DIR"] = str(cfg)
    os.environ.pop("MESHKOR_SOURCES", None); os.environ.pop("MESHKOR_RAW_DIR", None)
    try:
        res = runner.run_table("ref_hospital_mrf", data_root=str(root))
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    con = duckdb.connect()
    con.execute(f"CREATE VIEW t AS SELECT * FROM read_parquet('{(root / 'ref' / 'ref_hospital_mrf').as_posix()}/**/*.parquet', union_by_name=true)")
    yield root, con, res
    con.close()


def q(con, sql):
    return con.execute(sql).fetchall()


def test_three_layouts_load_into_one_table(built):
    root, con, res = built
    rows = dict((c, n) for c, _, n in q(con, "SELECT ccn, source_layout, count(*) FROM t GROUP BY 1,2"))
    assert rows == {"360085": 391, "360242": 9, "369999": 15}
    assert set(r[0] for r in q(con, "SELECT DISTINCT source_layout FROM t")) == {"tall", "json", "wide"}
    assert res.rows == 415


def test_lineage_and_hospital_block(built):
    _, con, _ = built
    cols = {r[0] for r in q(con, "DESCRIBE t")}
    assert set(LINEAGE_COLS + ["period", "ccn", "hospital_name", "mrf_version", "last_updated_on", "attestation"]) <= cols
    assert q(con, "SELECT count(*) FROM t WHERE source_sha256 IS NULL OR effective_start IS NULL OR ccn IS NULL") == [(0,)]
    assert q(con, "SELECT DISTINCT ccn, typeof(ccn) FROM t ORDER BY 1") == [("360085", "VARCHAR"), ("360242", "VARCHAR"), ("369999", "VARCHAR")]
    assert q(con, "SELECT last_updated_on FROM t WHERE ccn='360085' LIMIT 1") == [(__import__("datetime").date(2026, 7, 1),)]


def test_wide_unpivots_one_row_per_payer_and_keeps_percentiles(built):
    _, con, _ = built
    r = q(con, "SELECT payer_name, negotiated_dollar, negotiated_percentage, estimated_amount, median_amount, pct_10, pct_90, rate_count "
               "FROM t WHERE ccn='369999' AND hcpcs='73721' ORDER BY payer_name")
    assert r == [("Anthem", 750.0, None, None, None, None, None, None),
                 ("Medicare", None, None, 450.0, None, None, None, None),
                 ("UnitedHealthcare", None, 45.0, 675.0, 660.0, 600.0, 750.0, 12)]
    # the MS-DRG line has no HCPCS; revenue-code-only line keeps rc
    assert q(con, "SELECT ms_drg, hcpcs FROM t WHERE ccn='369999' AND ms_drg='470' LIMIT 1") == [("470", None)]
    assert q(con, "SELECT count(*) FROM t WHERE ccn='369999' AND rc='120' AND hcpcs IS NULL AND ms_drg IS NULL") == [(3,)]


def test_json_rows_match_payers_and_codes(built):
    _, con, _ = built
    r = q(con, "SELECT payer_name, setting, negotiated_dollar, negotiated_algorithm, estimated_amount, pct_10, rate_count "
               "FROM t WHERE ccn='360242' AND hcpcs='99213' ORDER BY payer_name")
    assert r == [("Anthem", "Outpatient", 119.0, None, None, None, None),
                 ("Cigna", "Outpatient", None, None, 107.1, 95.2, 12),
                 ("Medicare", "Outpatient", None, "CMS fee schedule", 71.4, None, None)]
    assert q(con, "SELECT ndc, drug_unit, drug_type FROM t WHERE ccn='360242' AND hcpcs='J9299' LIMIT 1") == [("00003377212", "1", "ME")]
    assert q(con, "SELECT DISTINCT attestation FROM t WHERE ccn='360242'") == [("True",)]


def test_tall_real_rows_and_cp1252_fallback(built):
    _, con, res = built
    assert any("not UTF-8" in w for w in res.warnings)
    assert q(con, "SELECT count(*) FROM t WHERE ccn='360085' AND description LIKE 'HC TEST ITEM%'") == [(1,)]
    assert q(con, "SELECT count(*) FROM t WHERE ccn='360085' AND ms_drg IS NOT NULL")[0][0] >= 40
    assert q(con, "SELECT count(*) FROM t WHERE ccn='360085' AND ndc IS NOT NULL")[0][0] >= 40
    assert q(con, "SELECT count(*) FROM t WHERE ccn='360085' AND apr_drg IS NOT NULL")[0][0] >= 10
    # every row has a code and a mapped type; no negative prices
    assert q(con, "SELECT count(*) FROM t WHERE code_1 IS NULL AND code_2 IS NULL AND code_3 IS NULL") == [(0,)]
    assert q(con, "SELECT count(*) FROM t WHERE hcpcs IS NULL AND ms_drg IS NULL AND apr_drg IS NULL AND rc IS NULL AND ndc IS NULL AND cdm IS NULL") == [(0,)]
    assert q(con, "SELECT count(*) FROM t WHERE negotiated_dollar < 0 OR gross_charge < 0") == [(0,)]


def test_payer_group_rules():
    assert payer_group("Anthem", "Anthem - Traditional") == "Anthem"
    assert payer_group("Aetna", "Aetna - Medicare") == "Medicare Advantage"
    assert payer_group("Medicare", "Medicare FFS") == "Medicare"
    assert payer_group("Molina", "Molina - Medicaid") == "Medicaid"
    assert payer_group("Multiplan", "Multiplan") == "PPO network / TPA"
    assert payer_group("Some Unknown Co", None) == "Other"


def test_read_prefix_and_layout(tmp_path):
    p = FIX / "MRF" / "2026-10" / "369999" / "99-9999999_TEST-WIDE-HOSPITAL_standardcharges.csv"
    meta, header, skip = read_prefix(p)
    assert meta["hospital_name"] == "Test Wide Hospital" and skip == 2 and layout_of(header) == "wide"
    p = FIX / "MRF" / "2026-10" / "360085" / "31-1340739_OHIO-STATE-UNIVERSITY-HOSPITALS_standardcharges.csv"
    meta, header, skip = read_prefix(p)
    assert meta["version"] == "3.0.0" and layout_of(header) == "tall"


def test_cms_hpt_txt_parser_and_name_match():
    text = ("location-name: Ohio State University Hospitals\nsource-page-url: https://wexnermedical.osu.edu/pricing\n"
            "mrf-url: https://wexnermedical.osu.edu/Files/31-1340739_OHIO-STATE-UNIVERSITY-HOSPITALS_standardcharges.csv.zip\n"
            "contact-name: Beth Carlson\ncontact-email: pricing@osumc.edu\n\n"
            "location-name: James Cancer Hospital\nmrf-url: https://wexnermedical.osu.edu/files/31-1322863_JAMES-CANCER-HOSPITAL_standardcharges.csv.zip\n")
    blocks = discover.parse_hpt_txt(text)
    assert [b["location_name"] for b in blocks] == ["Ohio State University Hospitals", "James Cancer Hospital"]
    assert blocks[0]["contact_email"] == "pricing@osumc.edu"
    hosp = pl.DataFrame({"ccn": ["360085", "360242"], "hospital_name": ["OHIO STATE UNIVERSITY HOSPITALS", "ARTHUR G JAMES CANCER HOSPITAL AND RESEARCH INSTITUTE"],
                         "dba_name": [None, "THE JAMES"]})
    assert discover.best_ccn("Ohio State University Hospitals", hosp)[0] == "360085"
    assert discover.best_ccn("James Cancer Hospital", hosp)[0] == "360242"
    assert discover.guess_format(blocks[0]["mrf_url"]) == "zip"


def test_hospital_list_from_synthetic_registry(tmp_path, monkeypatch):
    root = tmp_path / "data"; (root / "ref").mkdir(parents=True)
    prov = pl.DataFrame({"npi": [1447359997, 1831389550, 1000000001, 1000000002],
                         "entity_type": [2, 2, 2, 2], "practice_state": ["OH", "OH", "OH", "KY"],
                         "provider_name": ["OSU HOSPITALS", "OSU EAST", "VA MEDICAL CENTER", "KENTUCKY HOSP"],
                         "organization_name": ["OSU HOSPITALS", "OSU EAST", "VA MEDICAL CENTER", "KENTUCKY HOSP"],
                         "practice_city": ["COLUMBUS"] * 3 + ["LEXINGTON"], "zip5": ["43210"] * 4,
                         "primary_taxonomy": ["282N00000X"] * 4, "all_taxonomies": [["282N00000X"]] * 4,
                         "is_deactivated": [False] * 4})
    prov.write_parquet(root / "ref" / "ref_provider.parquet")
    ccn = pl.DataFrame({"ccn": ["360085", "360085", "360999", "180001"], "npi": [1447359997, 1831389550, 1000000001, 1000000002],
                        "organization_name": ["OHIO STATE UNIVERSITY HOSPITALS", "OHIO STATE UNIVERSITY HOSPITALS", "VA MEDICAL CENTER", "KENTUCKY HOSP"],
                        "dba_name": [None, "OSU EAST", None, None], "city": ["COLUMBUS", "COLUMBUS", "COLUMBUS", "LEXINGTON"],
                        "match_source": ["enrollment", "enrollment_additional", "enrollment", "enrollment"],
                        "subgroup_acute_care": [True, True, True, True]})
    ccn.write_parquet(root / "ref" / "ref_ccn_npi.parquet")
    cfg = tmp_path / "config"; cfg.mkdir()
    for p in Path("config").glob("*"):
        if p.is_file():
            shutil.copy(p, cfg / p.name)
    (cfg / "ccn_npi_reclass.csv").write_text("npi,category,reason,source\n1000000001,federal,VA hospital,test\n")
    monkeypatch.setattr(hospitals.config, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("MESHKOR_CONFIG_DIR", str(cfg))
    out = hospitals.build(str(root))
    df = pl.read_parquet(out)
    assert df["ccn"].to_list() == ["360085"]               # KY out (prefix), VA out (reclass)
    assert df["npi"][0] == 1447359997 and df["npi_count"][0] == 2
    assert df["website"][0] == "https://wexnermedical.osu.edu"  # from hospital_sites.csv
