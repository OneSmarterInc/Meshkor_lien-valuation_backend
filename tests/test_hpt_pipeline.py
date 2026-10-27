"""Failure handling of the hospital-price pipeline: ledger, validation, quarantine, yaml edits.
No network: everything runs on tests/fixtures and temp folders."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

FIX = Path(__file__).parent / "fixtures" / "raw" / "MRF" / "2026-10"


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A data root + raw dir + config dir under tmp, with the three fixture hospitals."""
    data = tmp_path / "data"; raw = tmp_path / "raw"; cfg = tmp_path / "config"
    (data / "ref").mkdir(parents=True); (data / "reports").mkdir(); cfg.mkdir()
    shutil.copytree(FIX.parent, raw / "MRF")
    src_cfg = Path(__file__).parents[1] / "config"
    for f in ("hospital_sites.csv", "hpt_tiers.csv", "payer_groups.yaml", "hospital_taxonomies.yaml", "geography.yaml", "ccn_npi_reclass.csv"):
        if (src_cfg / f).exists():
            shutil.copy(src_cfg / f, cfg / f)
    (cfg / "sources_local.yaml").write_text(
        'ref_hospital_mrf:\n  loader: hospital_mrf\n  releases:\n'
        '  - period: "2026-10"\n    ccn: "360085"\n    effective_start: 2026-07-01\n    effective_end: 9999-12-31\n'
        '    file: MRF/2026-10/360085\n    members:\n      mrf: "*standardcharges*.csv"\n'
        '  - period: "2026-10"\n    ccn: "360242"\n    effective_start: 2026-02-01\n    effective_end: 9999-12-31\n'
        '    file: MRF/2026-10/360242\n    members:\n      mrf: "*standardcharges*.json"\n', encoding="utf-8")
    monkeypatch.setenv("MESHKOR_DATA_ROOT", str(data)); monkeypatch.setenv("MESHKOR_RAW_DIR", str(raw))
    monkeypatch.setenv("MESHKOR_CONFIG_DIR", str(cfg)); monkeypatch.setenv("MESHKOR_SOURCES", "sources_local.yaml")
    from pipeline.common import config
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    return tmp_path


def test_validate_accepts_fixtures_and_rejects_junk(tmp_path):
    from pipeline.hpt.validate import validate
    work = tmp_path / "work"
    for f in FIX.rglob("*standardcharges*"):
        ok, code, detail, info = validate(f, work)
        assert ok, (f.name, code, detail)
        assert info["layout"] in ("tall", "wide", "json")
    html = tmp_path / "login.csv"; html.write_text("<html><body>Sign in</body></html>")
    assert validate(html, work)[1] == "HTML"
    junk = tmp_path / "junk.csv"; junk.write_text("a,b,c\n" + "1,2,3\n" * 400)
    assert validate(junk, work)[1] == "INVALID"


def test_ledger_retry_then_park(tmp_path, monkeypatch):
    monkeypatch.setenv("MESHKOR_DATA_ROOT", str(tmp_path))
    from pipeline.hpt.ledger import Ledger
    led = Ledger()
    led.get("360051", "2026-11")["hospital_name"] = "Miami Valley"
    for _ in range(3):
        r = led.fail("360051", "2026-11", "TIMEOUT", "read timed out")
        assert r["state"] != "parked"
    r = led.fail("360051", "2026-11", "TIMEOUT", "read timed out")
    assert r["state"] == "parked" and r["attempts"] == "4"
    assert led.fail("360180", "2026-11", "AUTH", "login")["state"] == "parked"      # parks at once
    assert led.skip("360051", "2026-11") == "parked (TIMEOUT)"
    assert led.skip("360051", "2026-11", retry_parked=True) is None
    led.set_state("360999", "2026-11", "verified", rows=5)
    assert led.skip("360999", "2026-11") == "verified"
    csv_p, xlsx_p = led.save()
    assert csv_p.exists() and xlsx_p is not None and xlsx_p.exists()
    led2 = Ledger()
    assert led2.rows[("360051", "2026-11")]["code"] == "TIMEOUT" and led2.rows[("360051", "2026-11")]["hospital_name"] == "Miami Valley"


