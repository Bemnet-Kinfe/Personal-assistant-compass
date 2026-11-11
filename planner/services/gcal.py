"""Google Calendar: copy events into Compass, and add time blocks.

Calls the REST API with `requests` so tests mock a single module. Failures are
recorded on CalendarSync and shown on the page; they never break a page load.
"""
import logging
from datetime import date as date_cls
from datetime import datetime, timedelta
from urllib.parse import quote

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import GOOGLE_COLOR_IDS, CalendarEvent, CalendarSync

log = logging.getLogger(__name__)
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"
TIMEOUT = 15


class CalendarError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code  # not_connected | reconnect | google_error


MESSAGES = {
    "not_connected": "Google Calendar isn’t connected. Connect it in Settings.",
    "reconnect": "Google needs you to reconnect. Go to Settings and connect Google Calendar again.",
    "google_error": "Google Calendar didn’t respond. Compass will try again shortly.",
}


def social_token(user):
    from allauth.socialaccount.models import SocialToken

    return (
        SocialToken.objects.filter(account__user=user, account__provider="google")
        .select_related("account")
        .order_by("-id")
        .first()
    )


def is_connected(user):
    return social_token(user) is not None


def _access_token(user):
    tok = social_token(user)
    if not tok:
        raise CalendarError("not_connected", MESSAGES["not_connected"])
    if tok.expires_at and tok.expires_at > timezone.now() + timedelta(seconds=60):
        return tok.token
    if not tok.token_secret:
        raise CalendarError("reconnect", MESSAGES["reconnect"])
    try:
        r = requests.post(
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "refresh_token": tok.token_secret,
                "grant_type": "refresh_token",
            },
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        log.warning("google token refresh failed: %s", e)
        raise CalendarError("google_error", MESSAGES["google_error"])
    if r.status_code != 200:
        log.warning("google token refresh rejected: %s", r.status_code)
        raise CalendarError("reconnect", MESSAGES["reconnect"])
    body = r.json()
    tok.token = body["access_token"]
    tok.expires_at = timezone.now() + timedelta(seconds=int(body.get("expires_in", 3600)))
    tok.save(update_fields=["token", "expires_at"])
    return tok.token


def _call(user, method, path, **kw):
    headers = {"Authorization": f"Bearer {_access_token(user)}"}
    try:
        r = requests.request(method, API + path, headers=headers, timeout=TIMEOUT, **kw)
    except requests.RequestException as e:
        log.warning("google calendar request failed: %s", e)
        raise CalendarError("google_error", MESSAGES["google_error"])
    if r.status_code in (401, 403):
        raise CalendarError("reconnect", MESSAGES["reconnect"])
    if r.status_code >= 400:
        log.warning("google calendar error %s: %s", r.status_code, r.text[:300])
        raise CalendarError("google_error", MESSAGES["google_error"])
    return r.json() if r.content else {}


def list_calendars(user):
    """Calendars ticked on in the user's Google Calendar, without duplicate subscriptions."""
    data = _call(user, "GET", "/users/me/calendarList", params={"minAccessRole": "reader", "maxResults": 50})
    cals, seen = [], set()
    for c in data.get("items", []):
        if c.get("hidden") or c.get("selected") is False:
            continue
        name = (c.get("summaryOverride") or c.get("summary") or "").strip()
        key = name.lower() if "#holiday" in c.get("id", "") else c.get("id")
        if key in seen:
            continue
        seen.add(key)
        cals.append({"id": c["id"], "name": name, "primary": bool(c.get("primary"))})
    return cals


def _event_fields(ev, cal):
    start, end = ev.get("start", {}), ev.get("end", {})
    private = (ev.get("extendedProperties") or {}).get("private") or {}
    fields = {
        "calendar_name": cal["name"][:200],
        "is_primary": cal["primary"],
        "title": (ev.get("summary") or "(No title)")[:300],
        "is_free": ev.get("transparency") == "transparent",
        "html_link": (ev.get("htmlLink") or "")[:500],
        "start": None, "end": None, "all_day_date": None, "all_day_end": None,
    }
    if "date" in start:
        fields["all_day_date"] = date_cls.fromisoformat(start["date"])
        fields["all_day_end"] = date_cls.fromisoformat(end["date"]) if end.get("date") else None
    else:
        fields["start"] = parse_datetime(start.get("dateTime", "")) if start.get("dateTime") else None
        fields["end"] = parse_datetime(end.get("dateTime", "")) if end.get("dateTime") else None
        if not fields["start"] or not fields["end"]:
            return None
    return fields, private


