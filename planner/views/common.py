"""Helpers every page uses, the home page, and the health check."""
import json
import logging
from datetime import date as date_cls
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET

from ..models import Task

log = logging.getLogger(__name__)


def is_htmx(request):
    return request.headers.get("HX-Request") == "true"


def changed(request, toast=None, fallback="home"):
    """After a change: htmx gets 204 plus an event that refreshes the page body; plain forms get a redirect."""
    if is_htmx(request):
        resp = HttpResponse(status=204)
        trigger = {"compass:changed": True}
        if toast:
            trigger["compass:toast"] = toast
        resp["HX-Trigger"] = json.dumps(trigger)
        return resp
    if toast:
        messages.success(request, toast)
    nxt = request.POST.get("next") or request.GET.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, {request.get_host()}, require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(fallback)


def toast_only(request, toast, fallback="home"):
    """Tell the user something without changing the page."""
    if is_htmx(request):
        resp = HttpResponse(status=204)
        resp["HX-Trigger"] = json.dumps({"compass:toast": toast})
        return resp
    messages.warning(request, toast)
    return redirect(fallback)


def parse_date(value, default=None):
    try:
        return date_cls.fromisoformat(value)
    except (TypeError, ValueError):
        return default


def greeting():
    h = timezone.localtime().hour
    if h < 5 or h >= 22:
        return "Up late"
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


@login_required
def home(request):
    user, today = request.user, timezone.localdate()
    open_tasks = list(Task.objects.filter(user=user, done=False).select_related("area"))
    ctx = {
        "nav": "home",
        "greeting": greeting(),
        "today": today,
        "open_count": len(open_tasks),
        "done_today": Task.objects.filter(user=user, done=True, done_at__date=today).count(),
        "has_tasks": Task.objects.filter(user=user).exists(),
        "coming_up": [t for t in open_tasks if t.due_date and today < t.due_date <= today + timedelta(days=3)],
    }
    planned = set()
    ctx["due_now"] = [t for t in open_tasks if t.due_date and t.due_date <= today and t.id not in planned]
    return render(request, "planner/home.html", ctx)


@require_GET
def healthz(request):
    """For the hosting platform: 200 when the app can reach its database."""
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception:  # noqa: BLE001 - any database failure means unhealthy
        log.exception("health check failed")
        return JsonResponse({"status": "error", "database": "unreachable"}, status=503)
    return JsonResponse({"status": "ok"})