def test_classify_codes():
    from pipeline.hpt.download import classify
    assert classify(401) == "AUTH" and classify(404) == "NOT_FOUND" and classify(429) == "BLOCKED"
    assert classify(0, "Read timed out") == "TIMEOUT" and classify(0, "connection refused") == "CONN"


def test_yaml_add_and_remove(tree):
    from pipeline.hpt.intake import remove_release, write_yaml, yaml_block
    y = tree / "config" / "sources_local.yaml"
    assert write_yaml(yaml_block("2026-11", "360051", "p", "f.json"), "2026-11", "360051", y).startswith("added")
    assert "not added twice" in write_yaml(yaml_block("2026-11", "360051", "p", "f.json"), "2026-11", "360051", y)
    assert remove_release("2026-11", "360051", y) is True
    assert "360051" not in y.read_text() and "360085" in y.read_text() and "360242" in y.read_text()


def test_load_is_incremental_and_quarantines_bad_file(tree, monkeypatch):
    from pipeline import runner
    from pipeline.ref import hospital_mrf as H
    # full load of the two configured releases -> two folders + two manifests
    res = runner.run_table("ref_hospital_mrf")
    assert res.rows == 391 + 9
    ref = tree / "data" / "ref" / "ref_hospital_mrf"
    assert sorted(p.name for p in ref.iterdir()) == ["360085_2026-10", "360242_2026-10"]
    man = tree / "data" / "ref" / "_manifest" / "ref_hospital_mrf"
    assert json.loads((man / "360085_2026-10.json").read_text())["rows"] == 391
    # make the JSON release fail to parse: it is quarantined, the other one still loads, table rows stay whole
    real = H._load_release
    def boom(rel, ctx, raw, m):
        if str(rel["ccn"]) == "360242":
            raise ValueError("simulated parse failure")
        return real(rel, ctx, raw, m)
    monkeypatch.setattr(H, "_load_release", boom)
    res = runner.run_table("ref_hospital_mrf")
    assert res.skipped and "quarantined 360242" in res.skipped[0]
    q = json.loads((man / "360242_2026-10.quarantine.json").read_text())
    assert q["stage"] == "load" and "simulated" in q["error"]
    assert res.rows == 391 + 9            # the earlier good Parquet of 360242 is kept (incremental)
    monkeypatch.setattr(H, "_load_release", real)
    res = runner.run_table("ref_hospital_mrf", periods=["2026-10"])
    assert not (man / "360242_2026-10.quarantine.json").exists()   # a good load clears the quarantine record


def test_verify_quarantines_a_failing_release(tree):
    from pipeline import runner
    from pipeline.hpt import verify
    runner.run_table("ref_hospital_mrf")
    res = verify.run(data_root=None, do_quarantine=True)
    assert all(r["fail"] == 0 for r in res.values()), res
    # corrupt one manifest's row count -> that release fails and is quarantined, the other stays
    man = tree / "data" / "ref" / "_manifest" / "ref_hospital_mrf" / "360242_2026-10.json"
    m = json.loads(man.read_text()); m["rows"] = 999; man.write_text(json.dumps(m))
    res = verify.run(data_root=None, do_quarantine=True)
    assert res["360242_2026-10"]["quarantined"] and res["360085_2026-10"]["fail"] == 0
    assert not (tree / "data" / "ref" / "ref_hospital_mrf" / "360242_2026-10").exists()
    assert (tree / "data" / "ref" / "_manifest" / "ref_hospital_mrf" / "360242_2026-10.quarantine.json").exists()
    assert list((tree / "data" / "ref" / "_quarantine" / "ref_hospital_mrf").iterdir())


