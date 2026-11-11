"""The planning assistant.

The model never changes anything itself. It returns a structured list of
proposed changes; Compass validates each one against the user's own data, shows
them as a checklist, and applies only the ones the user approves.
"""
import json
import logging
import re
from datetime import date as date_cls
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from ..models import AIUsage, Area, ChatMessage, DayPlan, PlanEntry, Task
from . import ai, days, gcal

log = logging.getLogger(__name__)
SLOT_KEYS = [s[0] for s in PlanEntry.SLOTS]
HISTORY = 12

ERROR_COPY = {
    "rate_limited": "You’ve reached today’s assistant limit. It resets at midnight.",
    "not_configured": "The assistant isn’t set up yet. Add an OPENROUTER_API_KEY on the server.",
    "invalid_json": "My answer came out garbled. Try asking again.",
    "upstream_error": "I couldn’t reach the AI just now. Try again in a moment.",
}

RULES = """You are {name}'s planning assistant inside Compass, a personal planner. Keep replies short, warm and easy to skim on a phone: a few sentences or a short list. No headings, no tables.

You can propose changes. Nothing happens until the user approves, so propose only what they asked for or clearly need. Change types:
- {{"type":"add_task","title":"...","area":"area name","due":"YYYY-MM-DD"|null,"minutes":number,"priority":"high|normal|low","energy":"deep|easy"}}
- {{"type":"update_task","task":id,"title"?,"area"?,"due"?,"minutes"?,"priority"?,"energy"?}} (only fields that change)
- {{"type":"complete","task":id}}
- {{"type":"plan","task":id,"date":"YYYY-MM-DD","slot":"morning|midday|afternoon|evening"}} (also moves a task already planned that day)
- {{"type":"unplan","task":id,"date":"YYYY-MM-DD"}}
- {{"type":"set_top3","date":"YYYY-MM-DD","tasks":[id, ...]}} (at most 3)
- {{"type":"block_time","task":id,"date":"YYYY-MM-DD","start":"HH:MM","minutes":number}} (puts a block on Google Calendar and plans the task; only when the user asks for calendar blocks, and only in free time)
To refer to a task you add in the same reply, use "new:0", "new:1", ... in order of your add_task changes.
Every change needs a short "label" the user will read, like "Plan ‘Grade psets’ for tomorrow morning".

Planning rules: calendar events are fixed; never exceed a part of the day's free minutes and leave a little buffer; deadlines first, then high priority; deep-focus work in the morning or afternoon, easy things midday or evening; protect some personal time. Only use task ids and area names from the data.

Reply with only a JSON object: {{"reply":"what you say","changes":[...]}}. Use an empty list when nothing should change."""


def context_for(user):
    today = timezone.localdate()
    areas = list(Area.objects.filter(user=user))
    open_tasks = Task.objects.filter(user=user, done=False).select_related("area")[:80]
    lines = [
        f"Now: {timezone.localtime():%A %B %-d, %Y %-I:%M %p}. Today is {today.isoformat()}.",
        "Areas: " + ", ".join(f"{a.name}{' (personal time)' if a.is_personal else ''}" for a in areas),
        "Open tasks:",
    ]
    for t in open_tasks:
        lines.append(json.dumps({
            "id": t.id, "title": t.title, "area": t.area.name, "due": t.due_date.isoformat() if t.due_date else None,
            "minutes": t.minutes, "priority": t.priority, "energy": t.energy,
        }))
    if not open_tasks:
        lines.append("(none)")
    gcal.ensure_fresh(user, today, days=2)
    for d in (today, today + timedelta(days=1)):
        s = days.summarize(user, d)
        lines.append(f"Plan for {d.isoformat()} ({'today' if d == today else 'tomorrow'}):")
        for slot in s.slots:
            tasks = "; ".join(f"{e.task.title} [{e.task_id}]{' (done)' if e.task.done else ''}" for e in slot.entries)
            evs = "; ".join(
                f"{timezone.localtime(ev.start):%H:%M}–{timezone.localtime(ev.end):%H:%M} {ev.title}"
                + (f" [{ev.calendar_name}]" if ev.calendar_name and not ev.is_primary else "")
                for ev in slot.events
            )
            lines.append(f"  {slot.key} ({slot.range}, {slot.free} free min): tasks: {tasks or 'none'}; calendar: {evs or 'none'}")
        if s.all_day:
            lines.append("  all day: " + "; ".join(e.title for e in s.all_day))
        top = list(s.plan.top_tasks.values_list("id", flat=True))
        if top:
            lines.append(f"  top 3: {top}")
    if not gcal.is_connected(user):
        lines.append("Google Calendar: not connected.")
    return "\n".join(lines)


