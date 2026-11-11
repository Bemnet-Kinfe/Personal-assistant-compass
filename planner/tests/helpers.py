import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

User = get_user_model()
HTMX = {"HTTP_HX_REQUEST": "true"}


def make_user(email="me@example.com", **extra):
    return User.objects.create_user(username=email, email=email, password="a-strong-test-pass-91", **extra)


def fake_response(status=200, body=None):
    """A stand-in for requests.Response."""
    body = body if body is not None else {}
    r = mock.Mock(status_code=status, content=b"x", text=json.dumps(body))
    r.json.return_value = body
    return r


@override_settings(OPENROUTER_API_KEY="", GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
class SignedInTestCase(TestCase):
    def setUp(self):
        self.user = make_user(first_name="Bemnet")
        self.client.force_login(self.user)

    def area(self, name="Class"):
        return self.user.areas.get(name=name)

    def hx_post(self, url, data=None):
        return self.client.post(url, data or {}, **HTMX)
