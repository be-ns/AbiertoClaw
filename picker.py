"""Pick today's best free model for Hermes, with a local model as the safety net.

Pure stdlib and no Hermes imports, so it is testable on its own. The rule from
the original AbiertoClaw still holds: never commit a model that didn't just
pass a smoke test. The smoke test now demands a real tool call, because a free
model that only chats is useless to an agent like Hermes.
"""

import json
import urllib.error
import urllib.request

OPENROUTER = "https://openrouter.ai/api/v1"

# Hermes recommends at least 64K context; smaller windows break compression.
MIN_CONTEXT = 64_000

# Known-capable family substrings, best first.
PREFERRED_FAMILIES = (
    "gemini", "qwen", "deepseek", "llama", "glm", "kimi", "mistral", "gemma",
    "nemotron",
)

# Local OpenAI-compatible servers, checked in order. Provider names are Hermes'.
LOCAL_SERVERS = (
    ("custom", "http://127.0.0.1:11434/v1"),   # Ollama
    ("lmstudio", "http://127.0.0.1:1234/v1"),  # LM Studio
)

PING_TOOL = {
    "type": "function",
    "function": {
        "name": "ping",
        "description": "Health check. Always call this when asked to ping.",
        "parameters": {"type": "object", "properties": {}},
    },
}
SMOKE_MESSAGES = [{"role": "user", "content": "Call the ping tool now."}]


def http_json(url, body=None, key=None, timeout=30):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def is_candidate(model):
    """Free, tool-capable, and big enough context for an agent."""
    pricing = model.get("pricing") or {}
    try:
        free = (float(pricing.get("prompt", 1)) == 0.0
                and float(pricing.get("completion", 1)) == 0.0)
    except (TypeError, ValueError):
        return False
    return (free
            and "tools" in (model.get("supported_parameters") or [])
            and (model.get("context_length") or 0) >= MIN_CONTEXT)


def rank(models):
    """Known family + more context wins; reasoning-only variants sink (slow turns)."""
    def score(m):
        s = float(m.get("context_length") or 0) / 1_000_000
        mid = (m.get("id") or "").lower()
        for i, family in enumerate(PREFERRED_FAMILIES):
            if family in mid:
                s += (len(PREFERRED_FAMILIES) - i) * 0.5
                break
        if "thinking" in mid or "reason" in mid:
            s -= 2
        return s
    return sorted(models, key=score, reverse=True)


def smoke_test(model_id, key, http=http_json):
    """True only if the model answers with a tool call."""
    try:
        resp = http(OPENROUTER + "/chat/completions", {
            "model": model_id,
            "messages": SMOKE_MESSAGES,
            "tools": [PING_TOOL],
            "max_tokens": 200,
        }, key=key)
        message = resp["choices"][0]["message"]
        return bool(message.get("tool_calls"))
    except (urllib.error.URLError, OSError, ValueError, KeyError, IndexError, TypeError):
        return False


def find_local(http=http_json):
    """First chat model served by a local Ollama / LM Studio, as a Hermes fallback entry."""
    for provider, base_url in LOCAL_SERVERS:
        try:
            models = http(base_url + "/models", timeout=3).get("data") or []
        except (urllib.error.URLError, OSError, ValueError, AttributeError):
            continue
        for m in models:
            mid = m.get("id") or ""
            if mid and "embed" not in mid.lower():
                return {"provider": provider, "model": mid, "base_url": base_url}
    return None


def plan(key, http=http_json, keep=3, attempts=8, log=print):
    """Return {"primary": entry, "fallbacks": [entries]} or None if nothing works.

    Primary is the best free model that passed; the runners-up and any local
    model become Hermes' fallback chain, local last. With no key or no working
    free model, the local model becomes primary.
    """
    winners = []
    if key:
        try:
            models = http(OPENROUTER + "/models", key=key).get("data") or []
        except (urllib.error.URLError, OSError, ValueError, AttributeError) as e:
            log("  could not list OpenRouter models: %s" % e)
            models = []
        candidates = rank([m for m in models if is_candidate(m)])
        log("  %d free tool-capable models; smoke-testing..." % len(candidates))
        for m in candidates[:attempts]:
            if smoke_test(m["id"], key, http):
                log("  ✅ %s" % m["id"])
                winners.append({"provider": "openrouter", "model": m["id"]})
                if len(winners) == keep:
                    break
            else:
                log("  ✗ %s" % m["id"])
    else:
        log("  no OPENROUTER_API_KEY; skipping free models")

    local = find_local(http)
    log("  local: %s" % (local["model"] if local else "none found"))

    chain = winners + ([local] if local else [])
    if not chain:
        return None
    return {"primary": chain[0], "fallbacks": chain[1:]}
