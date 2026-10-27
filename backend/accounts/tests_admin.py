r"""Admin pages: firms, users, payer names, own password. Run:  set DB_ENGINE=sqlite && python backend\manage.py test cases accounts"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from cases.models import AuditEntry, Case, PayerName
from .models import Firm, Profile

User = get_user_model()


def make(email, role, firm=None, pw="Right-pw-123"):
    u = User.objects.create_user(username=email, email=email, password=pw)
    Profile.objects.create(user=u, role=role, firm=firm)
    return u


class AdminApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.firm = Firm.objects.create(name="Smith & Lee LLP")
        cls.admin = make("boss@mk.test", "admin")
        cls.rev = make("rev@mk.test", "reviewer")
        cls.lawyer = make("jane@firm.test", "firm", cls.firm)

    def as_(self, email, pw="Right-pw-123"):
        self.client.credentials()
        r = self.client.post("/api/auth/login/", {"email": email, "password": pw}, format="json")
        if r.status_code == 200:
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
        return r

    # ---- who may use the pages
    def test_only_an_admin_gets_in(self):
        for who, code in (("rev@mk.test", 403), ("jane@firm.test", 403), ("boss@mk.test", 200)):
            self.as_(who)
            for url in ("/api/admin/firms/", "/api/admin/users/", "/api/admin/payer-names/"):
                self.assertEqual(self.client.get(url).status_code, code, (who, url))

    def test_a_reviewer_still_reviews(self):
        self.as_("rev@mk.test")
        self.assertEqual(self.client.get("/api/cases/").status_code, 200)
        self.as_("boss@mk.test")
        self.assertEqual(self.client.get("/api/cases/").status_code, 200)          # an admin reviews too (option 1)

    # ---- firms
    def test_add_rename_and_turn_off_a_firm(self):
        self.as_("boss@mk.test")
        r = self.client.post("/api/admin/firms/", {"name": "  Doe   Law  ", "contact_email": "ops@doe.test"}, format="json")
        self.assertEqual((r.status_code, r.data["name"]), (201, "Doe Law"))
        self.assertEqual(self.client.post("/api/admin/firms/", {"name": "doe law"}, format="json").status_code, 400)
        r = self.client.patch(f"/api/admin/firms/{self.firm.id}/", {"active": False}, format="json")
        self.assertFalse(r.data["active"])
        self.assertTrue(AuditEntry.objects.filter(action="Firm changed").exists())
        self.assertNotIn(self.firm.id, [f["id"] for f in self.client.get("/api/firms/").data])   # not in the upload list
        r = self.as_("jane@firm.test")
        self.assertEqual(r.status_code, 403)
        self.assertIn("turned off", r.data["detail"])

    # ---- users
    def test_add_a_user_who_must_change_the_password(self):
        self.as_("boss@mk.test")
        r = self.client.post("/api/admin/users/", {"email": "Paul@Firm.test", "name": "Paul Doe", "role": "firm", "firm_id": self.firm.id}, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        pw = r.data["temporary_password"]
        self.assertEqual((r.data["email"], r.data["name"], r.data["firm"]["id"]), ("paul@firm.test", "Paul Doe", self.firm.id))
        self.assertNotIn("temporary_password", self.client.get("/api/admin/users/").data[0])
        r = self.as_("paul@firm.test", pw)
        self.assertTrue(r.data["user"]["must_change_password"])
        r = self.client.post("/api/auth/password/", {"current_password": pw, "new_password": "short"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/auth/password/", {"current_password": pw, "new_password": "A-much-better-pw-42"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["must_change_password"])
        self.assertEqual(self.as_("paul@firm.test", "A-much-better-pw-42").status_code, 200)

    def test_user_rules(self):
        self.as_("boss@mk.test")
        bad = [({"email": "x@y.test", "role": "firm"}, "firm_id"),                    # a firm user needs a firm
               ({"email": "jane@firm.test", "role": "reviewer"}, "email")]            # email in use
        for body, key in bad:
            r = self.client.post("/api/admin/users/", body, format="json")
            self.assertEqual(r.status_code, 400); self.assertIn(key, r.data)
        r = self.client.post("/api/admin/users/", {"email": "new@mk.test", "role": "reviewer", "firm_id": self.firm.id}, format="json")
        self.assertIsNone(r.data["firm"])                                                # staff belong to no firm
        r = self.client.patch(f"/api/admin/users/{self.admin.id}/", {"role": "reviewer"}, format="json")
        self.assertEqual(r.status_code, 400)                                             # not your own role
        r = self.client.patch(f"/api/admin/users/{self.admin.id}/", {"active": False}, format="json")
        self.assertEqual(r.status_code, 400)

    def test_the_last_admin_stays(self):
        other = make("boss2@mk.test", "admin")
        self.as_("boss2@mk.test")
        self.assertEqual(self.client.patch(f"/api/admin/users/{self.admin.id}/", {"role": "reviewer"}, format="json").status_code, 200)
        self.as_("boss@mk.test")
        self.assertEqual(self.client.get("/api/admin/users/").status_code, 403)          # boss is a reviewer now
        Profile.objects.filter(user=self.admin).update(role="admin")
        self.as_("boss@mk.test")
        self.client.patch(f"/api/admin/users/{other.id}/", {"active": False}, format="json")
        r = self.client.patch(f"/api/admin/users/{other.id}/", {"active": True, "role": "admin"}, format="json")
        self.assertEqual(r.status_code, 200)

    def test_turn_off_and_reset(self):
        self.as_("jane@firm.test")
        refresh = self.client.post("/api/auth/login/", {"email": "jane@firm.test", "password": "Right-pw-123"}, format="json").data["refresh"]
        self.as_("boss@mk.test")
        r = self.client.post(f"/api/admin/users/{self.lawyer.id}/reset-password/")
        pw = r.data["temporary_password"]
        self.assertEqual(self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json").status_code, 401)   # signed out
        self.assertEqual(self.as_("jane@firm.test").status_code, 401)                    # old password gone
        self.assertEqual(self.as_("jane@firm.test", pw).status_code, 200)
        self.as_("boss@mk.test")
        self.client.patch(f"/api/admin/users/{self.lawyer.id}/", {"active": False}, format="json")
        self.assertEqual(self.as_("jane@firm.test", pw).status_code, 401)
        self.assertTrue(AuditEntry.objects.filter(action="User changed", detail__contains="turned off").exists())

    # ---- payer names
    def test_payer_names(self):
        Case.objects.create(case_number="MK-2026-0901", firm=self.firm, report_for="plaintiff", payer_name="Acme Benefit Admin",
                            payer_group="Other", status="needs_review")
        self.as_("boss@mk.test")
        d = self.client.get("/api/admin/payer-names/").data
        self.assertIn("PPO network / TPA", d["groups"])
        self.assertEqual(d["unknown"], [{"payer_name": "Acme Benefit Admin", "cases": 1, "open": 1}])
        r = self.client.post("/api/admin/payer-names/", {"name": "Acme Benefit Admin", "group": "Made up"}, format="json")
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/admin/payer-names/", {"name": "Acme  Benefit Admin", "group": "PPO network / TPA"}, format="json")
        self.assertEqual((r.status_code, r.data["open_cases"]), (201, 1))
        from pipeline.ref.hospital_mrf import payer_group, set_extra_payer_names
        set_extra_payer_names(PayerName.objects.values_list("name", "group"))
        self.assertEqual(payer_group("ACME benefit admin of Ohio", None), "PPO network / TPA")
        self.assertEqual(payer_group("Acme Benefit Administrators", None), "Other")      # whole words only
        set_extra_payer_names([])
        r = self.client.post("/api/admin/payer-names/reprice/", {"name": "acme benefit admin"}, format="json")
        self.assertEqual([c["case_number"] for c in r.data["repriced"]], ["MK-2026-0901"])   # this test case has no bill file
        self.assertTrue(AuditEntry.objects.filter(action="Cases priced again").exists())
        n = PayerName.objects.get()
        self.assertEqual(self.client.delete(f"/api/admin/payer-names/{n.id}/").status_code, 204)
