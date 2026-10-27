r"""Two-step sign-in (Google Authenticator). Run:  python backend\manage.py test accounts"""
import time
from unittest import mock

import pyotp
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from cases.models import AuditEntry
from .models import Firm, Profile, TwoFactor

User = get_user_model()


def make(email, role, firm=None, pw="Right-pw-123"):
    u = User.objects.create_user(username=email, email=email, password=pw)
    Profile.objects.create(user=u, role=role, firm=firm)
    return u


@override_settings(MESHKOR_MFA_REQUIRED=True)
class MfaTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.firm = Firm.objects.create(name="Smith & Lee LLP")
        cls.lawyer = make("jane@firm.test", "firm", cls.firm)
        cls.rev = make("rev@mk.test", "reviewer")
        cls.admin = make("boss@mk.test", "admin")

    def password(self, email, pw="Right-pw-123"):
        return self.client.post("/api/auth/login/", {"email": email, "password": pw}, format="json")

    def enroll(self, email):
        """First sign-in: password, QR, first code. Returns (secret, recovery codes)."""
        r = self.password(email)
        self.assertEqual(r.data["mfa"], "setup")
        self.assertNotIn("access", r.data)                                     # not signed in yet
        s = self.client.post("/api/auth/mfa/setup/", {"mfa_token": r.data["mfa_token"]}, format="json")
        self.assertTrue(s.data["qr_svg"].startswith("data:image/svg+xml"))
        self.assertIn("otpauth://totp/", s.data["otpauth_uri"])
        self.assertIn("issuer=MeshKor", s.data["otpauth_uri"])
        secret = s.data["secret"]
        c = self.client.post("/api/auth/mfa/confirm/", {"mfa_token": r.data["mfa_token"], "code": pyotp.TOTP(secret).now()}, format="json")
        self.assertEqual(c.status_code, 200, c.data)
        self.assertIn("access", c.data)
        self.assertEqual(len(c.data["recovery_codes"]), 10)
        return secret, c.data["recovery_codes"]

    def test_every_role_must_set_up_2fa(self):
        for email in ("jane@firm.test", "rev@mk.test", "boss@mk.test"):
            self.enroll(email)
        self.assertEqual(TwoFactor.objects.filter(confirmed_at__isnull=False).count(), 3)
        self.assertEqual(AuditEntry.objects.filter(action="Two-step sign-in set up").count(), 3)

    def test_the_secret_is_stored_encrypted(self):
        secret, _ = self.enroll("rev@mk.test")
        tf = TwoFactor.objects.get(user=self.rev)
        self.assertNotIn(secret, tf.secret_enc)
        self.assertFalse(any(len(h) != 64 for h in tf.recovery_hashes))             # hashes only

    def test_next_sign_in_asks_for_the_code(self):
        secret, _ = self.enroll("jane@firm.test")
        r = self.password("jane@firm.test")
        self.assertEqual(r.data["mfa"], "verify")
        with mock.patch("time.time", return_value=time.time() + 60):               # a new 30-second code
            code = pyotp.TOTP(secret).at(time.time())          # time.time() is 60 s ahead here
            v = self.client.post("/api/auth/mfa/verify/", {"mfa_token": r.data["mfa_token"], "code": code}, format="json")
            self.assertEqual(v.status_code, 200, v.data)
            self.assertEqual(v.data["user"]["email"], "jane@firm.test")
            r2 = self.password("jane@firm.test")                                    # the same code again: refused
            v2 = self.client.post("/api/auth/mfa/verify/", {"mfa_token": r2.data["mfa_token"], "code": code}, format="json")
            self.assertEqual(v2.status_code, 400)

    def test_wrong_codes_are_limited(self):
        self.enroll("rev@mk.test")
        for _ in range(5):
            tok = self.password("rev@mk.test").data["mfa_token"]                    # the right password ...
            self.assertEqual(self.client.post("/api/auth/mfa/verify/", {"mfa_token": tok, "code": "000000"}, format="json").status_code, 400)
        r = self.password("rev@mk.test")                                            # ... does not clear the count
        self.assertEqual(r.status_code, 429)

    def test_a_recovery_code_works_once(self):
        _, codes = self.enroll("boss@mk.test")
        tok = self.password("boss@mk.test").data["mfa_token"]
        v = self.client.post("/api/auth/mfa/verify/", {"mfa_token": tok, "code": codes[0].upper()}, format="json")
        self.assertEqual((v.status_code, v.data["recovery_codes_left"]), (200, 9))
        tok = self.password("boss@mk.test").data["mfa_token"]
        self.assertEqual(self.client.post("/api/auth/mfa/verify/", {"mfa_token": tok, "code": codes[0]}, format="json").status_code, 400)

    def test_tokens_cannot_skip_a_step(self):
        self.enroll("rev@mk.test")
        r = self.password("rev@mk.test")
        bad = [("/api/auth/mfa/verify/", "nonsense"), ("/api/auth/mfa/setup/", r.data["mfa_token"])]   # forged, or the wrong step
        self.assertEqual(self.client.post(bad[0][0], {"mfa_token": bad[0][1], "code": "123456"}, format="json").status_code, 401)
        self.assertEqual(self.client.post(bad[1][0], {"mfa_token": bad[1][1]}, format="json").status_code, 401)
        self.assertEqual(self.password("rev@mk.test", "wrong").status_code, 401)  # still needs the password first

    def test_a_password_change_ends_a_half_done_sign_in(self):
        r = self.password("jane@firm.test")
        self.lawyer.set_password("Other-pw-456"); self.lawyer.save()
        s = self.client.post("/api/auth/mfa/setup/", {"mfa_token": r.data["mfa_token"]}, format="json")
        self.assertEqual(s.status_code, 401)

    def test_admin_resets_a_lost_phone(self):
        self.enroll("jane@firm.test")
        _, _ = self.enroll("boss@mk.test")
        tok = self.password("boss@mk.test").data["mfa_token"]
        tf = TwoFactor.objects.get(user=self.admin)
        from .mfa import secret_of
        with mock.patch("time.time", return_value=time.time() + 60):
            v = self.client.post("/api/auth/mfa/verify/", {"mfa_token": tok, "code": pyotp.TOTP(secret_of(tf)).at(time.time())}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {v.data['access']}")
        users = {u["email"]: u for u in self.client.get("/api/admin/users/").data}
        self.assertTrue(users["jane@firm.test"]["mfa_enabled"])
        self.assertIsNotNone(users["jane@firm.test"]["last_login"])              # set by a full sign-in
        r = self.client.post(f"/api/admin/users/{self.lawyer.id}/reset-2fa/")
        self.assertEqual((r.status_code, r.data["mfa_enabled"]), (200, False))
        self.assertEqual(self.client.post(f"/api/admin/users/{self.admin.id}/reset-2fa/").status_code, 400)   # not your own
        self.client.credentials()
        self.assertEqual(self.password("jane@firm.test").data["mfa"], "setup")    # sets it up again
        self.assertTrue(AuditEntry.objects.filter(action="Two-step sign-in reset").exists())

    def test_new_recovery_codes_need_a_current_code(self):
        secret, old = self.enroll("rev@mk.test")
        tok = self.password("rev@mk.test").data["mfa_token"]
        with mock.patch("time.time", return_value=time.time() + 60):
            v = self.client.post("/api/auth/mfa/verify/", {"mfa_token": tok, "code": pyotp.TOTP(secret).at(time.time())}, format="json")
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {v.data['access']}")
        st = self.client.get("/api/auth/mfa/").data
        self.assertEqual((st["enabled"], st["recovery_codes_left"]), (True, 10))
        self.assertEqual(self.client.post("/api/auth/mfa/recovery-codes/", {"code": "000000"}, format="json").status_code, 400)
        with mock.patch("time.time", return_value=time.time() + 120):
            r = self.client.post("/api/auth/mfa/recovery-codes/", {"code": pyotp.TOTP(secret).at(time.time())}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(set(r.data["recovery_codes"]), set(old))