def test_matcher_on_real_index_names():
    """Names copied from Cleveland Clinic's and Premier Health's cms-hpt.txt (Oct 2026)."""
    import polars as pl
    from pipeline.hpt.discover import best_ccn, common_tokens
    hosp = pl.DataFrame({
        "ccn": ["360364", "363038", "360180", "360077", "360027", "360070", "360010", "360144", "360051", "360076", "360174"],
        "hospital_name": ["CLEVELAND CLINIC AVON HOSPITAL", "CLEVELAND CLINIC REHABILITATION HOSPITALS, LLC", "THE CLEVELAND CLINIC FOUNDATION",
                          "FAIRVIEW HOSPITAL", "AKRON GENERAL MEDICAL CENTER", "CLEVELAND CLINIC MERCY HOSPITAL", "THE UNION HOSPITAL ASSOCIATION",
                          "CLEVELAND CLINIC HEALTH SYSTEM - EAST REGION", "MIAMI VALLEY HOSPITAL", "ATRIUM MEDICAL CENTER", "UPPER VALLEY MEDICAL CENTER"],
        "dba_name": [None, None, "CLEVELAND CLINIC", None, None, None, None, "EUCLID HOSPITAL", None, None, None],
        "city": ["AVON", "AVON", "CLEVELAND", "CLEVELAND", "AKRON", "CANTON", "DOVER", "EUCLID", "DAYTON", "MIDDLETOWN", "TROY"]})
    cc = [{"location_name": n} for n in ["cleveland clinic main campus", "akron general", "avon hospital", "cleveland clinic florida weston hospital",
                                          "euclid hospital", "fairview hospital", "mercy hospital", "union hospital",
                                          "Cleveland Clinic Rehabilitation Hospital, Avon", "Cleveland Clinic Rehabilitation Hospital, Beachwood"]]
    c = common_tokens(cc)
    got = {b["location_name"]: best_ccn(b["location_name"], hosp, c)[0] for b in cc}
    assert got["avon hospital"] == "360364" and got["Cleveland Clinic Rehabilitation Hospital, Avon"] == "363038"
    assert got["cleveland clinic florida weston hospital"] is None and got["Cleveland Clinic Rehabilitation Hospital, Beachwood"] is None
    assert got["euclid hospital"] == "360144" and got["mercy hospital"] == "360070" and got["union hospital"] == "360010"
    pr = [{"location_name": n} for n in ["Miami Valley Hospital", "Miami Valley Hospital North", "Miami Valley Hospital South", "Austin Blvd Emergency Department",
                                          "Jamestown Emergency Department", "Beavercreek Emergency Department", "Northwest Urgent Care", "Miami Valley Hospital Psychiatry",
                                          "Atrium Medical Center", "Atrium Medical Center Rehabilitation Unit", "Upper Valley Medical Center", "Upper Valley Medical Center Rehabilitation"]]
    c = common_tokens(pr)
    got = {b["location_name"]: best_ccn(b["location_name"], hosp, c)[0] for b in pr}
    assert got["Miami Valley Hospital"] == "360051" and got["Atrium Medical Center"] == "360076" and got["Upper Valley Medical Center"] == "360174"
    assert got["Miami Valley Hospital North"] is None and got["Austin Blvd Emergency Department"] is None


def test_bare_drg_with_severity_is_apr_drg_otherwise_code_other():
    """Mercy writes the code type as a bare DRG; a severity word at the end of the description means APR-DRG."""
    import duckdb
    from pipeline.ref.hospital_mrf import _derived
    con = duckdb.connect()
    con.execute("""CREATE TABLE _t (description VARCHAR, code_1 VARCHAR, code_1_type VARCHAR, code_2 VARCHAR, code_2_type VARCHAR,
                   code_3 VARCHAR, code_3_type VARCHAR, code_4 VARCHAR, code_4_type VARCHAR)""")
    con.executemany("INSERT INTO _t VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL)", [
        ("ANTEPARTUM WITH O.R. PROCEDURE,MODERATE", "547", "DRG"),
        ("HEART FAILURE AND SHOCK", "291", "DRG"),
        ("OFFICE VISIT", "99213", "CPT"),
        ("REHAB TRIS", "123", "TRIS-DRG"),
        ("SEVERE CASE, EXTREME ", "720", "drg"),
    ])
    cols = ", ".join(_derived(n) for n in ("hcpcs", "ms_drg", "apr_drg", "code_other"))
    rows = con.execute(f"SELECT description, {cols} FROM _t").fetchall()
    got = {r[0]: r[1:] for r in rows}        # (hcpcs, ms_drg, apr_drg, code_other)
    assert got["ANTEPARTUM WITH O.R. PROCEDURE,MODERATE"] == (None, None, "547", None)
    assert got["HEART FAILURE AND SHOCK"] == (None, None, None, "291")
    assert got["OFFICE VISIT"] == ("99213", None, None, None)
    assert got["REHAB TRIS"] == (None, None, None, "123")
    assert got["SEVERE CASE, EXTREME "] == (None, None, "720", None)


