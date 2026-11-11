"""Daily and weekly check-ins."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..forms import WeeklyGoalForm
from ..models import Area, DayPlan, PlanEntry, Task, WeeklyCheckIn
from ..services import days
from .common import changed, parse_date


@login_required
def checkin_daily(request):
    user, today = request.user, timezone.localdate()
    tomorrow = today + timedelta(days=1)
    today_plan = DayPlan.for_date(user, today)
    tomorrow_summary = days.summarize(user, tomorrow)
    planned_today = list(Task.objects.filter(plan_entries__plan=today_plan).select_related("area"))
    due_today = Task.objects.filter(user=user, due_date=today).select_related("area")
    tomorrow_ids = {e.task_id for s in tomorrow_summary.slots for e in s.entries}
    ctx = {
        "nav": "checkins",
        "today": today,
        "tomorrow": tomorrow,
        "today_plan": today_plan,
        "close_out": list({t.id: t for t in [*planned_today, *due_today]}.values()),
        "carry": [t for t in planned_today if not t.done and t.id not in tomorrow_ids],
        "tomorrow_summary": tomorrow_summary,
        "tomorrow_events": [ev for s in tomorrow_summary.slots for ev in s.events],
        "top_ids": set(tomorrow_summary.plan.top_tasks.values_list("id", flat=True)),
        "open_tasks": Task.objects.filter(user=user, done=False).select_related("area")[:15],
    }
    return render(request, "planner/checkin_daily.html", ctx)


@login_required
@require_POST
def carry_over(request):
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)
    entries = PlanEntry.objects.filter(plan__user=request.user, plan__date=today, task__done=False).select_related("task")
    already = set(PlanEntry.objects.filter(plan__user=request.user, plan__date=tomorrow).values_list("task_id", flat=True))
    moved = 0
    for e in entries:
        if e.task_id not in already:
            days.plan_task(request.user, e.task, tomorrow, e.slot)
            moved += 1
    return changed(request, f"Moved {moved} to tomorrow" if moved else "Nothing to move", "checkin_daily")


@login_required
@require_POST
def finish_day(request):
    plan_obj = DayPlan.for_date(request.user, timezone.localdate())
    plan_obj.reflection = (request.POST.get("reflection") or "")[:1000]
    plan_obj.checked_in_at = timezone.now()
    plan_obj.save(update_fields=["reflection", "checked_in_at"])
    return changed(request, "Daily check-in done. Good night!", "checkin_daily")


def week_for(today):
    """The week a check-in plans: this week, or next week once it's Sunday."""
    return WeeklyCheckIn.monday_of(today + timedelta(days=1) if today.weekday() == 6 else today)


@login_required
def checkin_weekly(request):
    user, today = request.user, timezone.localdate()
    monday = week_for(today)
    sunday = monday + timedelta(days=6)
    week, _ = WeeklyCheckIn.objects.get_or_create(user=user, week_start=monday)
    form = WeeklyGoalForm(request.POST or None, instance=week)
    if request.method == "POST" and form.is_valid():
        week = form.save(commit=False)
        finishing = bool(request.POST.get("finish"))
        if finishing:
            week.completed_at = timezone.now()
        week.save()
        return changed(request, "Weekly check-in done" if finishing else "Saved", "checkin_weekly")
    due = list(Task.objects.filter(user=user, done=False, due_date__range=(monday, sunday)).select_related("area"))
    by_day = [(monday + timedelta(days=n), [t for t in due if t.due_date == monday + timedelta(days=n)]) for n in range(7)]
    ctx = {
        "nav": "checkins",
        "week": week,
        "monday": monday,
        "form": form,
        "by_day": [(d, ts) for d, ts in by_day if ts],
        "areas": Area.objects.filter(user=user).annotate(open_count=Count("tasks", filter=Q(tasks__done=False))),
        "overdue": Task.objects.filter(user=user, done=False, due_date__lt=today).select_related("area"),
        "last_week": WeeklyCheckIn.objects.filter(user=user, week_start=monday - timedelta(days=7)).first(),
    }
    return render(request, "planner/checkin_weekly.html", ctx)


@login_required
@require_POST
def task_reschedule(request, pk):
    task = get_object_or_404(Task, user=request.user, pk=pk)
    d = parse_date(request.POST.get("due_date"))
    if not d:
        return changed(request, None, "checkin_weekly")
    task.due_date = d
    task.save(update_fields=["due_date"])
    return changed(request, f"Moved to {d:%a %b} {d.day}", "checkin_weekly")
