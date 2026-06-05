"""Intent + complexity routing (SPEC §6).

Cheap heuristics only — never pay a model just to choose a model. Scores a
message and thresholds it into simple (everyday model) or complex (strong
model). Phase 2 grows this into the full role/escalation router; the rules
here are the §6.2 baseline and are covered by the golden set in tests/.
"""

import re

COMPLEX_KEYWORDS = (
    "plan", "brainstorm", "compare", "draft", "summarize", "analyze",
    "explain why", "pros and cons", "step by step", "rewrite", "debug",
    "strategy", "tradeoff", "trade-off",
)

_MULTI_PART = re.compile(r"(^|\n)\s*(\d+[.)]|[-*])\s+\S", re.MULTILINE)


def classify_intent(text):
    """commands are deterministic; everything else goes to chat (for now)."""
    stripped = text.strip()
    if stripped.startswith("/"):
        return "command"
    return "chat"


def classify_complexity(text):
    """Return 'simple' or 'complex' from cheap signals (SPEC §6.2)."""
    stripped = text.strip()
    words = stripped.split()
    score = 0
    if len(words) > 40:
        score += 2
    elif len(words) > 15:
        score += 1
    if stripped.count("?") > 1:
        score += 2
    lowered = stripped.lower()
    if any(kw in lowered for kw in COMPLEX_KEYWORDS):
        score += 2
    if _MULTI_PART.search(stripped):
        score += 2
    if len(stripped) > 400:
        score += 2
    return "complex" if score >= 2 else "simple"
