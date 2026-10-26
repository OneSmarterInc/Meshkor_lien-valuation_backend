r"""Pricing step tests (pipeline/lien). Run:
    set DB_ENGINE=sqlite && python backend\manage.py test cases accounts
Uses the synthetic test bills in tests/fixtures/test_bills and a tiny DuckDB (lien_testdb.py)."""
import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

from accounts.models import Firm, Profile
from pipeline.lien import db, match, price, reader
from . import lien_testdb as T
from .models import Case

BILLS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "test_bills"
TMP = tempfile.mkdtemp()
DATA = Path(tempfile.mkdtemp())
T.build(DATA)


def bill(name):
    return (BILLS / f"{name}_TEST_bill.pdf").read_bytes()


@mock.patch.dict(os.environ, {"MESHKOR_DATA_ROOT": str(DATA)})
class ReaderAndPriceTests(SimpleTestCase):
    def test_reader_gets_header_lines_and_total(self):
        b = reader.read(bill("B01"), "b.pdf")
        self.assertEqual((b.ccn, b.type_of_bill, b.payer), ("360085", "0131", "Anthem"))
        self.assertEqual(b.facility_name, "OHIO STATE UNIVERSITY HOSPITALS")
        self.assertEqual((b.date_from, b.date_to), (date(2026, 8, 14), date(2026, 8, 14)))
        self.assertEqual(len(b.lines), 11)
        self.assertEqual(b.lines_total, Decimal("9647.87")); self.assertEqual(b.stated_total, Decimal("9647.87"))
        ln = b.lines[9]
        self.assertEqual((ln.revenue_code, ln.hcpcs, ln.units, ln.charge), ("0636", "J2405", Decimal("4"), Decimal("1.00")))
        self.assertFalse(b.inpatient)
        b8 = reader.read(bill("B08"), "b.pdf")
        self.assertTrue(b8.inpatient); self.assertEqual(b8.ms_drg, "481")
        self.assertEqual(b8.lines[3].hcpcs, ""); self.assertEqual(b8.lines[3].units, Decimal("3"))   # room and board, no code
        self.assertTrue(b8.lines[11].description.endswith("MINS"))                                   # wrapped text joined

    def _photo(self, name="B01"):
        """A tilted, blurred phone-photo of a synthetic test bill, as JPEG bytes."""
        import io as _io
        import pypdfium2 as pdfium
        from PIL import ImageFilter
        img = pdfium.PdfDocument(bill(name))[0].render(scale=200 / 72).to_pil().convert("RGB")
        img = img.resize((int(img.width * 0.75), int(img.height * 0.75))).rotate(1.0, expand=True, fillcolor=(235, 232, 225))
        img = img.filter(ImageFilter.GaussianBlur(0.6))
        out = _io.BytesIO(); img.save(out, "JPEG", quality=70)
        return out.getvalue()

    def test_ocr_reads_a_phone_photo(self):
        b = reader.read(self._photo("B01"), "photo.jpg")
        self.assertEqual(b.method, "ocr")
        self.assertEqual((b.ccn, b.payer, str(b.date_from)), ("360085", "Anthem", "2026-08-14"))
        self.assertEqual(len(b.lines), 11)
        self.assertEqual(b.lines_total, Decimal("9647.87")); self.assertEqual(b.stated_total, Decimal("9647.87"))
        self.assertTrue(all(ln.confidence <= 0.95 for ln in b.lines))          # OCR is never "certain"
        codes = [ln.hcpcs for ln in b.lines]
        self.assertEqual(codes[:3], ["99285", "70450", "72125"])

    def test_ocr_reads_a_scanned_pdf(self):
        import io as _io
        from PIL import Image
        buf = _io.BytesIO(); Image.open(_io.BytesIO(self._photo("B08"))).save(buf, "PDF")
        b = reader.read(buf.getvalue(), "scan.pdf")
        self.assertEqual(b.method, "ocr"); self.assertTrue(b.inpatient); self.assertEqual(b.ms_drg, "481")
        self.assertEqual(b.lines_total, Decimal("58612.00"))

    def test_word_file_with_a_table(self):
        import io as _io
        import docx
        d = docx.Document()
        for t in ("Facility OHIO STATE UNIVERSITY HOSPITALS", "CCN 360085", "Type of bill 0131",
                  "Service dates 2026-09-18 to 2026-09-18", "Primary payer Aetna"):
            d.add_paragraph(t)
        rows = [("#", "Date", "Rev", "HCPCS/CPT", "Units", "Description", "Charge"),
                ("1", "2026-09-18", "0610", "73721", "1", "HC MRI LOWER EXTREMITY JOINT W/O CONTRAST", "$2,957.00")]
        tb = d.add_table(rows=0, cols=7)
        for r in rows:
            cells = tb.add_row().cells
            for c, v in zip(cells, r):
                c.text = v
        d.add_paragraph("TOTAL CHARGES $2,957.00")
        buf = _io.BytesIO(); d.save(buf)
        b = reader.read(buf.getvalue(), "bill.docx")
        self.assertEqual((b.method, b.ccn, b.payer, len(b.lines)), ("docx", "360085", "Aetna", 1))
        ln = b.lines[0]
        self.assertEqual((ln.revenue_code, ln.hcpcs, ln.units, ln.charge), ("0610", "73721", Decimal("1"), Decimal("2957.00")))

    def test_not_a_readable_bill(self):
        with self.assertRaises(reader.BillNotReadable):
            reader.read(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", "b.pdf")
        with self.assertRaises(reader.BillNotReadable):
            reader.read(b"\x89PNG....", "scan.png")

    def test_outpatient_line_values(self):
        b = reader.read(bill("B01"), "b.pdf")
        con = db.connect()
        r = price.price(con, b, "360085", b.payer)
        con.close()
        self.assertEqual(r.payer_group, "Anthem"); self.assertTrue(r.price_file.covers_service_date)
        er = r.lines["service_date"][0]
        self.assertEqual(er["payer_rate"], Decimal("1450.00"))          # median of the 2 Anthem outpatient plans; inpatient row ignored
        self.assertEqual(er["median"], Decimal("1450.00"))              # commercial only: 1300, 1400, 1500, 1700 (Humana MA 620, Medicaid 450 left out)
        self.assertEqual(er["medicare"], Decimal(str(T.opps_adjusted(600))))
        self.assertEqual(er["cost"], Decimal("714.63"))                 # 3403 x 0.21
        ct = r.lines["service_date"][1]
        self.assertTrue(ct["payer_rate_is_estimate"]); self.assertEqual(ct["payer_rate"], Decimal("825.60"))   # 40 % of 2064
        self.assertEqual(ct["median"], Decimal("750.00"))                 # Cigna's 0.62 "dollar" row is a factor: left out
        self.assertFalse(price.is_multiplier({"negotiated_dollar": 3.0, "gross_charge": 60.0}, 3.0))   # a real cheap price (venipuncture)
        self.assertTrue(price.is_multiplier({"negotiated_dollar": 0.62, "gross_charge": 3403.0}, 586.78))
        self.assertIn("Factors posted as dollars", " ".join(f["title"] for f in r.flags))
        lab = r.lines["service_date"][5]
        self.assertEqual((lab["medicare"], lab["medicare_source"]), (Decimal("7.50"), "CLFS 2026Q3"))
        self.assertEqual(lab["cash"], Decimal("15.00"))
        xr = r.lines["service_date"][3]                                  # 226.10 % of Medicare, and a $200 plan
        self.assertEqual(xr["payer_rate"], Decimal(str(round((2.261 * T.opps_adjusted(70) + 200) / 2, 2))))
        self.assertTrue(xr["payer_rate_is_estimate"])
        self.assertIn("226.1 %", " ".join(f["title"] for f in r.flags))
        drug = r.lines["service_date"][8]
        self.assertEqual((drug["medicare"], drug["medicare_status"]), (Decimal("0.00"), "packaged"))
        self.assertNotIn("estimate", r.lines)
        self.assertEqual(r.totals["billed"], 9647.87)
        self.assertEqual(r.totals["coverage"]["payer_rate"], round(100 * (3403 + 2064 + 323 + 131) / 9647.87))
        kinds = {f["kind"] for f in r.flags}
        self.assertIn("packaged", kinds); self.assertIn("no_rate", kinds)

    def test_comprehensive_apc_packages_the_other_lines(self):
        b = reader.read(bill("B07"), "b.pdf")
        con = db.connect()
        r = price.price(con, b, "360085", b.payer)
        con.close()
        lines = r.lines["service_date"]
        # anesthesia, recovery room, implant: no code, paid inside the J1 payment -> $0 and counted as covered
        self.assertEqual([(l["medicare"], l["medicare_status"]) for l in lines[1:4]], [(Decimal("0.00"), "packaged")] * 3)
        self.assertEqual(r.totals["coverage"]["medicare"], 100)
        self.assertEqual(r.totals["coverage"]["medicare_billed"], 27671.34)
        self.assertEqual(lines[0]["medicare"], Decimal(str(T.opps_adjusted(6800))))
        self.assertEqual(lines[4]["medicare_status"], "packaged")           # splint 29125 rides on the J1 line
        self.assertEqual(r.totals["medicare"], T.opps_adjusted(6800))

    def test_inpatient_stay_priced_as_one_drg(self):
        b = reader.read(bill("B08"), "b.pdf")
        con = db.connect()
        r = price.price(con, b, "360085", b.payer)
        con.close()
        v = r.stay["values"]
        self.assertEqual(r.stay["ms_drg"], "481"); self.assertEqual(r.stay["los_days"], 3)
        self.assertEqual(v["payer_rate"], 22000.0)                          # UnitedHealthcare
        self.assertEqual(v["median"], 22000.0)                              # commercial: exchange 20401.30, UHC 22000, Anthem 26000 (Medicare left out)
        self.assertEqual(v["medicare"], T.ipps_total(2.0))
        self.assertEqual(v["cost"], round(58612 * T.CCR, 2))
        self.assertEqual(r.totals["payer_rate"], 22000.0)
        self.assertIn("drg_check", {f["kind"] for f in r.flags})

    def test_service_date_before_the_price_file_gives_an_estimate(self):
        b = reader.read(bill("B01"), "b.pdf")
        b.date_from = b.date_to = date(2026, 3, 1)
        for ln in b.lines:
            ln.service_date = date(2026, 3, 1)
        con = db.connect()
        r = price.price(con, b, "360085", b.payer)
        con.close()
        self.assertFalse(r.price_file.covers_service_date)
        self.assertIsNone(r.lines["service_date"][0]["payer_rate"])
        self.assertEqual(r.lines["estimate"][0]["payer_rate"], Decimal("1450.00"))
        self.assertTrue(r.lines["estimate"][0]["payer_rate_is_estimate"])
        self.assertIn("estimate", {f["kind"] for f in r.flags})
        self.assertEqual(r.totals["basis"], "estimate")                    # the report uses the nearest file ...
        self.assertEqual(r.totals["payer_rate"], 1450.0 + 825.6 + 200.0 + 20.0)   # no OPPS rate in March, so no %-of-Medicare value
        self.assertTrue(r.totals["payer_rate_is_estimate"])                 # ... and says every value is an estimate
        self.assertNotIn("Line 1", " ".join(f["title"] for f in r.flags if f["kind"] == "no_rate"))

    def test_unknown_insurer_gets_no_rate_and_a_reversal_line_subtracts(self):
        b = reader.read(bill("B01"), "b.pdf")
        con = db.connect()
        r = price.price(con, b, "360085", "XYZ Benefit Trust")
        self.assertEqual(r.payer_group, "Other")
        self.assertTrue(all(l["payer_rate"] is None for l in r.lines["service_date"]))   # never another plan's rate
        self.assertIn("not in the payer list", " ".join(f["title"] for f in r.flags))
        import copy
        b2 = copy.deepcopy(b)
        rev = copy.deepcopy(b2.lines[0]); rev.line_no = 12; rev.charge = -rev.charge; b2.lines.append(rev)
        r2 = price.price(con, b2, "360085", "Anthem")
        con.close()
        self.assertEqual(r2.lines["service_date"][11]["payer_rate"], Decimal("-1450.00"))
        self.assertEqual(r2.totals["payer_rate"], r.totals["billed"] and round(825.6 + 176.76 + 20.0, 2))
        self.assertEqual(r2.totals["billed"], round(9647.87 - 3403, 2))

    def test_price_file_without_payer_group_column(self):
        # Files loaded with the first load_mrf.py have no payer_group: it is worked out from payer and plan names.
        import shutil, duckdb
        d = Path(tempfile.mkdtemp())
        shutil.copy(DATA / "meshkor.duckdb", d / "meshkor.duckdb")
        c = duckdb.connect(str(d / "meshkor.duckdb")); c.execute("ALTER TABLE ref_hospital_mrf DROP COLUMN payer_group"); c.close()
        b = reader.read(bill("B01"), "b.pdf")
        con = db.connect(d / "meshkor.duckdb")
        r = price.price(con, b, "360085", b.payer)
        con.close()
        self.assertEqual(r.lines["service_date"][0]["payer_rate"], Decimal("1450.00"))

    def test_patient_on_a_government_plan_still_gets_its_own_rate(self):
        # The median is commercial only, but a Medicare Advantage patient's own plan rate is still shown.
        b = reader.read(bill("B01"), "b.pdf")
        con = db.connect()
        r = price.price(con, b, "360085", "Humana Medicare Advantage")
        con.close()
        er = r.lines["service_date"][0]
        self.assertEqual(r.payer_group, "Medicare Advantage")
        self.assertEqual(er["payer_rate"], Decimal("620.00"))
        self.assertEqual(er["median"], Decimal("1450.00"))

    def test_hospital_match_by_npi_and_by_name(self):
        con = db.connect()
        self.assertEqual(match.find(con, npi="1124127683").ccn, "360242")
        m = match.find(con, name="Ohio State University Hospital")
        self.assertEqual((m.ccn, m.method, m.certain), ("360085", "name", False))
        self.assertIsNone(match.find(con, name="Nowhere General"))
        con.close()


@override_settings(MESHKOR_FILE_KEY=Fernet.generate_key().decode(), MESHKOR_UPLOAD_DIR=TMP)
@mock.patch.dict(os.environ, {"MESHKOR_DATA_ROOT": str(DATA)})
class IntakeApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.firm = Firm.objects.create(name="Smith & Lee LLP")
        cls.rev = User.objects.create_user(username="rev@mk.test", email="rev@mk.test", password="pw-12345")
        Profile.objects.create(user=cls.rev, role="reviewer")

    def setUp(self):
        r = self.client.post("/api/auth/login/", {"email": "rev@mk.test", "password": "pw-12345"}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

    def upload(self, name):
        return self.client.post("/api/cases/", {"report_for": "plaintiff", "consent": "true", "firm_id": self.firm.id,
                                                "bill": SimpleUploadedFile(f"{name}.pdf", bill(name), content_type="application/pdf")},
                                format="multipart")

    def test_upload_prices_the_bill(self):
        r = self.upload("B01")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "needs_review")
        self.assertEqual(r.data["hospital_name"], "Ohio State University Hospitals")
        self.assertEqual(r.data["billed_total"], 9647.87)
        cid = r.data["id"]
        det = self.client.get(f"/api/cases/{cid}/").data
        self.assertEqual(det["hospital_match"]["ccn"], "360085")
        self.assertTrue(det["hospital_match"]["price_file"]["covers_service_date"])
        self.assertEqual(det["totals"]["medicare"], Case.objects.get(pk=cid).totals["medicare"])
        self.assertIn("no_eob", {f["kind"] for f in det["flags"]})
        lines = self.client.get(f"/api/cases/{cid}/lines/").data
        self.assertEqual(len(lines), 11); self.assertEqual(lines[0]["payer_rate"], 1450.0)
        self.assertEqual(lines[0]["sources"][0]["label"], "Medicare cost report, year ending 2024-06-30")
        rep = self.client.get(f"/api/cases/{cid}/report/").data
        pr = rep["summary"][1]
        self.assertEqual(pr["key"], "payer_rate")
        cov = Case.objects.get(pk=cid).totals["coverage"]
        self.assertLess(cov["payer_rate"], 100)                           # the Anthem total leaves out some lines ...
        self.assertEqual(pr["pct_of_billed"], round(100 * pr["total"] / cov["payer_rate_billed"]))   # ... so its % uses those lines only
        self.assertIn("lines", pr["note"])
        self.assertIn(f"{pr['pct_of_billed']} % of the billed charges on those", rep["summary_text"])  # text and table agree
        self.assertTrue(all(r["key"] != "cash" or r["pct_of_billed"] is None for r in rep["summary"]))  # cash on 1 line: not compared
        pdf = self.client.get(f"/api/cases/{cid}/report.pdf")
        self.assertEqual(pdf.status_code, 200); self.assertEqual(pdf.content[:4], b"%PDF")

    def test_inpatient_upload_and_drg_change_reprices(self):
        cid = self.upload("B08").data["id"]
        det = self.client.get(f"/api/cases/{cid}/").data
        rep = self.client.get(f"/api/cases/{cid}/report/").data
        self.assertEqual(rep["stay"]["ms_drg"], "481"); self.assertIn("MS-DRG 481", rep["summary_text"])
        self.assertTrue(any(s["data"].startswith("Medicare IPPS") for s in rep["sources"]))
        self.assertEqual(rep["summary"][1]["pct_of_billed"], round(100 * 22000 / 58612))
        self.assertEqual(det["setting"], "inpatient"); self.assertEqual(det["stay"]["ms_drg"], "481")
        self.assertEqual(det["stay"]["values"]["medicare"], T.ipps_total(2.0))
        r = self.client.post(f"/api/cases/{cid}/drg/confirm/", {"ms_drg": "480"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual((r.data["ms_drg"], r.data["drg_source"], r.data["drg_confirmed"]), ("480", "reviewer", True))
        self.assertEqual(r.data["values"]["medicare"], T.ipps_total(3.0))
        self.assertFalse(Case.objects.get(pk=cid).flags.filter(kind="drg_check", resolved=False).exists())

    def test_hospital_without_price_file(self):
        r = self.upload("B10")
        self.assertEqual(r.data["status"], "no_price_file")
        rep = self.client.get(f"/api/cases/{r.data['id']}/report/").data
        self.assertEqual(rep["summary"][1]["benchmark"], "No insurer on the bill")   # self-pay, no made-up insurer name
        lines = self.client.get(f"/api/cases/{r.data['id']}/lines/").data
        self.assertEqual(lines[0]["medicare"], 110.0)                       # national OPPS: James has no IPPS wage index

    def test_photo_upload_is_priced_and_flagged_for_checking(self):
        photo = ReaderAndPriceTests._photo(self, "B01")
        r = self.client.post("/api/cases/", {"report_for": "plaintiff", "consent": "true", "firm_id": self.firm.id,
                                             "bill": SimpleUploadedFile("bill.jpg", photo, content_type="image/jpeg")}, format="multipart")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "needs_review")
        det = self.client.get(f"/api/cases/{r.data['id']}/").data
        self.assertEqual(det["bill_type"], "UB-04 (OCR)")
        f = det["flags"][0]
        self.assertEqual((f["kind"], f["severity"]), ("low_confidence", "check"))
        self.assertIn("by OCR", f["title"])

    def test_renamed_file_is_refused(self):
        r = self.client.post("/api/cases/", {"report_for": "plaintiff", "consent": "true", "firm_id": self.firm.id,
                                             "bill": SimpleUploadedFile("bill.pdf", b"MZ\x90\x00 not a pdf", content_type="application/pdf")},
                             format="multipart")
        self.assertEqual(r.status_code, 400); self.assertIn("not a real PDF", str(r.data))

    def test_unreadable_bill_goes_to_error(self):
        r = self.client.post("/api/cases/", {"report_for": "plaintiff", "consent": "true", "firm_id": self.firm.id,
                                             "bill": SimpleUploadedFile("scan.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")},
                             format="multipart")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data["status"], "error"); self.assertIn("could not be read", r.data["status_detail"])
