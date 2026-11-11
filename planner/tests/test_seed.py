import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from ..models import Area, PlanEntry, Task

User = get_user_model()


class SeedTests(TestCase):
    env = {"DEMO_EMAIL": "demo@compass.app", "DEMO_PASSWORD": "demo-pass-123", "OWNER_EMAIL": "Me@Example.com"}

    def seed(self):
        with mock.patch.dict(os.environ, self.env):
            call_command("seed", stdout=StringIO())

    def test_seed_is_safe_to_run_twice(self):
        self.seed()
        self.seed()
        demo = User.objects.get(email="demo@compass.app")
        self.assertEqual(Task.objects.filter(user=demo).count(), 9)
        self.assertEqual(Area.objects.filter(user=demo).count(), 8)
        self.assertEqual(PlanEntry.objects.filter(plan__user=demo).count(), 4)
        self.assertEqual(User.objects.count(), 2)

    def test_demo_account_can_sign_in(self):
        self.seed()
        r = self.client.post("/accounts/login/", {"login": "demo@compass.app", "password": "demo-pass-123"})
        self.assertEqual(r.status_code, 302)
        self.assertContains(self.client.get("/"), "Read two papers for seminar")

    def test_owner_is_admin_without_example_data(self):
        self.seed()
        owner = User.objects.get(email="me@example.com")
        self.assertTrue(owner.is_superuser)
        self.assertFalse(owner.has_usable_password())
        self.assertFalse(Task.objects.filter(user=owner).exists())

    def test_password_required_in_production(self):
        with mock.patch.dict(os.environ, {"DEMO_PASSWORD": ""}), self.settings(DEBUG=False):
            with self.assertRaises(CommandError):
                call_command("seed", stdout=StringIO())
