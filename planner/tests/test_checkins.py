from datetime import date, timedelta

from django.utils import timezone

from ..models import DayPlan, PlanEntry, Task, WeeklyCheckIn
from ..services import days
from ..views.checkins import week_for
from .helpers import SignedInTestCase


class DailyCheckInTests(SignedInTestCase):
    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.tomorrow = self.today + timedelta(days=1)

    def test_page_lists_today_and_unfinished(self):
        done = Task.objects.create(user=self.user, area=self.area(), title="Finished thing", done=True)
        left = Task.objects.create(user=self.user, area=self.area(), title="Unfinished thing")
        days.plan_task(self.user, done, self.today, "morning")
        days.plan_task(self.user, left, self.today, "afternoon")
        r = self.client.get("/check-in/daily/")
        self.assertContains(r, "Finished thing")
        self.assertContains(r, "Move 1 to tomorrow")

    def test_carry_over_moves_only_unfinished_once(self):
        done = Task.objects.create(user=self.user, area=self.area(), title="Done", done=True)
        left = Task.objects.create(user=self.user, area=self.area(), title="Left")
        days.plan_task(self.user, done, self.today, "morning")
        days.plan_task(self.user, left, self.today, "afternoon")
        self.hx_post("/check-in/daily/carry/")
        self.hx_post("/check-in/daily/carry/")
        tomorrow = PlanEntry.objects.filter(plan__date=self.tomorrow)
        self.assertEqual([(e.task.title, e.slot) for e in tomorrow], [("Left", "afternoon")])

    def test_finish_saves_reflection(self):
        self.hx_post("/check-in/daily/finish/", {"reflection": "Good focus in the morning"})
        plan = DayPlan.objects.get(date=self.today)
        self.assertEqual(plan.reflection, "Good focus in the morning")
        self.assertIsNotNone(plan.checked_in_at)
        self.assertContains(self.client.get("/check-in/daily/"), "You finished today’s check-in")

    def test_star_tomorrows_top_three(self):
        t = Task.objects.create(user=self.user, area=self.area(), title="Top thing")
        self.hx_post("/plan/star/", {"task": t.pk, "date": self.tomorrow.isoformat()})
        self.assertEqual(list(DayPlan.objects.get(date=self.tomorrow).top_tasks.all()), [t])


class WeeklyCheckInTests(SignedInTestCase):
    def test_week_for(self):
        self.assertEqual(week_for(date(2026, 11, 11)), date(2026, 11, 9))  # Wednesday -> this Monday
        self.assertEqual(week_for(date(2026, 11, 15)), date(2026, 11, 16))  # Sunday plans next week

    def test_save_goal_then_finish(self):
        self.hx_post("/check-in/weekly/", {"goal": "Finish the lit review", "reflection": ""})
        week = WeeklyCheckIn.objects.get()
        self.assertEqual(week.goal, "Finish the lit review")
        self.assertIsNone(week.completed_at)
        self.hx_post("/check-in/weekly/", {"goal": "Finish the lit review", "reflection": "", "finish": "1"})
        week.refresh_from_db()
        self.assertIsNotNone(week.completed_at)

    def test_page_shows_deadlines_and_overdue(self):
        today = timezone.localdate()
        monday = week_for(today)
        Task.objects.create(user=self.user, area=self.area(), title="Problem set", due_date=monday + timedelta(days=3))
        Task.objects.create(user=self.user, area=self.area(), title="Old essay", due_date=today - timedelta(days=9))
        r = self.client.get("/check-in/weekly/")
        self.assertContains(r, "Problem set")
        self.assertContains(r, "Old essay")

    def test_reschedule_overdue(self):
        today = timezone.localdate()
        t = Task.objects.create(user=self.user, area=self.area(), title="Old", due_date=today - timedelta(days=3))
        new = today + timedelta(days=2)
        self.hx_post(f"/tasks/{t.pk}/reschedule/", {"due_date": new.isoformat()})
        t.refresh_from_db()
        self.assertEqual(t.due_date, new)
