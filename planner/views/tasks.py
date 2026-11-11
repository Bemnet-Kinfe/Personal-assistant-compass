"""Tasks, life areas and the settings page."""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from ..forms import AreaForm, TaskForm
from ..models import Area, Task
from ..models import PlanEntry
from ..services import days
from ..models import CalendarSync
from ..services import gcal
from .common import changed, is_htmx, toast_only
from .common import parse_date


@login_required
def tasks(request):
    user = request.user
    areas = Area.objects.filter(user=user).annotate(open_count=Count("tasks", filter=Q(tasks__done=False)))
    area = None
    if request.GET.get("area"):
        area = get_object_or_404(Area, user=user, id=request.GET["area"])
    show_done = request.GET.get("done") == "1"
    q = (request.GET.get("q") or "").strip()
    qs = Task.objects.filter(user=user).select_related("area")
    if area:
        qs = qs.filter(area=area)
    if not show_done:
        qs = qs.filter(done=False)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(notes__icontains=q))
    ctx = {
        "nav": "tasks",
        "areas": areas,
        "area": area,
        "show_done": show_done,
        "q": q,
        "task_list": qs[:300],
        "open_total": Task.objects.filter(user=user, done=False).count(),
        "has_tasks": Task.objects.filter(user=user).exists(),
    }
    return render(request, "planner/tasks.html", ctx)


@login_required
def task_new(request):
    initial = {"area": request.GET.get("area"), "due_date": request.GET.get("due"), "minutes": 60}
    return _task_form(request, None, initial)


@login_required
def task_edit(request, pk):
    return _task_form(request, get_object_or_404(Task, user=request.user, pk=pk), None)


def _task_form(request, task, initial):
    form = TaskForm(request.POST or None, instance=task, initial=initial, user=request.user)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        plan_date = parse_date(request.POST.get("plan_date"))
        if plan_date and request.POST.get("plan_slot") in dict(PlanEntry.SLOT_CHOICES):
            days.plan_task(request.user, obj, plan_date, request.POST["plan_slot"])
        return changed(request, "Saved" if task else "Added", "tasks")
    ctx = {
        "form": form,
        "task": task,
        "plan_date": request.GET.get("plan_date") or request.POST.get("plan_date", ""),
        "plan_slot": request.GET.get("plan_slot") or request.POST.get("plan_slot", ""),
    }
    if is_htmx(request):
        return render(request, "planner/partials/task_modal.html", ctx)
    return render(request, "planner/task_form.html", {**ctx, "nav": "tasks"})


@login_required
@require_POST
def task_toggle(request, pk):
    task = get_object_or_404(Task, user=request.user, pk=pk)
    task.set_done(not task.done)
    task.save(update_fields=["done", "done_at"])
    return changed(request, "Done! Nice." if task.done else "Marked not done")


@login_required
@require_POST
def task_delete(request, pk):
    get_object_or_404(Task, user=request.user, pk=pk).delete()
    return changed(request, "Deleted", "tasks")


@login_required
def settings_page(request):
    user = request.user
    ctx = {
        "nav": "settings",
        "areas": Area.objects.filter(user=user).annotate(task_count=Count("tasks")),
        "new_area_form": AreaForm(user=user),
        "connected": gcal.is_connected(user),
        "sync": CalendarSync.objects.filter(user=user).first(),
    }
    return render(request, "planner/settings.html", ctx)


@login_required
@require_POST
def area_save(request, pk=None):
    area = get_object_or_404(Area, user=request.user, pk=pk) if pk else None
    form = AreaForm(request.POST, instance=area, user=request.user)
    if not form.is_valid():
        return toast_only(request, "; ".join(e for errs in form.errors.values() for e in errs), "settings")
    obj = form.save(commit=False)
    obj.user = request.user
    if not area:
        obj.position = Area.objects.filter(user=request.user).count()
    obj.save()
    return changed(request, "Area saved", "settings")


@login_required
@require_POST
def area_delete(request, pk):
    area = get_object_or_404(Area, user=request.user, pk=pk)
    if area.tasks.exists():
        return toast_only(request, "Move or delete this area’s tasks first.", "settings")
    area.delete()
    return changed(request, "Area deleted", "settings")
