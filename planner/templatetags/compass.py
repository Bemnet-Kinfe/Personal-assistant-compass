from datetime import timedelta

from django import template
from django.utils import timezone

from ..utils import fmt_minutes

register = template.Library()


@register.filter
def mins(value):
    return fmt_minutes(value)


@register.filter
def rel_day(d):
    today = timezone.localdate()
    if d == today:
        return "Today"
    if d == today + timedelta(days=1):
        return "Tomorrow"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return f"{d:%a %b} {d.day}"


@register.filter
def day_phrase(d):
    """For mid-sentence use: 'today', 'tomorrow', 'Fri Nov 13'."""
    label = rel_day(d)
    return label.lower() if label in ("Today", "Tomorrow", "Yesterday") else label


@register.filter
def due_text(d):
    """'Due today', 'Due tomorrow', 'Due Fri Nov 13'."""
    label = rel_day(d)
    return f"Due {label.lower()}" if label in ("Today", "Tomorrow", "Yesterday") else f"Due {label}"


@register.filter
def due_state(task):
    if not task.due_date or task.done:
        return ""
    today = timezone.localdate()
    if task.due_date < today:
        return "bad"
    if task.due_date == today:
        return "warn"
    return ""


@register.filter
def event_color(ev):
    """One palette for every calendar: Compass blocks wear their area color, Canvas is blue, your own calendar coral."""
    if ev.area_id:
        return f"var(--c-{ev.area.color})"
    name = (ev.calendar_name or "").lower()
    if ev.is_primary:
        return "var(--c-coral)"
    if "canvas" in name:
        return "var(--c-blue)"
    if "holiday" in name:
        return "var(--c-slate)"
    palette = ["violet", "teal", "amber", "pink", "cyan"]
    return f"var(--c-{palette[sum(map(ord, ev.calendar_id)) % len(palette)]})"


@register.filter
def event_label(ev):
    if ev.area_id:
        return ev.area.name
    if ev.is_primary:
        return "Calendar"
    name = ev.calendar_name or "Calendar"
    if "canvas" in name.lower():
        return "Canvas"
    return name[:22]


@register.simple_tag
def is_top(task, top_ids):
    return task.id in top_ids
