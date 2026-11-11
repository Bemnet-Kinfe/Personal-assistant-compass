from unittest import mock

from django.test import TestCase, override_settings

from ..adapters import AccountAdapter, email_allowed
from ..models import Area
from .helpers import SignedInTestCase, make_user


class HealthTests(TestCase):
    def test_healthy(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"status": "ok"})

    def test_database_down_reports_503(self):
        with mock.patch("planner.views.common.connection") as conn:
            conn.cursor.side_effect = Exception("db gone")
            r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 503)


class AccessTests(TestCase):
    def test_pages_need_sign_in(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_login_page_renders(self):
        r = self.client.get("/accounts/login/")
        self.assertContains(r, "Sign in")
        self.assertNotContains(r, "Continue with Google")  # Google isn't configured in tests

    def test_password_sign_in(self):
        make_user("me@example.com")
        r = self.client.post("/accounts/login/", {"login": "me@example.com", "password": "a-strong-test-pass-91"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(SIGNUP_OPEN=False)
    def test_signup_closed_by_default(self):
        r = self.client.post("/accounts/signup/", {"email": "new@example.com", "password1": "x9!longpass", "password2": "x9!longpass"})
        self.assertFalse(Area.objects.filter(user__email="new@example.com").exists())
        self.assertIn(r.status_code, (200, 302))

    @override_settings(SIGNUP_OPEN=True, ALLOWED_EMAILS=["friend@example.com"])
    def test_signup_open_only_for_allowed_emails(self):
        self.client.post("/accounts/signup/", {"email": "stranger@example.com", "password1": "x9!longpass", "password2": "x9!longpass"})
        self.assertFalse(Area.objects.filter(user__email="stranger@example.com").exists())
        self.client.post("/accounts/signup/", {"email": "friend@example.com", "password1": "x9!longpass", "password2": "x9!longpass"})
        self.assertTrue(Area.objects.filter(user__email="friend@example.com").exists())

    @override_settings(ALLOWED_EMAILS=[])
    def test_no_allowlist_means_anyone(self):
        self.assertTrue(email_allowed("anyone@example.com"))
        self.assertFalse(AccountAdapter().is_open_for_signup(None))


class NewUserTests(TestCase):
    def test_new_users_get_default_areas(self):
        user = make_user()
        names = list(user.areas.values_list("name", flat=True))
        self.assertEqual(names[:2], ["Class", "TA work"])
        self.assertTrue(user.areas.get(name="Personal").is_personal)

    def test_default_areas_are_not_duplicated(self):
        user = make_user()
        Area.create_defaults(user)
        self.assertEqual(user.areas.count(), 8)


class HomeTests(SignedInTestCase):
    def test_home_greets_by_name(self):
        r = self.client.get("/")
        self.assertContains(r, "Bemnet")
        self.assertContains(r, "Welcome to Compass")
