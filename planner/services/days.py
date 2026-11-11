"""How full a day is: tasks and calendar events per part of the day, and the balance check."""
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import CalendarEvent, DayPlan, PlanEntry, Task
from ..utils import fmt_minutes  # noqa: F401 - re-exported for templates and tests


def day_bounds(date):
    start = timezone.make_aware(datetime.combine(date, time.min))
    return start, start + timedelta(days=1)


def minute_of_day(dt, date):
    start, _ = day_bounds(date)
    return (timezone.localtime(dt) - start).total_seconds() / 60


def events_on(user, date):
    """Timed events overlapping the date, and all-day events covering it."""
    start, end = day_bounds(date)
    timed = list(
        CalendarEvent.objects.filter(user=user, start__lt=end, end__gt=start, all_day_date__isnull=True).order_by("start")
    )
    all_day = list(
        CalendarEvent.objects.filter(user=user, all_day_date__lte=date)
        .filter(Q(all_day_end__gt=date) | Q(all_day_end__isnull=True, all_day_date=date))
        .order_by("calendar_name", "title")
    )
    return timed, all_day


@dataclass
class Slot:
    key: str
    name: str
    range: str
    start: int
    end: int
    entries: list = field(default_factory=list)
    events: list = field(default_factory=list)
    task_minutes: int = 0
    event_minutes: int = 0

    @property
    def capacity(self):
        return self.end - self.start

    @property
    def used(self):
        return self.task_minutes + self.event_minutes

    @property
    def free(self):
        return max(0, self.capacity - self.used)

    @property
    def percent(self):
        return min(100, round(self.used / self.capacity * 100)) if self.capacity else 0

    @property
    def state(self):
        if self.used > self.capacity:
            return "over"
        if self.used > self.capacity * 0.85:
            return "near"
        return "ok"


@dataclass
class DaySummary:
    date: object
    plan: DayPlan
    slots: list
    all_day: list
    issues: list
    verdict: str
    word: str

    @property
    def used(self):
        return sum(s.used for s in self.slots)

    @property
    def capacity(self):
        return sum(s.capacity for s in self.slots)

    @property
    def planned_count(self):
        return sum(len(s.entries) for s in self.slots)

    def slot(self, key):
        return next(s for s in self.slots if s.key == key)


def summarize(user, date):
    plan = DayPlan.for_date(user, date)
    entries = list(plan.entries.select_related("task", "task__area"))
    timed, all_day = events_on(user, date)
    slots = []
    for key, name, rng, start, end in PlanEntry.SLOTS:
        s = Slot(key, name, rng, start, end)
        s.entries = [e for e in entries if e.slot == key]
        s.task_minutes = sum(e.task.minutes for e in s.entries if not e.task.done)
        for ev in timed:
            a, b = max(start, minute_of_day(ev.start, date)), min(end, minute_of_day(ev.end, date))
            if b > a:
                s.events.append(ev)
                if not ev.is_free and not ev.task_id:  # a Compass block for a planned task isn't counted twice
                    s.event_minutes += int(b - a)
        slots.append(s)

    issues = []
    for s in slots:
        if s.used > s.capacity:
            issues.append(("bad", f"{s.name} is over by {fmt_minutes(s.used - s.capacity)}."))
        deep = [e.task for e in s.entries if not e.task.done and e.task.energy == "deep"]
        if s.key == "evening":
            for t in deep:
                issues.append(("warn", f"“{t.title}” needs deep focus but sits in the evening."))
        if len(deep) >= 3:
            issues.append(("warn", f"{s.name} has {len(deep)} deep-focus tasks in a row. Add a break."))
    planned_ids = {e.task_id for e in entries}
    due = Task.objects.filter(user=user, done=False, due_date__lte=date).exclude(id__in=planned_ids)
    for t in due[:6]:
        when = "overdue" if t.due_date < date else "due that day"
        issues.append(("bad", f"“{t.title}” is {when} and isn’t planned."))
    if entries and not any(e.task.area.is_personal for e in entries):
        issues.append(("warn", "No personal time planned."))

    if any(lvl == "bad" for lvl, _ in issues):
        verdict, word = "bad", "Needs a fix"
    elif issues:
        verdict, word = "warn", "Almost there"
    elif entries:
        verdict, word = "good", "Balanced day"
    else:
        verdict, word = "idle", "Nothing planned yet"
    return DaySummary(date, plan, slots, all_day, issues, verdict, word)


def suggest_score(task, slot_key, date):
    """Higher is a better fit; used to order the 'add to this part of the day' list."""
    s = 0
    if task.due_date:
        diff = (task.due_date - date).days
        s += 60 if diff <= 0 else 40 if diff <= 1 else 20 if diff <= 3 else 8 if diff <= 7 else 0
    s += {"high": 15, "low": -5}.get(task.priority, 0)
    deep_slot = slot_key in ("morning", "afternoon")
    s += (10 if deep_slot else -10) if task.energy == "deep" else (0 if deep_slot else 6)
    if task.area.is_personal and slot_key == "evening":
        s += 8
    return s


def plan_task(user, task, date, slot):
    plan = DayPlan.for_date(user, date)
    entry = PlanEntry.objects.filter(plan=plan, task=task).first()
    last = plan.entries.filter(slot=slot).order_by("-position").values_list("position", flat=True).first()
    pos = (last + 1) if last is not None else 0
    if entry:
        if entry.slot != slot:
            entry.slot, entry.position = slot, pos
            entry.save(update_fields=["slot", "position"])
        return entry
    return PlanEntry.objects.create(plan=plan, task=task, slot=slot, position=pos)