def test_only_ccn_filter_loads_just_that_hospital(tree, monkeypatch):
    """load_ref --ccn: only the named hospitals are read; the others keep their Parquet."""
    from pipeline import runner
    runner.run_table("ref_hospital_mrf")                       # both hospitals loaded
    ref = tree / "data" / "ref" / "ref_hospital_mrf"
    stamp = (ref / "360242_2026-10" / "part-000.parquet").stat().st_mtime_ns
    monkeypatch.setenv("MESHKOR_ONLY_CCN", "360085")
    res = runner.run_table("ref_hospital_mrf", periods=["2026-10"])
    assert sorted(p.name for p in ref.iterdir()) == ["360085_2026-10", "360242_2026-10"]
    assert (ref / "360242_2026-10" / "part-000.parquet").stat().st_mtime_ns == stamp    # not re-read
    assert res.rows == 391 + 9                                  # whole-table count still right


FIX_CSV = FIX / "360085" / "31-1340739_OHIO-STATE-UNIVERSITY-HOSPITALS_standardcharges.csv"
FIX_JSON = FIX / "360242" / "31-1322863_TEST-JSON-HOSPITAL_standardcharges.json"


def test_header_with_spaces_around_pipes_is_read(tree, tmp_path):
    """Blanchard Valley and Western Reserve write "code | 1" and "standard_charge | gross"."""
    from pipeline import runner
    from pipeline.hpt.validate import validate
    lines = FIX_CSV.read_bytes().split(b"\n")
    lines[2] = lines[2].replace(b"|", b" | ")
    f = tmp_path / "99-1_SPACED_standardcharges.csv"
    f.write_bytes(b"\n".join(lines))
    ok, code, detail, info = validate(f, tmp_path / "w")
    assert ok, (code, detail)
    # and the full load gives the same rows as the normal file
    shutil.copy(f, tree / "raw" / "MRF" / "2026-10" / "360085" / FIX_CSV.name)
    res = runner.run_table("ref_hospital_mrf")
    assert res.rows == 391 + 9


def test_mixed_encoding_file_passes_validation(tmp_path):
    """Holzer: a few Windows-1252 bytes plus real UTF-8 text. DuckDB latin-1 rejects it; the cp1252 clean copy works."""
    from pipeline.hpt.validate import validate
    lines = FIX_CSV.read_bytes().split(b"\n")
    lines[3] = b"\x93QUOTED\x94 " + lines[3]
    lines[4] = "CAFÉ ".encode("utf-8") + lines[4]
    f = tmp_path / "99-2_MIXED_standardcharges.csv"
    f.write_bytes(b"\n".join(lines))
    ok, code, detail, info = validate(f, tmp_path / "w")
    assert ok, (code, detail)


def test_json_with_long_modifier_list_before_the_charges(tmp_path):
    """Knox: a long modifier list sits before standard_charge_information (more than 200 KB)."""
    from pipeline.hpt.validate import validate
    d = json.loads(FIX_JSON.read_text(encoding="utf-8"))
    charges = d.pop("standard_charge_information")
    d["modifier_information"] = [{"description": "MODIFIER " + "x" * 80, "code": str(i)} for i in range(4000)]
    d["standard_charge_information"] = charges
    f = tmp_path / "99-3_KNOX_standardcharges.json"
    f.write_text(json.dumps(d), encoding="utf-8")
    assert f.stat().st_size > 300_000
    ok, code, detail, info = validate(f, tmp_path / "w")
    assert ok, (code, detail)
    d2 = {k: v for k, v in d.items() if k != "standard_charge_information"}
    f2 = tmp_path / "99-4_NOCHARGES_standardcharges.json"
    f2.write_text(json.dumps(d2), encoding="utf-8")
    ok, code, detail, info = validate(f2, tmp_path / "w2")
    assert not ok and code == "INVALID"