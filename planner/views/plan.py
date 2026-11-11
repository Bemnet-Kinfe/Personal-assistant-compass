"""The day plan: parts of the day, adding and removing tasks, and the top 3."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..models import DayPlan, PlanEntry, Task
from ..services import days
from .common import changed, is_htmx, parse_date, toast_only


@login_required
def plan(request):
    user, today = request.user, timezone.localdate()
    date = parse_date(request.GET.get("date"), today)
    ctx = {"nav": "plan", "date": date, "today": today}
    ctx.update({
        "summary": days.summarize(user, date),
        "day_choices": [today + timedelta(days=n) for n in range(7)],
        "prev_day": date - timedelta(days=1),
        "next_day": date + timedelta(days=1),
    })
    return render(request, "planner/plan.html", ctx)


@login_required
def plan_pick(request, date, slot):
    d = parse_date(date)
    if not d or slot not in dict(PlanEntry.SLOT_CHOICES):
        return HttpResponse(status=404)
    taken = DayPlan.for_date(request.user, d).entries.values_list("task_id", flat=True)
    pool = list(Task.objects.filter(user=request.user, done=False).exclude(id__in=taken).select_related("area"))
    pool.sort(key=lambda t: -days.suggest_score(t, slot, d))
    ctx = {"date": d, "slot": PlanEntry.slot_info(slot), "pool": pool}
    return render(request, "planner/partials/pick_modal.html" if is_htmx(request) else "planner/pick_page.html", ctx)


@login_required
@require_POST
def plan_add(request):
    d, slot = parse_date(request.POST.get("date")), request.POST.get("slot")
    task = get_object_or_404(Task, user=request.user, pk=request.POST.get("task"))
    if not d or slot not in dict(PlanEntry.SLOT_CHOICES):
        return HttpResponse("Pick a day and a part of the day.", status=400)
    days.plan_task(request.user, task, d, slot)
    return changed(request, f"Added to {dict(PlanEntry.SLOT_CHOICES)[slot].lower()}", "plan")


@login_required
@require_POST
def plan_remove(request, pk):
    get_object_or_404(PlanEntry, plan__user=request.user, pk=pk).delete()
    return changed(request, "Taken off the plan", "plan")


@login_required
@require_POST
def plan_star(request):
    d = parse_date(request.POST.get("date"))
    task = get_object_or_404(Task, user=request.user, pk=request.POST.get("task"))
    if not d:
        return HttpResponse(status=400)
    plan_obj = DayPlan.for_date(request.user, d)
    if plan_obj.top_tasks.filter(pk=task.pk).exists():
        plan_obj.top_tasks.remove(task)
    elif plan_obj.top_tasks.count() >= 3:
        return toast_only(request, "Top 3 is full. Unstar one first.", "plan")
    else:
        plan_obj.top_tasks.add(task)
    return changed(request, None, "plan")
