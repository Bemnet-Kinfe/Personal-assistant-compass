import json
from datetime import datetime, timedelta

from django.utils import timezone

from ..models import CalendarEvent, DayPlan, PlanEntry, Task
from ..services import days
from .helpers import SignedInTestCase


class PlanTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.task = Task.objects.create(user=self.user, area=self.area(), title="Read papers", minutes=90)

    def at(self, hour, minute=0, date=None):
        return timezone.make_aware(datetime.combine(date or self.today, datetime.min.time()) + timedelta(hours=hour, minutes=minute))

    def test_add_and_remove_from_a_part_of_the_day(self):
        r = self.hx_post("/plan/add/", {"task": self.task.pk, "date": self.today.isoformat(), "slot": "morning"})
        self.assertEqual(r.status_code, 204)
        entry = PlanEntry.objects.get()
        self.assertEqual((entry.slot, entry.plan.date), ("morning", self.today))
        # Adding the same task to another part of the day moves it.
        self.hx_post("/plan/add/", {"task": self.task.pk, "date": self.today.isoformat(), "slot": "afternoon"})
        self.assertEqual(PlanEntry.objects.get().slot, "afternoon")
        self.hx_post(f"/plan/entry/{entry.pk}/remove/")
        self.assertFalse(PlanEntry.objects.exists())

    def test_bad_slot_is_rejected(self):
        r = self.client.post("/plan/add/", {"task": self.task.pk, "date": self.today.isoformat(), "slot": "midnight"})
        self.assertEqual(r.status_code, 400)

    def test_plan_page_shows_tasks_and_events(self):
        days.plan_task(self.user, self.task, self.today, "morning")
        CalendarEvent.objects.create(user=self.user, google_id="e1", calendar_id="me", is_primary=True,
                                     title="Lab meeting", start=self.at(15), end=self.at(16))
        r = self.client.get("/plan/")
        self.assertContains(r, "Read papers")
        self.assertContains(r, "Lab meeting")
        self.assertContains(r, "1h on calendar")

    def test_top_three_limit(self):
        tasks = [Task.objects.create(user=self.user, area=self.area(), title=f"T{i}") for i in range(4)]
        for t in tasks[:3]:
            self.hx_post("/plan/star/", {"task": t.pk, "date": self.today.isoformat()})
        r = self.hx_post("/plan/star/", {"task": tasks[3].pk, "date": self.today.isoformat()})
        self.assertIn("Top 3 is full", json.loads(r["HX-Trigger"])["compass:toast"])
        self.assertEqual(DayPlan.objects.get().top_tasks.count(), 3)
        self.hx_post("/plan/star/", {"task": tasks[0].pk, "date": self.today.isoformat()})
        self.assertEqual(DayPlan.objects.get().top_tasks.count(), 2)

    def test_picker_puts_deadlines_first(self):
        Task.objects.create(user=self.user, area=self.area(), title="Due today", due_date=self.today)
        r = self.client.get(f"/plan/pick/{self.today.isoformat()}/morning/", HTTP_HX_REQUEST="true")
        html = r.content.decode()
        self.assertLess(html.index("Due today"), html.index("Read papers"))


class SummaryTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()

    def event(self, h1, h2, **kw):
        base = timezone.make_aware(datetime.combine(self.today, datetime.min.time()))
        return CalendarEvent.objects.create(user=self.user, google_id=f"e{h1}", calendar_id="me", title="Busy",
                                            start=base + timedelta(hours=h1), end=base + timedelta(hours=h2), **kw)

    def test_empty_day(self):
        s = days.summarize(self.user, self.today)
        self.assertEqual((s.verdict, s.planned_count, s.used), ("idle", 0, 0))

    def test_events_count_toward_the_part_of_the_day(self):
        self.event(9, 11)
        self.event(11, 13)  # spans morning and midday
        self.event(19, 20, is_free=True)  # marked free: shown but not counted
        s = days.summarize(self.user, self.today)
        self.assertEqual(s.slot("morning").event_minutes, 180)
        self.assertEqual(s.slot("midday").event_minutes, 60)
        self.assertEqual(s.slot("evening").event_minutes, 0)
        self.assertEqual(len(s.slot("evening").events), 1)

    def test_balance_check_flags_problems(self):
        big = Task.objects.create(user=self.user, area=self.area(), title="Huge", minutes=300, energy="deep")
        days.plan_task(self.user, big, self.today, "morning")
        Task.objects.create(user=self.user, area=self.area(), title="Forgotten", due_date=self.today)
        s = days.summarize(self.user, self.today)
        texts = " ".join(t for _, t in s.issues)
        self.assertEqual(s.verdict, "bad")
        self.assertIn("Morning is over by 1h", texts)
        self.assertIn("“Forgotten” is due that day and isn’t planned", texts)
        self.assertIn("No personal time planned", texts)

    def test_balanced_day(self):
        work = Task.objects.create(user=self.user, area=self.area(), title="Essay", minutes=120)
        gym = Task.objects.create(user=self.user, area=self.area("Personal"), title="Gym", minutes=60, energy="easy")
        days.plan_task(self.user, work, self.today, "morning")
        days.plan_task(self.user, gym, self.today, "evening")
        s = days.summarize(self.user, self.today)
        self.assertEqual((s.verdict, s.word), ("good", "Balanced day"))

    def test_fmt_minutes(self):
        self.assertEqual([days.fmt_minutes(m) for m in (45, 60, 90, 150)], ["45m", "1h", "1h 30m", "2h 30m"])
