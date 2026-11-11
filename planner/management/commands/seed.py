"""Create the demo account (and optionally your own account) with example data.

Safe to run any number of times: it updates what exists instead of duplicating it.

    python manage.py seed

Environment variables:
    DEMO_EMAIL / DEMO_PASSWORD    the demo account (password required outside DEBUG)
    OWNER_EMAIL / OWNER_PASSWORD  optional: your own account, created as an admin, with no example data
"""
import os
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from ...models import Area, DayPlan, PlanEntry, Task, WeeklyCheckIn

User = get_user_model()

# title, area, due in days (None = no date), minutes, priority, energy, plan today in slot
EXAMPLE_TASKS = [
    ("Grade problem set 4", "TA work", 2, 180, "high", "deep", "afternoon"),
    ("Office hours prep notes", "TA work", 1, 30, "normal", "easy", None),
    ("Read two papers for seminar", "Class", 1, 90, "high", "deep", "morning"),
    ("Run gel for the sample batch", "Lab work", 3, 120, "normal", "deep", None),
    ("Draft STEMPower workshop outline", "STEMPower", 5, 60, "normal", "deep", None),
    ("Follow up on internship application", "Jobs", 0, 15, "high", "easy", "midday"),
    ("YBC meeting agenda", "YBC", 4, 30, "low", "easy", None),
    ("Gym and a real dinner", "Personal", None, 90, "normal", "easy", "evening"),
    ("Submit timesheet", "Work", -1, 15, "normal", "easy", None),
]


class Command(BaseCommand):
    help = "Create or refresh the demo account and its example data. Safe to run repeatedly."

    def handle(self, *args, **opts):
        demo_email = os.environ.get("DEMO_EMAIL", "demo@compass.app").strip().lower()
        demo_password = os.environ.get("DEMO_PASSWORD") or ("compass-demo-2026" if settings.DEBUG else "")
        if not demo_password:
            raise CommandError("Set DEMO_PASSWORD before seeding outside development.")
        with transaction.atomic():
            demo = self.account(demo_email, demo_password, first_name="Demo")
            self.example_data(demo)
            owner_email = os.environ.get("OWNER_EMAIL", "").strip().lower()
            if owner_email:
                owner = self.account(owner_email, os.environ.get("OWNER_PASSWORD") or None, admin=True)
                self.stdout.write(f"Owner account ready: {owner.email}")
        self.stdout.write(self.style.SUCCESS(f"Demo account ready: {demo_email}"))

    def account(self, email, password, first_name="", admin=False):
        user = User.objects.filter(email__iexact=email).first()
        if not user:
            user = User.objects.create_user(username=email, email=email, first_name=first_name)
            if not password:
                user.set_unusable_password()
        if password:
            user.set_password(password)
        if admin:
            user.is_staff = user.is_superuser = True
        user.save()
        Area.create_defaults(user)
        from allauth.account.models import EmailAddress

        EmailAddress.objects.update_or_create(user=user, email=email, defaults={"primary": True, "verified": True})
        return user

    def example_data(self, user):
        today = timezone.localdate()
        areas = {a.name: a for a in Area.objects.filter(user=user)}
        plan = DayPlan.for_date(user, today)
        for i, (title, area, due, minutes, priority, energy, slot) in enumerate(EXAMPLE_TASKS):
            task, _ = Task.objects.update_or_create(
                user=user, title=title,
                defaults={
                    "area": areas.get(area) or next(iter(areas.values())),
                    "due_date": today + timedelta(days=due) if due is not None else None,
                    "minutes": minutes, "priority": priority, "energy": energy, "done": False, "done_at": None,
                },
            )
            if slot:
                PlanEntry.objects.update_or_create(plan=plan, task=task, defaults={"slot": slot, "position": i})
        plan.top_tasks.set(Task.objects.filter(user=user, title__in=[
            "Read two papers for seminar", "Grade problem set 4", "Follow up on internship application"]))
        WeeklyCheckIn.objects.update_or_create(
            user=user, week_start=WeeklyCheckIn.monday_of(today),
            defaults={"goal": "Finish the lit review draft and stay on top of grading"},
        )
