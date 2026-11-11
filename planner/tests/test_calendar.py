"""Google Calendar import. `requests` is mocked; nothing reaches Google."""
from datetime import datetime, timedelta
from unittest import mock

from allauth.socialaccount.models import SocialAccount, SocialToken
from django.test import override_settings
from django.utils import timezone

from ..models import CalendarEvent, CalendarSync, Task
from ..services import gcal
from .helpers import SignedInTestCase, fake_response

CAL_LIST = {"items": [
    {"id": "me@example.com", "summary": "me@example.com", "primary": True, "selected": True},
    {"id": "canvas@import.calendar.google.com", "summary": "Canvas", "selected": True},
    {"id": "en.indian#holiday@group.v.calendar.google.com", "summary": "Holidays in India", "selected": True},
    {"id": "en-gb.indian#holiday@group.v.calendar.google.com", "summary": "Holidays in India", "selected": True},
    {"id": "hidden@group.calendar.google.com", "summary": "Hidden", "selected": False},
]}


def iso(dt):
    return dt.isoformat()


@override_settings(GOOGLE_CLIENT_ID="cid", GOOGLE_CLIENT_SECRET="secret", CALENDAR_SYNC_MINUTES=10)
class CalendarTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        base = timezone.make_aware(datetime.combine(self.today, datetime.min.time()))
        self.events_by_cal = {
            "me@example.com": {"items": [
                {"id": "lab", "summary": "Lab meeting", "start": {"dateTime": iso(base + timedelta(hours=15))},
                 "end": {"dateTime": iso(base + timedelta(hours=16))}, "htmlLink": "https://calendar.google.com/x"},
                {"id": "gone", "status": "cancelled", "start": {}, "end": {}},
                {"id": "nope", "summary": "Declined", "attendees": [{"self": True, "responseStatus": "declined"}],
                 "start": {"dateTime": iso(base + timedelta(hours=9))}, "end": {"dateTime": iso(base + timedelta(hours=10))}},
            ]},
            "canvas@import.calendar.google.com": {"items": [
                {"id": "ps4", "summary": "PS4 due", "start": {"date": self.today.isoformat()},
                 "end": {"date": (self.today + timedelta(days=1)).isoformat()}},
            ]},
            "en.indian#holiday@group.v.calendar.google.com": {"items": []},
        }

    def connect(self, expires_in=3600, refresh="refresh-token"):
        acct = SocialAccount.objects.create(user=self.user, provider="google", uid="g-123")
        return SocialToken.objects.create(account=acct, token="access", token_secret=refresh,
                                          expires_at=timezone.now() + timedelta(seconds=expires_in))

    def google(self, method, url, **kw):
        if "calendarList" in url:
            return fake_response(body=CAL_LIST)
        for cal_id, body in self.events_by_cal.items():
            if gcal.quote(cal_id, safe="") in url:
                return fake_response(body=body)
        return fake_response(404)

    @mock.patch("planner.services.gcal.requests.request")
    def test_sync_copies_visible_calendars(self, req):
        self.connect()
        req.side_effect = self.google
        n = gcal.sync(self.user, self.today, days=7)
        self.assertEqual(n, 2)
        lab = CalendarEvent.objects.get(google_id="lab")
        self.assertTrue(lab.is_primary)
        ps4 = CalendarEvent.objects.get(google_id="ps4")
        self.assertEqual((ps4.calendar_name, ps4.all_day_date), ("Canvas", self.today))
        # Hidden calendar skipped and the duplicate holiday calendar fetched once: 3 event requests.
        self.assertEqual(sum(1 for c in req.call_args_list if "/events" in c.args[1]), 3)
        self.assertIsNotNone(CalendarSync.objects.get(user=self.user).synced_at)

    @mock.patch("planner.services.gcal.requests.request")
    def test_resync_removes_deleted_events(self, req):
        self.connect()
        req.side_effect = self.google
        gcal.sync(self.user, self.today)
        self.events_by_cal["me@example.com"]["items"] = []
        gcal.sync(self.user, self.today)
        self.assertFalse(CalendarEvent.objects.filter(google_id="lab").exists())
        self.assertTrue(CalendarEvent.objects.filter(google_id="ps4").exists())

    @mock.patch("planner.services.gcal.requests.post")
    @mock.patch("planner.services.gcal.requests.request")
    def test_expired_token_is_refreshed(self, req, post):
        tok = self.connect(expires_in=-30)
        post.return_value = fake_response(body={"access_token": "fresh", "expires_in": 3600})
        req.side_effect = self.google
        gcal.sync(self.user, self.today)
        tok.refresh_from_db()
        self.assertEqual(tok.token, "fresh")
        self.assertEqual(req.call_args.kwargs["headers"]["Authorization"], "Bearer fresh")

    @mock.patch("planner.services.gcal.requests.post", return_value=fake_response(400))
    def test_revoked_access_asks_to_reconnect(self, post):
        self.connect(expires_in=-30)
        with self.assertRaises(gcal.CalendarError) as e:
            gcal.sync(self.user, self.today)
        self.assertEqual(e.exception.code, "reconnect")
        self.assertEqual(CalendarSync.objects.get(user=self.user).error_code, "reconnect")

    @mock.patch("planner.services.gcal.requests.request", side_effect=gcal.requests.ConnectionError("down"))
    def test_google_outage_never_breaks_the_page(self, req):
        self.connect()
        r = self.client.get("/plan/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Google Calendar didn’t respond")

    @mock.patch("planner.services.gcal.requests.request")
    def test_fresh_copy_is_not_refetched(self, req):
        self.connect()
        req.side_effect = self.google
        self.client.get("/plan/")
        calls = req.call_count
        self.client.get("/plan/")
        self.assertEqual(req.call_count, calls)

    @mock.patch("planner.services.gcal.requests.request")
    def test_events_show_on_plan_and_home(self, req):
        self.connect()
        req.side_effect = self.google
        r = self.client.get("/plan/")
        self.assertContains(r, "Lab meeting")
        self.assertContains(r, "Canvas · PS4 due")

    def test_not_connected(self):
        self.assertContains(self.client.get("/plan/"), "Connect Google Calendar")
        self.assertContains(self.client.get("/settings/"), "Not connected")

    @mock.patch("planner.services.gcal.requests.request")
    def test_time_block_uses_area_color(self, req):
        self.connect()
        task = Task.objects.create(user=self.user, area=self.area("TA work"), title="Grade psets", minutes=120)
        req.return_value = fake_response(body={"id": "blk", "htmlLink": "https://calendar.google.com/blk"})
        ev = gcal.create_block(self.user, task, self.today, 14 * 60, 120)
        body = req.call_args.kwargs["json"]
        self.assertEqual(body["colorId"], "3")  # TA work is violet -> Google "Grape"
        self.assertEqual(body["extendedProperties"]["private"]["compass_task"], str(task.pk))
        self.assertEqual((ev.task, ev.area), (task, task.area))
        self.assertEqual(timezone.localtime(ev.start).hour, 14)

    @mock.patch("planner.services.gcal.requests.request")
    def test_sync_now_button(self, req):
        self.connect()
        req.side_effect = self.google
        r = self.hx_post("/settings/calendar/sync/")
        self.assertEqual(r.status_code, 204)
        self.assertIn("2 events", r["HX-Trigger"])
