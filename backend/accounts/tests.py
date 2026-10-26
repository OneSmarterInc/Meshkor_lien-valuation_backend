r"""Sign-in limit tests. Run:  set DB_ENGINE=sqlite && python backend\manage.py test cases accounts"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from cases.models import AuditEntry
from .models import LoginAttempt, Profile


class LoginLimitTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        u = get_user_model().objects.create_user(username="jane@firm.test", email="jane@firm.test", password="right-pw-1")
        Profile.objects.create(user=u, role="reviewer")

    def login(self, password, ip="10.0.0.1", email="jane@firm.test"):
        return self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json", REMOTE_ADDR=ip)

    def test_five_wrong_passwords_block_that_computer_for_that_email(self):
        for _ in range(5):
            self.assertEqual(self.login("wrong").status_code, 401)
        r = self.login("right-pw-1")                                   # even the right password waits now
        self.assertEqual(r.status_code, 429)
        self.assertIn("Try again in 15 minutes", r.data["detail"])
        self.assertEqual(r["Retry-After"], "900")
        self.assertTrue(AuditEntry.objects.filter(action="Sign-in blocked").exists())

    def test_the_owner_on_another_computer_is_not_locked_out(self):
        for _ in range(5):
            self.login("wrong", ip="203.0.113.9")                       # someone else, somewhere else
        self.assertEqual(self.login("right-pw-1", ip="10.0.0.1").status_code, 200)

    def test_a_right_password_clears_the_count(self):
        for _ in range(4):
            self.login("wrong")
        self.assertEqual(self.login("right-pw-1").status_code, 200)
        self.assertEqual(LoginAttempt.objects.filter(email="jane@firm.test", ip="10.0.0.1").count(), 0)
        for _ in range(4):
            self.assertEqual(self.login("wrong").status_code, 401)      # a fresh count: 4 is still below 5

    def test_the_block_ends_after_the_window(self):
        for _ in range(5):
            self.login("wrong")
        LoginAttempt.objects.update(at=timezone.now() - timedelta(minutes=16))
        self.assertEqual(self.login("right-pw-1").status_code, 200)

    def test_one_computer_trying_many_accounts_is_blocked(self):
        for i in range(20):
            self.login("wrong", email=f"user{i}@firm.test", ip="198.51.100.7")
        self.assertEqual(self.login("right-pw-1", ip="198.51.100.7").status_code, 429)
        self.assertEqual(self.login("right-pw-1", ip="10.0.0.1").status_code, 200)   # other computers are fine

    def test_email_is_matched_without_case(self):
        for _ in range(5):
            self.login("wrong", email="JANE@Firm.Test")
        self.assertEqual(self.login("right-pw-1").status_code, 429)
