import json
from datetime import timedelta

from django.utils import timezone

from ..models import Area, Task
from .helpers import SignedInTestCase, make_user


class TaskTests(SignedInTestCase):
    def form(self, **kw):
        data = {"title": "Grade problem set 4", "area": self.area("TA work").pk, "due_date": "", "minutes": 120,
                "priority": "high", "energy": "deep", "notes": ""}
        data.update(kw)
        return data

    def test_add_task_with_plain_form(self):
        r = self.client.post("/tasks/new/", self.form())
        self.assertRedirects(r, "/tasks/", fetch_redirect_response=False)
        t = Task.objects.get()
        self.assertEqual((t.title, t.area.name, t.minutes, t.user), ("Grade problem set 4", "TA work", 120, self.user))

    def test_add_task_with_htmx_refreshes_page(self):
        r = self.hx_post("/tasks/new/", self.form())
        self.assertEqual(r.status_code, 204)
        trigger = json.loads(r["HX-Trigger"])
        self.assertTrue(trigger["compass:changed"])
        self.assertEqual(trigger["compass:toast"], "Added")

    def test_invalid_task_shows_errors_in_modal(self):
        r = self.hx_post("/tasks/new/", self.form(title="", minutes=0))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "This field is required")
        self.assertFalse(Task.objects.exists())

    def test_cannot_use_another_users_area(self):
        other = make_user("other@example.com")
        r = self.client.post("/tasks/new/", self.form(area=other.areas.first().pk))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Task.objects.exists())

    def test_edit_toggle_delete(self):
        t = Task.objects.create(user=self.user, area=self.area(), title="Read")
        self.client.post(f"/tasks/{t.pk}/", self.form(title="Read two papers", area=t.area_id))
        t.refresh_from_db()
        self.assertEqual(t.title, "Read two papers")
        self.hx_post(f"/tasks/{t.pk}/toggle/")
        t.refresh_from_db()
        self.assertTrue(t.done)
        self.assertIsNotNone(t.done_at)
        self.hx_post(f"/tasks/{t.pk}/toggle/")
        t.refresh_from_db()
        self.assertFalse(t.done)
        self.hx_post(f"/tasks/{t.pk}/delete/")
        self.assertFalse(Task.objects.exists())

    def test_other_users_tasks_are_off_limits(self):
        other = make_user("other@example.com")
        t = Task.objects.create(user=other, area=other.areas.first(), title="Theirs")
        self.assertEqual(self.client.get(f"/tasks/{t.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/tasks/{t.pk}/toggle/").status_code, 404)
        self.assertEqual(self.client.post(f"/tasks/{t.pk}/delete/").status_code, 404)

    def test_task_list_filters_and_search(self):
        Task.objects.create(user=self.user, area=self.area("Class"), title="Seminar reading")
        Task.objects.create(user=self.user, area=self.area("Jobs"), title="Follow up with recruiter")
        Task.objects.create(user=self.user, area=self.area("Jobs"), title="Old application", done=True)
        jobs = self.area("Jobs")
        r = self.client.get(f"/tasks/?area={jobs.pk}")
        self.assertContains(r, "Follow up with recruiter")
        self.assertNotContains(r, "Seminar reading")
        self.assertNotContains(r, "Old application")
        self.assertContains(self.client.get(f"/tasks/?area={jobs.pk}&done=1"), "Old application")
        r = self.client.get("/tasks/?q=seminar")
        self.assertContains(r, "Seminar reading")
        self.assertNotContains(r, "recruiter")

    def test_overdue_and_due_today_show_on_home(self):
        today = timezone.localdate()
        Task.objects.create(user=self.user, area=self.area(), title="Late essay", due_date=today - timedelta(days=1))
        Task.objects.create(user=self.user, area=self.area(), title="Lab report", due_date=today + timedelta(days=2))
        r = self.client.get("/")
        self.assertContains(r, "Late essay")
        self.assertContains(r, "Overdue")
        self.assertContains(r, "Lab report")


class AreaTests(SignedInTestCase):
    def test_add_rename_and_delete_area(self):
        self.client.post("/settings/areas/", {"name": "Research", "color": "teal"})
        a = Area.objects.get(user=self.user, name="Research")
        self.client.post(f"/settings/areas/{a.pk}/", {"name": "Thesis", "color": "green", "is_personal": "on"})
        a.refresh_from_db()
        self.assertEqual((a.name, a.color, a.is_personal), ("Thesis", "green", True))
        self.client.post(f"/settings/areas/{a.pk}/delete/")
        self.assertFalse(Area.objects.filter(pk=a.pk).exists())

    def test_duplicate_area_name_is_rejected(self):
        r = self.hx_post("/settings/areas/", {"name": "class", "color": "blue"})
        self.assertIn("already have an area", json.loads(r["HX-Trigger"])["compass:toast"])
        self.assertEqual(self.user.areas.filter(name__iexact="class").count(), 1)

    def test_area_with_tasks_cannot_be_deleted(self):
        a = self.area()
        Task.objects.create(user=self.user, area=a, title="Keep me")
        self.client.post(f"/settings/areas/{a.pk}/delete/")
        self.assertTrue(Area.objects.filter(pk=a.pk).exists())

    def test_settings_page(self):
        self.assertContains(self.client.get("/settings/"), "Lab work")