def _use_quota(user):
    today = timezone.localdate()
    with transaction.atomic():
        usage, _ = AIUsage.objects.select_for_update().get_or_create(user=user, day=today)
        if usage.count >= settings.AI_DAILY_LIMIT:
            return False
        AIUsage.objects.filter(pk=usage.pk).update(count=F("count") + 1)
    return True


def remaining_today(user):
    used = AIUsage.objects.filter(user=user, day=timezone.localdate()).values_list("count", flat=True).first() or 0
    return max(0, settings.AI_DAILY_LIMIT - used)


def ask(user, text):
    """Save the user's message, ask the model, save and return the assistant's reply."""
    ChatMessage.objects.create(user=user, role="user", content=text[:4000])
    if not _use_quota(user):
        return ChatMessage.objects.create(user=user, role="assistant", content=ERROR_COPY["rate_limited"], is_error=True)
    history = list(ChatMessage.objects.filter(user=user, is_error=False).order_by("-created_at", "-id")[:HISTORY])[::-1]
    messages = [{"role": "system", "content": RULES.format(name=user.first_name or "the user") + "\n\n" + context_for(user)}]
    for m in history:
        content = m.content
        if m.role == "assistant" and m.changes:
            content += f"\n[Proposed: {'; '.join(c['label'] for c in m.changes)} — {m.status or 'pending'}]"
        messages.append({"role": m.role, "content": content})
    try:
        result = ai.complete_json(messages)
    except ai.AIError as e:
        return ChatMessage.objects.create(user=user, role="assistant", content=ERROR_COPY.get(e.code, ERROR_COPY["upstream_error"]), is_error=True)
    changes = validate_changes(user, result.get("changes"))
    reply = result.get("reply") if isinstance(result.get("reply"), str) else ""
    reply = reply.strip() or ("Here’s what I’d change:" if changes else "I don’t have anything to change.")
    return ChatMessage.objects.create(
        user=user, role="assistant", content=reply[:4000], changes=changes, status="pending" if changes else ""
    )


# ---------- validation ----------
def _date(v):
    try:
        return date_cls.fromisoformat(str(v)).isoformat()
    except ValueError:
        return None


def validate_changes(user, raw):
    """Keep only well-formed changes that point at this user's own tasks and areas."""
    if not isinstance(raw, list):
        return []
    task_ids = set(Task.objects.filter(user=user).values_list("id", flat=True))
    areas = {a.name.lower(): a.name for a in Area.objects.filter(user=user)}
    n_new = sum(1 for c in raw if isinstance(c, dict) and c.get("type") == "add_task")

    def task_ref(v):
        if isinstance(v, str) and re.fullmatch(r"new:\d+", v) and int(v[4:]) < n_new:
            return v
        try:
            v = int(v)
        except (TypeError, ValueError):
            return None
        return v if v in task_ids else None

    def common(c, out):
        if "priority" in c and c["priority"] in ("high", "normal", "low"):
            out["priority"] = c["priority"]
        if "energy" in c and c["energy"] in ("deep", "easy"):
            out["energy"] = c["energy"]
        if "minutes" in c:
            try:
                out["minutes"] = max(5, min(720, int(c["minutes"])))
            except (TypeError, ValueError):
                pass
        if "area" in c and str(c["area"]).lower() in areas:
            out["area"] = areas[str(c["area"]).lower()]
        if "due" in c:
            out["due"] = _date(c["due"]) if c["due"] else None
        return out

    out = []
    for c in raw[:25]:
        if not isinstance(c, dict):
            continue
        kind, label = c.get("type"), str(c.get("label") or "")[:200]
        if kind == "add_task" and str(c.get("title") or "").strip():
            ch = common(c, {"type": kind, "title": str(c["title"]).strip()[:160]})
            ch.setdefault("area", next(iter(areas.values()), None))
            ch["label"] = label or f"Add “{ch['title']}”"
            out.append(ch)
        elif kind == "update_task" and task_ref(c.get("task")):
            ch = common(c, {"type": kind, "task": task_ref(c["task"])})
            if str(c.get("title") or "").strip():
                ch["title"] = str(c["title"]).strip()[:160]
            if len(ch) > 2:
                ch["label"] = label or "Update a task"
                out.append(ch)
        elif kind == "complete" and task_ref(c.get("task")):
            out.append({"type": kind, "task": task_ref(c["task"]), "label": label or "Mark done"})
        elif kind == "plan" and task_ref(c.get("task")) and _date(c.get("date")) and c.get("slot") in SLOT_KEYS:
            out.append({"type": kind, "task": task_ref(c["task"]), "date": _date(c["date"]), "slot": c["slot"],
                        "label": label or "Plan a task"})
        elif kind == "unplan" and task_ref(c.get("task")) and _date(c.get("date")):
            out.append({"type": kind, "task": task_ref(c["task"]), "date": _date(c["date"]), "label": label or "Take off the plan"})
        elif kind == "set_top3" and _date(c.get("date")) and isinstance(c.get("tasks"), list):
            ids = [r for r in (task_ref(v) for v in c["tasks"]) if r][:3]
            if ids:
                out.append({"type": kind, "date": _date(c["date"]), "tasks": ids, "label": label or "Set the top 3"})
        elif kind == "block_time" and task_ref(c.get("task")) and _date(c.get("date")):
            m = re.fullmatch(r"(\d{1,2}):(\d{2})", str(c.get("start") or ""))
            try:
                minutes = max(5, min(720, int(c.get("minutes") or 0)))
            except (TypeError, ValueError):
                minutes = 0
            if m and int(m.group(1)) < 24 and int(m.group(2)) < 60 and minutes:
                out.append({"type": kind, "task": task_ref(c["task"]), "date": _date(c["date"]),
                            "start": f"{int(m.group(1)):02d}:{m.group(2)}", "minutes": minutes,
                            "label": label or "Block time on your calendar"})
    return out


