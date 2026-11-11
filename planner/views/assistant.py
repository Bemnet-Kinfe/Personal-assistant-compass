"""The assistant chat: ask, then approve or skip its proposed changes."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from ..forms import AskForm
from ..models import ChatMessage
from ..services import assistant
from .common import changed, is_htmx

SUGGESTIONS = ["Plan my day", "What’s due this week?", "What can I push to tomorrow?", "Help with my daily check-in", "Plan my week"]


def chat_context(user):
    return {
        "chat": ChatMessage.objects.filter(user=user).order_by("-created_at", "-id")[:30][::-1],
        "suggestions": SUGGESTIONS,
        "ai_left": assistant.remaining_today(user),
        "ai_on": bool(settings.OPENROUTER_API_KEY),
        "ask_form": AskForm(),
    }


@login_required
@require_POST
def assistant_ask(request):
    form = AskForm(request.POST)
    if form.is_valid():
        assistant.ask(request.user, form.cleaned_data["text"])
    if is_htmx(request):
        return render(request, "planner/partials/assistant.html", chat_context(request.user))
    return redirect("home")


@login_required
@require_POST
def assistant_apply(request, pk):
    msg = get_object_or_404(ChatMessage, user=request.user, pk=pk, role="assistant")
    chosen = [int(i) for i in request.POST.getlist("change") if i.isdigit()]
    problems = assistant.apply(request.user, msg, chosen)
    for p in problems[1:]:
        messages.warning(request, p)
    return changed(request, problems[0] if problems else "Done")


@login_required
@require_POST
def assistant_skip(request, pk):
    assistant.skip(request.user, get_object_or_404(ChatMessage, user=request.user, pk=pk))
    return changed(request)


@login_required
@require_POST
def assistant_clear(request):
    ChatMessage.objects.filter(user=request.user).delete()
    return changed(request, "Started a new chat")
