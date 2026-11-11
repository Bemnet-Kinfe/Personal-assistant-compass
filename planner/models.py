from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# Colors are named tokens from the stylesheet so both themes and Google's event colors stay in step.
COLOR_CHOICES = [
    ("blue", "Blue"), ("violet", "Violet"), ("teal", "Teal"), ("green", "Green"),
    ("pink", "Pink"), ("amber", "Amber"), ("cyan", "Cyan"), ("slate", "Slate"), ("coral", "Coral"),
]
# Closest Google Calendar event colors (1 Lavender … 11 Tomato) for blocks Compass creates.
GOOGLE_COLOR_IDS = {
    "blue": "9", "violet": "3", "teal": "2", "green": "10", "pink": "4",
    "amber": "5", "cyan": "7", "slate": "8", "coral": "6",
}
DEFAULT_AREAS = [
    ("Class", "blue"), ("TA work", "violet"), ("STEMPower", "teal"), ("Lab work", "green"),
    ("Personal", "pink"), ("Jobs", "amber"), ("YBC", "cyan"), ("Work", "slate"),
]


class Area(models.Model):
    """A part of life tasks belong to, such as Class or Lab work."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=40)
    color = models.CharField(max_length=12, choices=COLOR_CHOICES, default="blue")
    position = models.PositiveSmallIntegerField(default=0)
    is_personal = models.BooleanField(default=False, help_text="Counts as personal time in the day check.")

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["user", "name"], name="unique_area_name_per_user")]

    def __str__(self):
        return self.name

    @classmethod
    def create_defaults(cls, user):
        if cls.objects.filter(user=user).exists():
            return
        cls.objects.bulk_create(
            cls(user=user, name=name, color=color, position=i, is_personal=(name == "Personal"))
            for i, (name, color) in enumerate(DEFAULT_AREAS)
        )


class Task(models.Model):
    PRIORITY_CHOICES = [("high", "High"), ("normal", "Normal"), ("low", "Low")]
    ENERGY_CHOICES = [("deep", "Deep focus"), ("easy", "Easy")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tasks")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="tasks")
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True, max_length=2000)
    due_date = models.DateField(null=True, blank=True)
    minutes = models.PositiveSmallIntegerField(default=60)
    priority = models.CharField(max_length=6, choices=PRIORITY_CHOICES, default="normal")
    energy = models.CharField(max_length=4, choices=ENERGY_CHOICES, default="deep")
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["done", models.F("due_date").asc(nulls_last=True), "created_at"]
        indexes = [models.Index(fields=["user", "done", "due_date"])]

    def __str__(self):
        return self.title

    def set_done(self, done):
        self.done = done
        self.done_at = timezone.now() if done else None

    @property
    def is_overdue(self):
        return bool(not self.done and self.due_date and self.due_date < timezone.localdate())


class DayPlan(models.Model):
    """One user's plan for one date: which tasks go in which part of the day, and the top 3."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="day_plans")
    date = models.DateField()
    top_tasks = models.ManyToManyField(Task, blank=True, related_name="top_in")
    reflection = models.TextField(blank=True, max_length=1000)
    checked_in_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "date"], name="unique_plan_per_day")]

    def __str__(self):
        return f"{self.user_id} {self.date}"

    @classmethod
    def for_date(cls, user, date):
        plan, _ = cls.objects.get_or_create(user=user, date=date)
        return plan


class PlanEntry(models.Model):
    SLOTS = [
        # key, label, range label, start minute, end minute (after midnight)
        ("morning", "Morning", "8am–12pm", 8 * 60, 12 * 60),
        ("midday", "Midday", "12–2pm", 12 * 60, 14 * 60),
        ("afternoon", "Afternoon", "2–6pm", 14 * 60, 18 * 60),
        ("evening", "Evening", "6–11:30pm", 18 * 60, 23 * 60 + 30),
    ]
    SLOT_CHOICES = [(s[0], s[1]) for s in SLOTS]

    plan = models.ForeignKey(DayPlan, on_delete=models.CASCADE, related_name="entries")
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="plan_entries")
    slot = models.CharField(max_length=10, choices=SLOT_CHOICES)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]
        constraints = [models.UniqueConstraint(fields=["plan", "task"], name="task_once_per_day")]

    @classmethod
    def slot_info(cls, key):
        return next(s for s in cls.SLOTS if s[0] == key)

    @classmethod
    def slot_for_minute(cls, minute):
        for key, _l, _r, start, end in cls.SLOTS:
            if start <= minute < end:
                return key
        return "morning" if minute < cls.SLOTS[0][3] else "evening"


class WeeklyCheckIn(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="weekly_checkins")
    week_start = models.DateField(help_text="The Monday of the week.")
    goal = models.CharField(max_length=300, blank=True)
    reflection = models.TextField(blank=True, max_length=1000)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "week_start"], name="unique_week_per_user")]

    @staticmethod
    def monday_of(date):
        return date - timedelta(days=date.weekday())


class CalendarEvent(models.Model):
    """A Google Calendar event copied into Compass so pages and the assistant can use it without calling Google."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="calendar_events")
    google_id = models.CharField(max_length=255)
    calendar_id = models.CharField(max_length=255)
    calendar_name = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    title = models.CharField(max_length=300)
    start = models.DateTimeField(null=True, blank=True)
    end = models.DateTimeField(null=True, blank=True)
    all_day_date = models.DateField(null=True, blank=True)
    all_day_end = models.DateField(null=True, blank=True, help_text="Exclusive, as Google sends it.")
    is_free = models.BooleanField(default=False)
    html_link = models.URLField(max_length=500, blank=True)
    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.SET_NULL, related_name="calendar_blocks")
    area = models.ForeignKey(Area, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["start"]
        constraints = [
            models.UniqueConstraint(fields=["user", "calendar_id", "google_id"], name="unique_event_per_calendar")
        ]
        indexes = [models.Index(fields=["user", "start"]), models.Index(fields=["user", "all_day_date"])]

    @property
    def from_compass(self):
        return self.area_id is not None or self.task_id is not None


class CalendarSync(models.Model):
    """When each user's calendar was last copied, and the last problem, so pages can say what went wrong."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="calendar_sync")
    synced_at = models.DateTimeField(null=True, blank=True)
    range_start = models.DateField(null=True, blank=True)
    range_end = models.DateField(null=True, blank=True)
    error_code = models.CharField(max_length=30, blank=True)
    error_message = models.CharField(max_length=300, blank=True)


class ChatMessage(models.Model):
    ROLE_CHOICES = [("user", "You"), ("assistant", "Assistant")]
    STATUS_CHOICES = [("", "No changes"), ("pending", "Waiting for you"), ("applied", "Done"), ("skipped", "Skipped")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="chat_messages")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(max_length=4000)
    changes = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, blank=True, default="")
    applied = models.JSONField(default=list, blank=True)
    is_error = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


class AIUsage(models.Model):
    """Assistant requests per user per day, to cap AI use."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    day = models.DateField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "day"], name="unique_usage_per_day")]