# ---------- applying ----------
def apply(user, message, chosen):
    """Apply the chosen changes (indexes into message.changes). Returns a list of problems to show."""
    if message.user_id != user.id or message.status != "pending":
        return ["These changes were already handled."]
    chosen = sorted({i for i in chosen if 0 <= i < len(message.changes)})
    problems, new_ids, blocks = [], [], []
    areas = {a.name: a for a in Area.objects.filter(user=user)}
    fallback_area = next(iter(areas.values()), None)

    def task_for(ref):
        if isinstance(ref, str) and ref.startswith("new:"):
            idx = int(ref[4:])
            return Task.objects.filter(user=user, id=new_ids[idx]).first() if idx < len(new_ids) and new_ids[idx] else None
        return Task.objects.filter(user=user, id=ref).first()

    with transaction.atomic():
        for i, c in enumerate(message.changes):
            if c["type"] == "add_task":
                if i not in chosen:
                    new_ids.append(None)
                    continue
                t = Task.objects.create(
                    user=user, area=areas.get(c.get("area")) or fallback_area, title=c["title"],
                    due_date=c.get("due"), minutes=c.get("minutes", 30), priority=c.get("priority", "normal"),
                    energy=c.get("energy", "deep"),
                )
                new_ids.append(t.id)
                continue
            if i not in chosen:
                continue
            t = task_for(c.get("task")) if "task" in c else None
            if "task" in c and not t:
                problems.append(f"Skipped “{c['label']}”: that task no longer exists.")
                continue
            if c["type"] == "update_task":
                for key, field in (("title", "title"), ("minutes", "minutes"), ("priority", "priority"), ("energy", "energy"), ("due", "due_date")):
                    if key in c:
                        setattr(t, field, c[key])
                if c.get("area") in areas:
                    t.area = areas[c["area"]]
                t.save()
            elif c["type"] == "complete":
                t.set_done(True)
                t.save(update_fields=["done", "done_at"])
            elif c["type"] in ("plan", "block_time"):
                d = date_cls.fromisoformat(c["date"])
                slot = c.get("slot")
                if c["type"] == "block_time":
                    hh, mm = map(int, c["start"].split(":"))
                    slot = PlanEntry.slot_for_minute(hh * 60 + mm)
                    blocks.append((t, d, hh * 60 + mm, c["minutes"], c["label"]))
                days.plan_task(user, t, d, slot)
            elif c["type"] == "unplan":
                PlanEntry.objects.filter(plan__user=user, plan__date=c["date"], task=t).delete()
            elif c["type"] == "set_top3":
                plan = DayPlan.for_date(user, date_cls.fromisoformat(c["date"]))
                tasks = [x for x in (task_for(r) for r in c["tasks"]) if x]
                plan.top_tasks.set(tasks[:3])
        message.status = "applied"
        message.applied = chosen
        message.save(update_fields=["status", "applied"])

    for t, d, start, minutes, label in blocks:
        try:
            gcal.create_block(user, t, d, start, minutes)
        except gcal.CalendarError as e:
            problems.append(f"Couldn’t add “{label}” to Google Calendar. {e}")
    return problems


def skip(user, message):
    if message.user_id == user.id and message.status == "pending":
        message.status = "skipped"
        message.save(update_fields=["status"])
