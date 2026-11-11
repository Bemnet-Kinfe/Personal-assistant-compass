"""One call to the model through OpenRouter. Server-side only: the key never reaches the browser."""
import json
import logging
import re

import requests
from django.conf import settings

log = logging.getLogger(__name__)
URL = "https://openrouter.ai/api/v1/chat/completions"


class AIError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code  # not_configured | upstream_error | invalid_json


def parse_json(text):
    """Read a JSON object from a model reply, tolerating a code fence or words around it."""
    text = (text or "").strip()
    candidates = [text]
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        candidates.append(fence.group(1))
    a, b = text.find("{"), text.rfind("}")
    if a != -1 and b > a:
        candidates.append(text[a : b + 1])
    for c in candidates:
        try:
            data = json.loads(c)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    raise AIError("invalid_json")


def complete_json(messages):
    """Send chat messages and return the reply as a dict. Tries the fallback models if the first is down."""
    if not settings.OPENROUTER_API_KEY:
        raise AIError("not_configured")
    payload = {
        "model": settings.AI_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
    }
    if settings.AI_FALLBACK_MODELS:
        payload["models"] = [settings.AI_MODEL, *settings.AI_FALLBACK_MODELS]
    try:
        r = requests.post(
            URL,
            headers={"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "X-Title": settings.APP_NAME},
            json=payload,
            timeout=90,
        )
    except requests.RequestException as e:
        log.warning("openrouter request failed: %s", e)
        raise AIError("upstream_error")
    if r.status_code != 200:
        log.warning("openrouter error %s: %s", r.status_code, r.text[:300])
        raise AIError("upstream_error")
    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIError("upstream_error")
    return parse_json(content)
