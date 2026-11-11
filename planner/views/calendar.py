"""Google Calendar: refresh on demand."""
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.views.decorators.http import require_POST

from ..services import gcal
from .common import changed, toast_only


@login_required
@require_POST
def calendar_sync_now(request):
    try:
        n = gcal.sync(request.user, timezone.localdate(), days=7)
    except gcal.CalendarError as e:
        return toast_only(request, str(e), "settings")
    return changed(request, f"Calendar synced: {n} events this week", "plan")
