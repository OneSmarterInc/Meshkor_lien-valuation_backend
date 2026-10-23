"""Build small test fixtures.

Real-file fixtures: trimmed copies of the CMS downloads in data/raw (kept
to the Spec §8 test codes, so tests check real layouts and real values).
Synthetic fixtures: NPPES, OPPS Addendum B and HCRIS, written in the
documented layouts until real samples arrive.

Run:  python -m tests.make_fixtures
"""
from __future__ import annotations

import csv
import io
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
FIX = ROOT / "tests" / "fixtures" / "raw"
CODES = ("99214", "45378", "29881", "73721", "27447", "70473", "G0463", "A2046", "0001F")


def _zip(path: Path, files: dict[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)


def _trim(text: str, keep_header_until: str, keep, header_line_limit: int = 60) -> str:
    out, in_body = [], False
    for ln in text.splitlines(keepends=True):
        if not in_body:
            out.append(ln)
            if keep_header_until in ln:
                in_body = True
            continue
        if keep(ln):
            out.append(ln)
    return "".join(out)


def real_fixtures() -> None:
    starts = tuple(c + "," for c in CODES)
    # RVU26D
    src = RAW / "mpfs/2026D/rvu26d_0.zip"
    if src.exists():
        with zipfile.ZipFile(src) as zf:
            files = {}
            for n in zf.namelist():
                if not n.endswith(".csv"):
                    continue
                t = zf.read(n).decode("utf-8-sig")
                if n.startswith("PPRRVU") and "nonQPP" in n:
                    t = _trim(t, "HCPCS,MOD,DESCRIPTION", lambda ln: ln.startswith(starts))
                elif n.startswith("OPPSCAP"):
                    t = _trim(t, "HCPCS,MOD", lambda ln: ln.startswith(starts) and ",15202," in ln
                              or ln.startswith("70473,,") and ",01112,05," in ln)
                elif "QPP" in n:
                    continue
                files[n] = t.encode()
        _zip(FIX / "mpfs/2026D/rvu26d_0.zip", files)
    # ASC
    src = RAW / "asc/2026Q4/october_2026_asc_addenda.26.10.09.zip"
    if src.exists():
        with zipfile.ZipFile(src) as zf:
            files = {}
            for n in zf.namelist():
                if not any(n.endswith(s) for s in ("AA.csv", "BB.csv", "DD1.csv")):
                    continue
                t = zf.read(n).decode("utf-8-sig")
                if "DD1" not in n:
                    t = _trim(t, "HCPCS Code", lambda ln: ln.startswith(starts))
                files[n] = t.encode("utf-8-sig")
        _zip(FIX / "asc/2026Q4/october_2026_asc_addenda.26.10.09.zip", files)
    # MUE
    for name in ("facilityoutpatienthospitalservicesmuetable-effective-10-01-2026.zip",
                 "practitionerservicesmuetable-effective-10-01-2026.zip"):
        src = RAW / "mue/2026Q4" / name
        if src.exists():
            with zipfile.ZipFile(src) as zf:
                n = next(x for x in zf.namelist() if x.endswith(".csv"))
                t = zf.read(n).decode("latin-1")
                t = _trim(t, "MUE Rationale", lambda ln: ln.startswith(starts))
                _zip(FIX / "mue/2026Q4" / name, {n: t.encode("latin-1")})
    # NCCI hospital part 1 — keep edits for the test codes plus the
    # modifier-9 duplicate pairs used in tests.
    src = RAW / "ncci/2026Q4/ccioph-v323r0-f1.zip"
    if src.exists():
        with zipfile.ZipFile(src) as zf:
            n = next(x for x in zf.namelist() if x.endswith(".txt"))
            lines = zf.read(n).decode("latin-1").splitlines(keepends=True)
            head, body = lines[:6], lines[6:]
            keep = [ln for ln in body if ln.split("\t")[0] in CODES or ln.startswith(("00100\t99497", "0001A\t0591T"))]
            _zip(FIX / "ncci/2026Q4/ccioph-v323r0-f1.zip", {n: "".join(head + keep).encode("latin-1")})

    # IPPS FY2027: Table 5 (CN) with DRGs 469/470, impact file (CN) with 3 Ohio hospitals
    src = RAW / "ipps/FY2027/cms-1849-fr-and-cn-table-5.zip"
    if src.exists():
        with zipfile.ZipFile(src) as zf:
            n = next(x for x in zf.namelist() if x.endswith("CN Table 5.txt"))
            lines = zf.read(n).decode("latin-1").splitlines(keepends=True)
            keep = lines[:3] + [ln for ln in lines[3:] if ln.startswith(("469\t", "470\t"))]
            _zip(FIX / "ipps/FY2027/cms-1849-fr-and-cn-table-5.zip", {n: "".join(keep).encode("latin-1")})
    src = RAW / "ipps/FY2027/fy-2027-ipps-fr-cn-impact-file.zip"
    if src.exists():
        with zipfile.ZipFile(src) as zf:
            n = next(x for x in zf.namelist() if x.endswith("Correction Notice.txt"))
            lines = zf.read(n).decode("latin-1").splitlines(keepends=True)
            keep = lines[:2] + [ln for ln in lines[2:] if ln.startswith(("360180\t", "360051\t", "360085\t"))]
            _zip(FIX / "ipps/FY2027/fy-2027-ipps-fr-cn-impact-file.zip", {n: "".join(keep).encode("latin-1")})


# ---------------------------------------------------------------- synthetic
def nppes_header() -> list[str]:
    from pipeline.ref.nppes import OPTIONAL, REQUIRED, TAXONOMY_SLOTS
    h = list(REQUIRED.values())
    h.insert(3, "Employer Identification Number (EIN)")
    for i in range(1, TAXONOMY_SLOTS + 1):
        h += [f"Healthcare Provider Taxonomy Code_{i}", f"Provider License Number_{i}",
              f"Provider License Number State Code_{i}", f"Healthcare Provider Primary Taxonomy Switch_{i}"]
    for i in range(1, 3):
        h += [f"Other Provider Identifier_{i}", f"Other Provider Identifier Type Code_{i}",
              f"Other Provider Identifier State_{i}", f"Other Provider Identifier Issuer_{i}"]
    h += list(OPTIONAL.values())
    return h


def nppes_fixture() -> None:
    h = nppes_header()

    def row(**kv):
        r = dict.fromkeys(h, "")
        for k, v in kv.items():
            r[k] = v
        return [r[c] for c in h]

    P = "Provider Business Practice Location Address "
    rows = [
        # Ohio doctor, primary flag on slot 3 (not slot 1)
        row(**{"NPI": "1000000001", "Entity Type Code": "1", "Provider Last Name (Legal Name)": "SMITH",
               "Provider First Name": "ANNA", "Provider Credential Text": "MD",
               P + "City Name": "Dayton", P + "State Name": "OH", P + "Postal Code": "454021234",
               "Provider Enumeration Date": "05/23/2008", "Last Update Date": "01/02/2026",
               "Healthcare Provider Taxonomy Code_1": "207Q00000X", "Healthcare Provider Primary Taxonomy Switch_1": "N",
               "Healthcare Provider Taxonomy Code_3": "207X00000X", "Healthcare Provider Primary Taxonomy Switch_3": "Y"}),
        # Ohio hospital with a Medicare OSCAR (CCN) other identifier
        row(**{"NPI": "1000000002", "Entity Type Code": "2",
               "Provider Organization Name (Legal Business Name)": "EXAMPLE GENERAL HOSPITAL",
               P + "City Name": "COLUMBUS", P + "State Name": "OH", P + "Postal Code": "43215",
               "Provider Enumeration Date": "06/01/2006",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y",
               "Other Provider Identifier_1": "360001", "Other Provider Identifier Type Code_1": "06",
               "Other Provider Identifier_2": "0012345", "Other Provider Identifier Type Code_2": "05",
               "Is Organization Subpart": "N"}),
        # Kentucky border (zip3 410), no primary flag set
        row(**{"NPI": "1000000003", "Entity Type Code": "1", "Provider Last Name (Legal Name)": "JONES",
               "Provider First Name": "LEE", P + "City Name": "COVINGTON", P + "State Name": "KY",
               P + "Postal Code": "41011", "Provider Enumeration Date": "03/03/2010",
               "Healthcare Provider Taxonomy Code_1": "208600000X", "Healthcare Provider Primary Taxonomy Switch_1": "X"}),
        # Deactivated NPI: NPPES blanks everything but the NPI and dates
        row(**{"NPI": "1000000004", "NPI Deactivation Date": "07/15/2025", "NPI Deactivation Reason Code": ""}),
        # Deactivated then reactivated
        row(**{"NPI": "1000000005", "Entity Type Code": "1", "Provider Last Name (Legal Name)": "BACK",
               P + "State Name": "OH", P + "Postal Code": "44101", "Provider Enumeration Date": "01/01/2015",
               "NPI Deactivation Date": "01/01/2020", "NPI Reactivation Date": "06/01/2020",
               "Healthcare Provider Taxonomy Code_1": "390200000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Hospital department NPI at the enrolled hospital's street address (not on the enrollment)
        row(**{"NPI": "1000000011", "Entity Type Code": "2",
               "Provider Organization Name (Legal Business Name)": "TEST HOSPITAL LAB",
               "Provider First Line Business Practice Location Address": "1 Main Street, Suite 200",
               P + "City Name": "DAYTON", P + "State Name": "OH", P + "Postal Code": "454091234",
               "Provider Enumeration Date": "06/01/2010", "Is Organization Subpart": "Y",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Hospital NPI with the enrolled legal name, other street, same zip
        row(**{"NPI": "1000000012", "Entity Type Code": "2",
               "Provider Organization Name (Legal Business Name)": "Test Hospital, Inc.",
               "Provider First Line Business Practice Location Address": "99 OTHER RD",
               P + "City Name": "DAYTON", P + "State Name": "OH", P + "Postal Code": "45409",
               "Provider Enumeration Date": "06/01/2011", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Ohio hospital NPI with no enrollment anywhere (stays unmatched)
        row(**{"NPI": "1000000013", "Entity Type Code": "2",
               "Provider Organization Name (Legal Business Name)": "LONELY HOSPITAL",
               "Provider First Line Business Practice Location Address": "5 FAR AWAY LN",
               P + "City Name": "LIMA", P + "State Name": "OH", P + "Postal Code": "45801",
               "Provider Enumeration Date": "06/01/2012", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # VA hospital (no Medicare enrollment) and a person filed with a hospital taxonomy
        row(**{"NPI": "1000000014", "Entity Type Code": "2", "Provider Organization Name (Legal Business Name)": "DAYTON VAMC",
               "Provider First Line Business Practice Location Address": "4100 W 3RD ST",
               P + "City Name": "DAYTON", P + "State Name": "OH", P + "Postal Code": "45428",
               "Last Update Date": "03/01/2024", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        row(**{"NPI": "1000000015", "Entity Type Code": "2", "Provider Organization Name (Legal Business Name)": "APRIL STAUFFER",
               "Provider First Line Business Practice Location Address": "3010 YORKSHIRE RD",
               P + "City Name": "CLEVELAND HEIGHTS", P + "State Name": "OH", P + "Postal Code": "44118",
               "Last Update Date": "03/01/2024", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Closed hospital: record not updated since 2016
        row(**{"NPI": "1000000016", "Entity Type Code": "2", "Provider Organization Name (Legal Business Name)": "OLD TOWN HOSPITAL",
               "Provider First Line Business Practice Location Address": "1 GONE ST",
               P + "City Name": "LIMA", P + "State Name": "OH", P + "Postal Code": "45801",
               "Last Update Date": "05/01/2016", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Enrolled name, same city, wrong zip in NPPES
        row(**{"NPI": "1000000017", "Entity Type Code": "2", "Provider Organization Name (Legal Business Name)": "TEST HOSPITAL",
               "Provider First Line Business Practice Location Address": "77 SIDE ST",
               P + "City Name": "Dayton", P + "State Name": "OH", P + "Postal Code": "45499",
               "Last Update Date": "03/01/2024", "Is Organization Subpart": "N",
               "Healthcare Provider Taxonomy Code_1": "282N00000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
        # Active in main file; the deactivation report says deactivated
        row(**{"NPI": "1000000006", "Entity Type Code": "1", "Provider Last Name (Legal Name)": "GONE",
               P + "State Name": "IN", P + "Postal Code": "47001", "Provider Enumeration Date": "01/01/2012",
               "Healthcare Provider Taxonomy Code_1": "390200000X", "Healthcare Provider Primary Taxonomy Switch_1": "Y"}),
    ]
    buf = io.StringIO()
    w = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
    w.writerow(h)
    w.writerows(rows)
    hbuf = io.StringIO()
    csv.writer(hbuf, quoting=csv.QUOTE_ALL, lineterminator="\n").writerow(h)
    _zip(FIX / "nppes/2026-10/NPPES_Data_Dissemination_October_2026_V2.zip", {
        "npidata_pfile_20050523-20261011.csv": buf.getvalue().encode(),
        "npidata_pfile_20050523-20261011_fileheader.csv": hbuf.getvalue().encode(),
        "NPPES_Data_Dissemination_Readme_v.2.pdf": b"%PDF-1.4 placeholder",
    })
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["NPPES Deactivated NPI Report"])
    ws.append([])
    ws.append(["NPI", "NPPES Deactivation Date"])
    ws.append(["1000000004", "07/15/2025"])
    ws.append(["1000000006", "09/30/2026"])
    xb = io.BytesIO()
    wb.save(xb)
    _zip(FIX / "nppes/2026-10/NPPES_Deactivated_NPI_Report_101226_V2.zip",
         {"NPPES Deactivated NPI Report 20261012.xlsx": xb.getvalue()})


def opps_fixture() -> None:
    t = (
        '"Addendum B.--OPPS Payment by HCPCS Code for CY 2026",,,,,,,,\n'
        '"CPT codes and descriptions only are copyright 2025 American Medical Association.",,,,,,,,\n'
        ',,,,,,,,\n'
        'HCPCS Code,Short Descriptor,SI,APC,Relative Weight,Payment Rate,National Unadjusted Copayment,'
        'Minimum Unadjusted Copayment,Note\n'
        '99214,Office o/p est mod 30 min,J2,5012,1.5000,"$150.00 ",,"$30.00 ",\n'
        '45378,Diagnostic colonoscopy,J1,5312,13.0000,"$1,300.00 ",,"$260.00 ",\n'
        '29881,Arthrs kne srg mnisectmy m/l,J1,5113,40.0000,"$4,000.00 ",,"$800.00 ",\n'
        '73721,Mri jnt of lwr extre w/o dye,Q3,5523,4.0000,"$400.00 ",,"$80.00 ",\n'
        '27447,Total knee arthroplasty,J1,5115,143.4859,"$13,116.76 ",,"$2,623.36 ",\n'
        'G0463,Hospital outpt clinic visit,J2,5012,1.5000,"$150.00 ",,"$30.00 ",\n'
    )
    _zip(FIX / "opps/2026Q4/October-2026-OPPS-Addendum-B.zip",
         {"2026_october_web_addendum_b.csv": t.encode(), "readme.txt": b"synthetic"})


def hcris_fixture() -> None:
    rpt = ("101,4,360001,1000000002,1,01/01/2024,12/31/2024,06/30/2025,,,,15201,,05/31/2025,F,,,05/30/2025\n"
           "102,2,360002,,2,07/01/2023,06/30/2024,01/15/2025,,,,15201,,,F,,,\n"
           "103,2,360002,,1,07/01/2024,12/31/2024,03/01/2025,,,,15201,,,F,,,\n"
           "104,2,361300,,1,01/01/2024,12/31/2024,04/01/2025,,,,15201,,,F,,,\n")
    nmrc = ("101,C000001,20200,00500,250000000\n"
            "101,C000001,20200,00800,1000000000\n"
            "101,S300001,01400,00200,300\n"
            "101,A000000,00100,00100,999\n"
            "102,C000001,20200,00500,60000000\n"
            "102,C000001,20200,00800,200000000\n"
            "103,C000001,20200,00500,30000000\n"
            "103,C000001,20200,00800,90000000\n"
            "104,C000001,20200,00500,1000\n"
            "104,C000001,20200,00800,0\n")
    _zip(FIX / "hcris/FY2024/HOSP10FY2024.zip",
         {"HOSP10_2024_RPT.CSV": rpt.encode(), "HOSP10_2024_NMRC.CSV": nmrc.encode(),
          "HOSP10_2024_ALPHA.CSV": b"101,S200001,00100,00100,EXAMPLE GENERAL HOSPITAL\n"})


ENROLL_HDR = ("ENROLLMENT ID,ENROLLMENT STATE,PROVIDER TYPE CODE,PROVIDER TYPE TEXT,NPI,MULTIPLE NPI FLAG,CCN,"
              "ASSOCIATE ID,ORGANIZATION NAME,DOING BUSINESS AS NAME,INCORPORATION DATE,INCORPORATION STATE,"
              "ORGANIZATION TYPE STRUCTURE,ORGANIZATION OTHER TYPE TEXT,PROPRIETARY NONPROFIT,ADDRESS LINE 1,"
              "ADDRESS LINE 2,CITY,STATE,ZIP CODE,PRACTICE LOCATION TYPE,LOCATION OTHER TYPE TEXT,SUBGROUP - GENERAL,"
              "SUBGROUP - ACUTE CARE,SUBGROUP - ALCOHOL DRUG,SUBGROUP - CHILDRENS,SUBGROUP - LONG-TERM,"
              "SUBGROUP - PSYCHIATRIC,SUBGROUP - REHABILITATION,SUBGROUP - SHORT-TERM,SUBGROUP - SWING-BED APPROVED,"
              "SUBGROUP - PSYCHIATRIC UNIT,SUBGROUP - REHABILITATION UNIT,SUBGROUP - SPECIALTY HOSPITAL,"
              "SUBGROUP - OTHER,SUBGROUP - OTHER TEXT,REH CONVERSION FLAG,REH CONVERSION DATE,CAH OR HOSPITAL CCN")


def enrollment_fixture() -> None:
    """Synthetic Hospital Enrollments (real July 2026 header)."""
    d = FIX / "enrollments" / "2026-07"
    d.mkdir(parents=True, exist_ok=True)
    tail = ",N,1 MAIN ST,,DAYTON,OH,454091234,MAIN/PRIMARY HOSPITAL LOCATION,,Y,Y,N,N,N,N,N,Y,N,N,N,N,N,,N,,"
    rows = [ENROLL_HDR,
            "O20020101000001,OH,00-09,PART A PROVIDER - HOSPITAL,1000000002,Y,360051,1,TEST HOSPITAL,,,,CORPORATION,"
            + tail,
            # CCN that lost its leading zero in Excel
            "O20020101000002,CA,00-09,PART A PROVIDER - HOSPITAL,1000000007,N,50001,2,CA HOSPITAL,,,,CORPORATION,"
            + tail.replace("1 MAIN ST,,DAYTON,OH,454091234", "2 PALM AVE,,FRESNO,CA,93701")]
    (d / "Hospital_Enrollments_2026.07.31.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (d / "Hospital_Additional_NPIs_2026.07.31.csv").write_text(
        '"ENROLLMENT ID","NPI"\nO20020101000001,1000000009\nO29999999999999,1000000010\n', encoding="utf-8")


UTIL_HDR = ("Rndrng_NPI,Rndrng_Prvdr_Last_Org_Name,Rndrng_Prvdr_First_Name,Rndrng_Prvdr_MI,Rndrng_Prvdr_Crdntls,"
            "Rndrng_Prvdr_Ent_Cd,Rndrng_Prvdr_St1,Rndrng_Prvdr_St2,Rndrng_Prvdr_City,Rndrng_Prvdr_State_Abrvtn,"
            "Rndrng_Prvdr_State_FIPS,Rndrng_Prvdr_Zip5,Rndrng_Prvdr_RUCA,Rndrng_Prvdr_RUCA_Desc,Rndrng_Prvdr_Cntry,"
            "Rndrng_Prvdr_Type,Rndrng_Prvdr_Mdcr_Prtcptg_Ind,HCPCS_Cd,HCPCS_Desc,HCPCS_Drug_Ind,Place_Of_Srvc,"
            "Tot_Benes,Tot_Srvcs,Tot_Bene_Day_Srvcs,Avg_Sbmtd_Chrg,Avg_Mdcr_Alowd_Amt,Avg_Mdcr_Pymt_Amt,Avg_Mdcr_Stdzd_Amt")


def utilization_fixture() -> None:
    """Synthetic 'by Provider and Service' rows (real CY2024 header).
    27447: orthopedic surgery dominant, 11 specialties at 1.6 %, dermatology
    at 0.02 % and rank 13 -> not plausible."""
    d = FIX / "utilization" / "CY2024"
    d.mkdir(parents=True, exist_ok=True)

    def r(npi, spec, code, srv):
        return (f'{npi},X,Y,,MD,I,1 ST,,DAYTON,OH,39,45409,1,"Metro, core",US,{spec},Y,{code},'
                f'"desc, with comma",N,F,{srv},{srv},{srv},100,50,40,41')
    rows = [UTIL_HDR, r(1000000001, "Orthopedic Surgery", "27447", 4000),
            r(1000000003, "Orthopedic Surgery", "27447", 1000.0)]
    rows += [r(1100000000 + i, f"Specialty {chr(65 + i)}", "27447", 100) for i in range(11)]
    rows += [r(1000000003, "Dermatology", "27447", 1),
             r(1000000001, "Internal Medicine", "99214", 300),
             r(1000000003, "Dermatology", "17000", 50)]
    (d / "PHY_R26_P05_V10_D24_Prov_Svc.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")


def ipps_fy2025_fixture() -> None:
    """FY2025 IFC impact file + CN Table 5, synthetic rows on the real FY2025
    headers: year wage-index name, CMIV41/42, low volume before VBP, a quoted
    multi-line Table 5 header."""
    hdr = ("Provider Number|Name|Geographic Labor Market Area|Pre-Reclass Labor Market Area|"
           "Post Reclass Labor Market Area|Payment Labor Market Area|FIPS County Code|Region|URGEO|URSPA|"
           "RECLASS|FY 2025 Wage Index|LUGAR|Section 401 Hospital|"
           "Section 401 or LUGAR Hospitals with a MGCRB Wage Index Reclass|Section 505 Eligible|"
           "Section 505 Adjustment|Cost of Living Adjustment|Resident to Bed Ratio|RDAY|Beds|"
           "Average Daily Census|TCHOP|TCHCP|DSHPCT|DSHOPP|DSHCPP|DSH_LY|UCP_ADJ|UCP Per Claim Amount|"
           "UCP_ADJ_LY|UCP Per Claim Amount LY|Operating CCR|Capital CCR|Provider Type|HSP Rate|Bills|"
           "CASETA41|CMIV41|TACMIV41|IME_CASETA41|IME_TACMIV41|CASETA42|CMIV42|TACMIV42|IME_CASETA42|"
           "IME_TACMIV42|GAF|Capital Cost of Living Adjustment|OUTFACT_F|COUTFACT_F|Medicare Percentage|"
           "Medicaid Percentage|Low Volume Hospital Adjustment|Proxy Value Based Purchasing Adjustment Factor|"
           "Proxy Readmission Adjustment Factor|Proxy Quality Reduction|Proxy EHR Reduction|"
           "Ownership Control Type|MDH Flag, CAA 2024|HSP Rate for MDHs, CAA 2024|"
           "Low-Volume Hospital Payment Adjustment, CAA 2024").split("|")
    val = {"Provider Number": "360051", "Name": "Miami Valley Hospital", "FY 2025 Wage Index": "0.9500",
           "Cost of Living Adjustment": "1", "Beds": "800", "CMIV41": "1.7000", "CMIV42": "1.8000",
           "GAF": "0.9655", "Proxy Quality Reduction": "0", "Proxy EHR Reduction": "0",
           "Payment Labor Market Area": "19430", "Geographic Labor Market Area": "19430",
           "FIPS County Code": "39113", "URGEO": "URBAN", "Provider Type": "0",
           "Ownership Control Type": "2", "Proxy Value Based Purchasing Adjustment Factor": "1.001"}
    row = [val.get(h, "") for h in hdr]
    hdr_txt = "\t".join(f'"{h}"' if "," in h else h for h in hdr)
    impact = ("FY 2025 IPPS Impact File -  Interim Final Action with Comment (September 2024)\n"
              + hdr_txt + "\n" + "\t".join(row) + "\n")
    name = "FY 2025 IPPS Impact File - Interim Final Action with Comment.txt"
    _zip(FIX / "ipps/FY2025/fy_2025_ipps_impact_file-fr-cn-ifc.zip", {
        name: impact.encode("latin-1"),
        "FY 2025 IPPS Impact File - Correction Notice.txt": b"not used\n"})
    t5 = ('"TABLE 5.LIST OF MS-DRGS\nFY 2025 Correction Notice Final Rule"\n'
          'MS-DRG \t"FY 2025 Correction Notice \nPost-Acute DRG"\t"FY 2025 Correction Notice \nSpecial Pay DRG"'
          "\tMDC\tTYPE\tMS-DRG Title\tWeights - Before Cap\tWeights - 10% Cap Applied \t"
          "Geometric mean LOS\tArithmetic mean LOS\n"
          "470\tYes\tNo\t08\tSURG\tMAJOR HIP AND KNEE JOINT REPLACEMENT OR REATTACHMENT OF LOWER "
          "EXTREMITY WITHOUT MCC\t1.9000\t1.9000\t1.7\t2.0\n")
    _zip(FIX / "ipps/FY2025/fy2025-ipps-final-rule-and-correction-notice-table-5.zip", {
        "FY2025 IPPS Correction Notice Table 5.txt": t5.encode("latin-1"),
        "FY2025 IPPS Final Rule Table 5.txt": b"not used\n"})


def ambulance_2025_fixture() -> None:
    """CY2025 ambulance as a comma CSV with a UTF-8 BOM (the 2024/2025 508 format),
    made from the 2026 fixture, in the 2025 column order; A0427 urban at 01112/05 set to 700.00."""
    import csv, io
    src = FIX / "ambulance/2026"
    with zipfile.ZipFile(src / "afs2026_puf_ext.zip") as zf:
        txt = zf.read(zf.namelist()[0]).decode("latin-1")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    for line in txt.splitlines():
        row = next(csv.reader([line], delimiter="\t"))
        if row[:3] == ["01112", "05", "A0427"]:
            row[6] = "$700.00"
        row = [row[2], row[0], row[1]] + row[3:]          # 2025 order: HCPCS, CARRIER, LOCALITY, ...
        if row[0] == "HCPCS":
            row[7] = row[7].replace("RURAL BASE", "RURALBASE")   # as in the real 2025 header
        w.writerow(row)
    d = FIX / "ambulance/2025"
    d.mkdir(parents=True, exist_ok=True)
    (d / "508-compliant-version-AFS2025_PUF_ext.csv").write_bytes(b"\xef\xbb\xbf" + out.getvalue().encode("latin-1"))
    with zipfile.ZipFile(src / "zplc_oct2026.zip") as zf:
        n = next(x for x in zf.namelist() if x.upper().startswith("ZIP5_") and x.lower().endswith(".txt"))
        (d / "ZIP5_DEC2025_FINAL.txt").write_bytes(zf.read(n))


def ambulance_2024_fixture() -> None:
    """CY2024 ambulance as a comma CSV in the 2024 column order (CONTRACTOR first),
    with the leading 0 dropped from the carrier as Excel does; A0427 urban 690.00."""
    import csv, io
    src = FIX / "ambulance/2026"
    with zipfile.ZipFile(src / "afs2026_puf_ext.zip") as zf:
        txt = zf.read(zf.namelist()[0]).decode("latin-1")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    for line in txt.splitlines():
        row = next(csv.reader([line], delimiter="\t"))
        if row[:3] == ["01112", "05", "A0427"]:
            row[6] = "$690.00"
        if row[0].isdigit():
            row[0] = row[0].lstrip("0")
        w.writerow(row)
    d = FIX / "ambulance/2024"
    d.mkdir(parents=True, exist_ok=True)
    (d / "508-Version-AFS2024__PUF.csv").write_bytes(out.getvalue().encode("latin-1"))
    with zipfile.ZipFile(src / "zplc_oct2026.zip") as zf:
        n = next(x for x in zf.namelist() if x.upper().startswith("ZIP5_") and x.lower().endswith(".txt"))
        (d / "ZIP5_DEC2024_FINAL.txt").write_bytes(zf.read(n))


def main() -> None:
    import sys
    sys.path.insert(0, str(ROOT))
    real_fixtures()
    enrollment_fixture()
    utilization_fixture()
    nppes_fixture()
    opps_fixture()
    hcris_fixture()
    ipps_fy2025_fixture()
    ambulance_2025_fixture()
    ambulance_2024_fixture()
    print("fixtures written to", FIX)


if __name__ == "__main__":
    main()
