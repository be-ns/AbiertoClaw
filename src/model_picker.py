"""Best-free-model picker (SPEC §7, Phase-1 slice).

Used by setup (and later by the morning job) to find a free model on the
active source that actually answers. Rule: never commit a model that didn't
just pass a smoke test.
"""

from .drivers import ProviderError, RateLimited

# Known-capable family substrings, best first (SPEC §7.2 ranking heuristic).
PREFERRED_FAMILIES = (
    "gemini", "llama", "qwen", "deepseek", "mistral", "gemma", "glm", "nemotron",
)
SMOKE_PROMPT = [{"role": "user", "content": "Reply with the single word: OK"}]


def is_free(model):
    pricing = model.get("pricing") or {}
    try:
        return (
            float(pricing.get("prompt", 1)) == 0.0
            and float(pricing.get("completion", 1)) == 0.0
        )
    except (TypeError, ValueError):
        return False


def rank(models):
    """Higher context + known family wins; reasoning models sink (slow chat)."""
    def score(m):
        s = float(m.get("context_length") or 0) / 1_000_000
        mid = (m.get("id") or "").lower()
        for i, family in enumerate(PREFERRED_FAMILIES):
            if family in mid:
                s += (len(PREFERRED_FAMILIES) - i) * 0.5
                break
        if "reason" in mid or "thinking" in mid:
            s -= 2
        return s
    return sorted(models, key=score, reverse=True)


def smoke_test(driver, model_id, timeout=30):
    try:
        result = driver.chat(SMOKE_PROMPT, model_id, opts={"timeout": timeout})
        return bool(result["text"])
    except (RateLimited, ProviderError):
        return False


def pick_free(source, attempts=5, log=print):
    """Return the best free model id on a pricing-filtered source, or None."""
    try:
        models = source.driver.list_models()
    except ProviderError as e:
        log("  could not list models: %s" % e)
        return None
    candidates = rank([m for m in models if is_free(m)])
    if not candidates:
        log("  no free models found on %s" % source.name)
        return None
    log("  %d free models on %s; smoke-testing the top picks..."
        % (len(candidates), source.name))
    for model in candidates[:attempts]:
        mid = model["id"]
        if smoke_test(source.driver, mid):
            log("  ✅ %s answered" % mid)
            return mid
        log("  ✗ %s failed smoke test, trying next" % mid)
    return None