def sync(user, start_date, days=7):
    """Copy events for [start_date, start_date + days) from every visible calendar. Returns the number kept."""
    tz = timezone.get_current_timezone()
    a = datetime.combine(start_date, datetime.min.time(), tzinfo=tz)
    b = a + timedelta(days=days)
    state, _ = CalendarSync.objects.get_or_create(user=user)
    try:
        calendars = list_calendars(user)
        kept = []
        for cal in calendars:
            try:
                data = _call(
                    user, "GET", f"/calendars/{quote(cal['id'], safe='')}/events",
                    params={"timeMin": a.isoformat(), "timeMax": b.isoformat(), "singleEvents": "true",
                            "orderBy": "startTime", "maxResults": 250},
                )
            except CalendarError as e:
                if cal["primary"] or e.code == "reconnect":
                    raise
                log.warning("skipping calendar %s: %s", cal["name"], e)
                continue
            for ev in data.get("items", []):
                if ev.get("status") == "cancelled":
                    continue
                me = next((x for x in ev.get("attendees", []) if x.get("self")), None)
                if me and me.get("responseStatus") == "declined":
                    continue
                shaped = _event_fields(ev, cal)
                if shaped:
                    kept.append((cal["id"], ev["id"], *shaped))
    except CalendarError as e:
        state.error_code, state.error_message = e.code, str(e)
        state.save(update_fields=["error_code", "error_message"])
        raise

    from ..models import Area, Task

    with transaction.atomic():
        in_range = CalendarEvent.objects.filter(user=user).filter(
            models_q_range(a, b, start_date, start_date + timedelta(days=days))
        )
        keep_keys = set()
        for cal_id, gid, fields, private in kept:
            if private.get("compass_task"):
                fields["task"] = Task.objects.filter(user=user, id=private["compass_task"]).first()
            if private.get("compass_area"):
                fields["area"] = Area.objects.filter(user=user, id=private["compass_area"]).first()
            CalendarEvent.objects.update_or_create(user=user, calendar_id=cal_id, google_id=gid, defaults=fields)
            keep_keys.add((cal_id, gid))
        stale = [e.id for e in in_range if (e.calendar_id, e.google_id) not in keep_keys]
        CalendarEvent.objects.filter(id__in=stale).delete()
        state.synced_at = timezone.now()
        state.range_start, state.range_end = start_date, start_date + timedelta(days=days)
        state.error_code = state.error_message = ""
        state.save()
    return len(kept)


def models_q_range(a, b, d1, d2):
    from django.db.models import Q

    return Q(start__lt=b, end__gt=a) | Q(all_day_date__gte=d1, all_day_date__lt=d2)


def ensure_fresh(user, start_date, days=3):
    """Sync if the copy is older than CALENDAR_SYNC_MINUTES or doesn't cover the dates. Never raises."""
    if not is_connected(user):
        return
    state = CalendarSync.objects.filter(user=user).first()
    end_date = start_date + timedelta(days=days)
    fresh = (
        state and state.synced_at
        and state.synced_at > timezone.now() - timedelta(minutes=settings.CALENDAR_SYNC_MINUTES)
        and state.range_start and state.range_start <= start_date and state.range_end >= end_date
    )
    if fresh:
        return
    try:
        sync(user, min(start_date, timezone.localdate()), days=max(7, (end_date - timezone.localdate()).days))
    except CalendarError:
        pass  # recorded on CalendarSync; the page shows it


def create_block(user, task, date, start_minute, minutes):
    """Put a time block for a task on the user's own calendar, in the task's area color."""
    tz = timezone.get_current_timezone()
    start = datetime.combine(date, datetime.min.time(), tzinfo=tz) + timedelta(minutes=start_minute)
    end = start + timedelta(minutes=minutes)
    body = {
        "summary": task.title[:200],
        "description": f"Planned with Compass · {task.area.name}",
        "start": {"dateTime": start.isoformat(), "timeZone": settings.TIME_ZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.TIME_ZONE},
        "colorId": GOOGLE_COLOR_IDS.get(task.area.color, "9"),
        "extendedProperties": {"private": {"compass_task": str(task.id), "compass_area": str(task.area_id)}},
    }
    ev = _call(user, "POST", "/calendars/primary/events", json=body)
    return CalendarEvent.objects.update_or_create(
        user=user, calendar_id="primary", google_id=ev.get("id", ""),
        defaults={"calendar_name": "", "is_primary": True, "title": task.title, "start": start, "end": end,
                  "html_link": ev.get("htmlLink", "")[:500], "task": task, "area": task.area},
    )[0]
