"""Optional LLM enhancer. Output is always validated; any failure returns {} so the rule path wins.
The LLM only fills attributes the regex extractor left empty; it never decides a match (ADR-12).

Robustness: answers are cached (successes only, so a transient error is retried later); after several failures
in a row the provider is paused for a few minutes (circuit breaker), so a dead endpoint cannot stall an upload
of 50,000 rows with 30-second timeouts."""
import json
import logging
import os
import re
import time
from collections import OrderedDict

import httpx

from .extract import canonical_value

log = logging.getLogger(__name__)

PROMPT = """Extract material attributes from this industrial material description.
Return ONLY a JSON object with any of these keys you are confident about:
noun, thread, length_mm, size_in, size_mm, grade, rating, schedule, standard, coating.
Use uppercase values, numbers without units. Description: {text}"""

ALLOWED = {"noun", "thread", "length_mm", "size_in", "size_mm", "grade", "rating", "schedule", "standard", "coating"}
TIMEOUT_S = 30
MAX_TEXT = 1000
_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX = 20_000
_BREAK_AFTER, _BREAK_FOR_S = 5, 300.0
_breaker = {"failures": 0, "open_until": 0.0}


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "noop").strip().lower() or "noop"


def needs_llm(attrs: dict) -> bool:
    """Only descriptions the rules could not read well go to the LLM."""
    return "noun" not in attrs or len(attrs) < 3


def _parse(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        if k in ALLOWED and v not in (None, "") and (clean := canonical_value(k, v)):
            out[k] = clean
    return out


def _call(prompt: str) -> str:
    p = provider()
    with httpx.Client(timeout=TIMEOUT_S) as c:
        if p == "ollama":
            r = c.post(f"{os.getenv('OLLAMA_URL', 'http://ollama:11434').rstrip('/')}/api/generate",
                       json={"model": os.getenv("OLLAMA_MODEL"), "prompt": prompt, "format": "json", "stream": False})
            r.raise_for_status()
            return r.json()["response"]
        if p == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{os.getenv('GEMINI_MODEL')}:generateContent"
            r = c.post(url, headers={"x-goog-api-key": os.getenv("GEMINI_API_KEY", "")},
                       json={"contents": [{"parts": [{"text": prompt}]}],
                             "generationConfig": {"responseMimeType": "application/json"}})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        if p == "groq":
            r = c.post("https://api.groq.com/openai/v1/chat/completions",
                       headers={"Authorization": f"Bearer {os.getenv('GROQ_API_KEY', '')}"},
                       json={"model": os.getenv("GROQ_MODEL"), "response_format": {"type": "json_object"},
                             "messages": [{"role": "user", "content": prompt}]})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    log.warning("unknown LLM_PROVIDER %r; expected noop, ollama, gemini or groq", p)
    return ""


def llm_attributes(text: str) -> dict:
    if provider() == "noop" or not text:
        return {}
    text = text[:MAX_TEXT]
    if text in _CACHE:
        _CACHE.move_to_end(text)
        return dict(_CACHE[text])
    if time.monotonic() < _breaker["open_until"]:
        return {}                                           # provider paused after repeated failures
    try:
        out = _parse(_call(PROMPT.format(text=text)))
    except Exception as e:                                  # any failure (bad URL, odd JSON, outage): rules win
        _breaker["failures"] += 1
        if _breaker["failures"] >= _BREAK_AFTER:
            _breaker.update(failures=0, open_until=time.monotonic() + _BREAK_FOR_S)
            log.warning("LLM failed %d times in a row (%s); pausing LLM calls for %d s",
                        _BREAK_AFTER, e, _BREAK_FOR_S)
        else:
            log.warning("LLM attribute extraction failed: %s", e)
        return {}
    _breaker["failures"] = 0
    _CACHE[text] = out
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return dict(out)


def fill_gaps(attrs: dict, conf: dict, text: str, confidence: float = 0.6) -> tuple[dict, dict]:
    """Merge LLM attributes into the regex result without overwriting anything the regex found."""
    extra = {k: v for k, v in llm_attributes(text).items() if k not in attrs}
    return {**attrs, **extra}, {**conf, **{k: confidence for k in extra}}
