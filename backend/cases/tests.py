r"""API contract tests. Run:  set DB_ENGINE=sqlite && python backend\manage.py test cases accounts
(sqlite keeps the test DB away from PostgreSQL; the code is the same)."""
import os
import tempfile

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from accounts.models import Firm, Profile
from .models import AuditEntry, Case, CaseLine, Flag, Stay

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
TMP = tempfile.mkdtemp()


@override_settings(MESHKOR_FILE_KEY=Fernet.generate_key().decode(), MESHKOR_UPLOAD_DIR=TMP,
                   EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class ContractTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.f1 = Firm.objects.create(name="Smith & Lee LLP", contact_email="ops@smithlee.test")
        cls.f2 = Firm.objects.create(name="Other Firm")
        def mk(email, role, firm=None, name=""):
            u = User.objects.create_user(username=email, email=email, password="pw-12345", first_name=name)
            Profile.objects.create(user=u, role=role, firm=firm)
            return u
        cls.firm_user = mk("jane@smithlee.test", "firm", cls.f1, "Jane")
        cls.other_user = mk("bob@other.test", "firm", cls.f2, "Bob")
        cls.reviewer = mk("rev@meshkor.test", "reviewer", None, "Rev")

    def login(self, email):
        r = self.client.post("/api/auth/login/", {"email": email, "password": "pw-12345"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return r.data

    def upload(self, **extra):
        data = {"matter_ref": "SL-1", "report_for": "plaintiff", "consent": "true",
                "bill": SimpleUploadedFile("bill.pdf", PDF, content_type="application/pdf")}
        data.update(extra)
        return self.client.post("/api/cases/", data, format="multipart")

    # ---- auth
    def test_login_shapes(self):
        d = self.login("jane@smithlee.test")
        self.assertEqual(d["user"]["role"], "firm")
        self.assertEqual(d["user"]["firm"]["name"], "Smith & Lee LLP")
        self.assertEqual(self.client.get("/api/auth/me/").data["email"], "jane@smithlee.test")
        r = self.client.post("/api/auth/refresh/", {"refresh": d["refresh"]}, format="json")
        self.assertEqual(r.status_code, 200); self.assertIn("access", r.data)
        self.assertEqual(self.client.post("/api/auth/logout/", {"refresh": r.data.get("refresh", d["refresh"])}, format="json").status_code, 204)

    def test_wrong_password_401_and_no_token_401(self):
        r = self.client.post("/api/auth/login/", {"email": "jane@smithlee.test", "password": "nope"}, format="json")
        self.assertEqual(r.status_code, 401); self.assertEqual(r.data["detail"], "Wrong email or password.")
        self.assertEqual(self.client.get("/api/cases/").status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer not-a-token")
        self.assertEqual(self.client.get("/api/cases/").status_code, 401)   # not 403: frontend refreshes

    # ---- cases
    def test_upload_list_detail_and_isolation(self):
        self.login("jane@smithlee.test")
        r = self.upload()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["status"], "error"); self.assertTrue(r.data["case_number"].startswith("MK-"))
        cid = r.data["id"]
        case = Case.objects.get(pk=cid)
        f = case.files.get(kind="bill")
        self.assertEqual(f.size_bytes, len(PDF))
        self.assertNotEqual(open(os.path.join(TMP, f.stored_path), "rb").read()[:4], b"%PDF")   # encrypted on disk
        from . import storage
        self.assertEqual(storage.read(f), PDF)
        lst = self.client.get("/api/cases/").data
        self.assertEqual(lst["count"], 1); self.assertIn("results", lst)
        det = self.client.get(f"/api/cases/{cid}/").data
        self.assertEqual(det["flags"], []); self.assertIsNone(det["hospital_match"]); self.assertIsNone(det["stay"])
        self.assertEqual(set(det["totals"]), {"billed", "payer_rate", "median", "cash", "medicare", "cost"})
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lines/").status_code, 403)     # firm: no draft before release
        self.assertEqual(self.client.get(f"/api/cases/{cid}/report/").status_code, 403)
        self.assertEqual(det["status_detail"], "MeshKor is looking at this bill.")                # not the internal reason
        self.assertIn("could not be read", case.status_detail)    # the dummy PDF has no text: pricing stops with a reason (staff see it)
        # another firm: 404, and its list is empty
        self.client.credentials(); self.login("bob@other.test")
        self.assertEqual(self.client.get(f"/api/cases/{cid}/").status_code, 404)
        self.assertEqual(self.client.get("/api/cases/").data["count"], 0)
        self.assertEqual(self.client.get("/api/cases/stats/").status_code, 403)   # firm user, staff endpoint
        self.assertTrue(AuditEntry.objects.filter(action="Bill uploaded", case=case).exists())

    def test_upload_validation(self):
        self.login("jane@smithlee.test")
        self.assertEqual(self.upload(consent="false").status_code, 400)
        r = self.upload(bill=SimpleUploadedFile("bill.exe", b"x", content_type="application/octet-stream"))
        self.assertEqual(r.status_code, 400); self.assertIn("bill", r.data)
        self.client.credentials(); self.login("rev@meshkor.test")
        self.assertEqual(self.upload().status_code, 400)                       # staff must pick a firm
        self.assertEqual(self.upload(firm_id=self.f1.id).status_code, 201)

    def test_staff_flow_review_approve_download_feedback(self):
        self.login("jane@smithlee.test")
        cid = self.upload().data["id"]
        case = Case.objects.get(pk=cid)
        # firm may not download before release
        self.assertEqual(self.client.get(f"/api/cases/{cid}/report.pdf").status_code, 403)
        # pretend the pipeline priced it
        case.hospital_name, case.ccn, case.payer_name, case.billed_total = "OSU Hospitals", "360085", "Anthem", 9647.87
        case.status = "needs_review"; case.totals = {"billed": 9647.87, "payer_rate": 3114.60, "median": 2964.90, "medicare": 1400.43, "cost": 2026.05}
        case.price_file = {"file_name": "osu.csv", "period": "2026-10", "last_updated_on": "2026-07-01", "covers_service_date": True, "sha256": "ab" * 32}
        case.save()
        CaseLine.objects.create(case=case, line_no=1, hcpcs="99285", revenue_code="0450", charge=3403, payer_rate=1452, median=1388,
                                medicare=598.40, medicare_status="priced", medicare_source="OPPS 2026Q3", cost=714.63, status="priced",
                                sources=[{"label": "Hospital price file", "file_name": "osu.csv", "sha256": "ab" * 32}])
        fl = Flag.objects.create(case=case, kind="low_confidence", severity="check", line_no=1, title="Line 1 read with 71 % certainty")
        self.client.credentials(); self.login("rev@meshkor.test")
        s = self.client.get("/api/cases/stats/").data
        self.assertEqual(s["needs_review"], 1); self.assertAlmostEqual(s["billed_open_total"], 9647.87)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lines/").data[0]["payer_rate"], 1452.0)
        r = self.client.post(f"/api/cases/{cid}/approve/", {}, format="json")
        self.assertEqual(r.status_code, 400)                                      # open flag blocks approval
        self.assertEqual(self.client.post(f"/api/cases/{cid}/flags/{fl.id}/resolve/", {"note": "checked"}, format="json").data["resolved"], True)
        self.assertEqual(self.client.post(f"/api/cases/{cid}/return/", {}, format="json").status_code, 400)   # reason required
        rep = self.client.get(f"/api/cases/{cid}/report/").data
        self.assertEqual(rep["summary"][0]["total"], 9647.87); self.assertEqual(rep["summary"][1]["pct_of_billed"], 32)
        pdf = self.client.get(f"/api/cases/{cid}/report.pdf")
        self.assertEqual(pdf.status_code, 200); self.assertEqual(pdf.content[:4], b"%PDF")
        self.assertIn("MK-", pdf["Content-Disposition"])
        r = self.client.post(f"/api/cases/{cid}/approve/", {"note": "ok"}, format="json")
        self.assertEqual(r.status_code, 200); self.assertEqual(r.data["status"], "sent")
        from django.core import mail
        self.assertEqual(len(mail.outbox), 1)
        # firm downloads and gives feedback
        self.client.credentials(); self.login("jane@smithlee.test")
        csv = self.client.get(f"/api/cases/{cid}/report.csv")
        self.assertEqual(csv.status_code, 200); self.assertIn(b"99285", csv.content)
        r = self.client.post(f"/api/cases/{cid}/feedback/", {"outcome": "reduced", "pricing_model": "per_report", "price_per_report": 250, "comment": ""}, format="json")
        self.assertEqual(r.status_code, 201)
        r = self.client.post(f"/api/cases/{cid}/feedback/", {"outcome": "no_change", "pricing_model": None, "price_per_report": None}, format="json")
        self.assertEqual(r.status_code, 201, r.content)                                          # blank dropdown is not a 500
        self.assertEqual(self.client.get(f"/api/cases/{cid}/lines/").status_code, 200)         # released: the firm sees the lines
        self.client.credentials(); self.login("rev@meshkor.test")
        a = self.client.get(f"/api/audit/?case={cid}").data
        self.assertTrue(any(e["action"] == "Report approved and sent" for e in a["results"]))
        self.assertEqual(self.client.get("/api/firms/").data[0]["name"], "Other Firm")

    def test_drg_confirm_and_data_sources(self):
        self.login("rev@meshkor.test")
        cid = self.upload(firm_id=self.f1.id).data["id"]
        case = Case.objects.get(pk=cid); case.setting = "inpatient"; case.status = "needs_review"; case.save()
        Stay.objects.create(case=case, ms_drg="481", drg_title="Hip and femur procedures except major joint with CC", los_days=3)
        self.assertEqual(self.client.get(f"/api/cases/{cid}/").data["stay"]["ms_drg"], "481")
        r = self.client.post(f"/api/cases/{cid}/drg/confirm/", {"ms_drg": "481"}, format="json")
        self.assertTrue(r.data["drg_confirmed"])
        d = self.client.get("/api/data-sources/").data
        self.assertIn("reference", d); self.assertIn("price_files", d)
        # verify comes from the VerifyRun table, or from data/reports/verify_latest.md when no run is recorded
        self.assertTrue(d["verify"] is None or {"pass", "fail", "run_at"} <= set(d["verify"]))
        self.assertTrue(all(x["status"] in ("ok", "partial", "missing") for x in d["reference"]))
