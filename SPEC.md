# AbiertoClaw — Build Spec

> **Status:** kickoff spec, v2. Self-contained. Drop it into a fresh repo / CLI
> session and build from it top-to-bottom. It distills hard-won lessons from the
> **Iris** project (a working OpenClaw-based iMessage+calendar assistant) so
> AbiertoClaw doesn't re-learn them.
>
> **Origin:** AbiertoClaw = an "openclaw dupe," spiritually modeled on
> `cyberpapiii/chipotlai-max` (an agent runtime that defaults to a free model) —
> but built as a **reusable assistant layer**, not a runtime fork, and shipped as
> a **public repo anyone can run**.
>
> **v2 changes:** model access is now a swappable **source** layer (OpenRouter /
> OpenCode Zen / bring-your-own / local), backed by a single OpenAI-compatible
> driver. Added: conversation memory, observability + cost tracking, testing
> strategy, rate-limit handling, concrete schemas, and a glossary.

---

## 0. One-line definition

**A capable, free-by-default personal "claw" (AI assistant) with an iMessage
frontend and a CLI frontend, calendar support, and a semi-local model router
that runs cheap/free for everyday chat and automatically upgrades to a stronger
model only when a request is genuinely complex — with model access swappable
between OpenRouter, OpenCode Zen, your own API key, or a fully-local model.**

---

## 1. Goals & non-goals

### Goals
1. **Free by default.** Out of the box it runs on local (Ollama) and/or a free
   hosted tier. No credit card required to get a working assistant.
2. **Model source is the user's choice.** A first-class, swappable decision:
   **OpenRouter**, **OpenCode Zen**, **bring-your-own API** (any OpenAI-compatible
   endpoint / direct provider key), or **local Ollama**. Mix sources per tier.
3. **Self-upgrading on complexity.** A semi-local router classifies each message
   and escalates only hard requests to a stronger model.
4. **Two frontends, one brain.** Talk to it via **iMessage** (preferred) *or* a
   **CLI**. Same engine, handlers, and memory.
5. **Calendar support.** Answer schedule questions and create/edit/cancel events
   — *deterministically* for high-stakes writes (no hallucinated events).
6. **Easily extensible.** Adding a skill, a model source, or a frontend is a
   documented drop-in — not code surgery.
7. **Publishable.** A stranger clones the repo, runs a setup wizard, and has a
   working CLI assistant in minutes. iMessage is an opt-in Mac add-on.

### Non-goals (explicit, to keep scope honest)
- **Not** a fork of an agent runtime. AbiertoClaw is the *assistant layer*; it
  calls models directly through the source layer (§4). Forking a runtime is
  months of maintenance for no user benefit here.
- **No reverse-engineered "free company bot" endpoints** (the chipotlai "Pepper"
  trick). Decision: **legitimate sources only** — local + free/paid API tiers.
  Reverse-engineered endpoints break without notice, violate ToS, and create
  takedown risk for a public repo. The source layer is pluggable, so the
  *community* could add such a thing as an unofficial plugin, but we neither ship
  nor depend on one.
- **Not** trying to make iMessage portable. It is Mac-only by nature (§2).

---

## 2. Honest constraints (read before designing anything)

Non-negotiable realities. Design *around* them.

1. **iMessage is Mac-only and needs an always-on Mac.** It requires `Full Disk
   Access` to read `~/Library/Messages/chat.db`, and sending goes through Apple
   Events (slow: a send can take >60s from a background job).
   → **CLI is the universal path; iMessage is the premium Mac add-on.** Lead the
   README with CLI.

2. **"Free" and "capable" are in tension.** Free-tier hosted models and small
   local models are weak at *agentic tool-calling* — they narrate "I'll add that
   event" without doing it. Reliable tool-use needs a capable (~8B+ / frontier)
   model. → **High-stakes structured actions (calendar writes, anything costly if
   wrong) run in a DETERMINISTIC tier — plain code, no model.** The model only
   does language: chat, classification, fuzzy parsing.

3. **Free models are unstable and rate-limited.** Free OpenRouter / OpenCode Zen
   models get rate-limited (429s), deprecated, made paid, or removed frequently;
   Zen explicitly markets some as "free for a limited time." → The morning picker
   (§7) must **smoke-test + fall back**, and the request path must **handle 429s
   by rotating** to the next candidate. Never assume today's free pick survives
   to tomorrow.

4. **Unattended senders double-act.** Retries/timeouts WILL happen. → Every
   send/action needs an **idempotency key** (date, message id, or "does this
   event already exist?" check).

5. **Message content is untrusted input.** A message body (especially from a
   group) can contain prompt-injection ("ignore your rules and…"). → The model
   tier has no tools and a hard guardrail; destructive deterministic actions
   (event cancel/delete) confirm before acting.

---

## 3. Architecture

```
                    ┌─────────────────────────────────────────┐
   iMessage  ─────▶ │   FRONTEND ADAPTERS (thin)              │
   (Mac only)       │   - imessage: watch chat.db, send       │
   CLI / stdin ───▶ │   - cli: read stdin, print stdout       │
                    │   - (future: web, telegram, ...)        │
                    └───────────────────┬─────────────────────┘
                                        │ normalized Message
                                        ▼
                    ┌─────────────────────────────────────────┐
                    │   ENGINE (the brain — frontend-agnostic) │
                    │   1. ROUTER: intent + complexity         │
                    │   2. DETERMINISTIC HANDLERS (no model):  │
                    │        calendar CRUD, schedule Q&A, cmds │
                    │   3. MODEL TIER (language only):         │
                    │        complexity-routed chat            │
                    │   4. MEMORY + IDEMPOTENCY + STATE        │
                    └───────────────────┬─────────────────────┘
                                        │
              ┌─────────────────────────┼───────────────┬───────────────┐
              ▼                         ▼               ▼               ▼
      SOURCE LAYER (§4)           SKILLS/TOOLS     CONFIG+IDENTITY   OBSERVABILITY
      OpenRouter / Zen /          (calendar, …)    (persona,         (logs, cost,
      BYO / Ollama                                 secrets)          metrics)
```

### 3.1 Engine ↔ frontend split (the key refactor vs. Iris)
In Iris the iMessage watcher *is* the engine. AbiertoClaw **separates** them:
- **Frontend adapter:** turns a channel event into a normalized `Message` and
  knows how to `send(thread_id, text)`. Stateless re: logic.
- **Engine:** `handle(Message) -> Reply | None`. Pure, testable from the CLI with
  zero Mac dependencies. This is what makes "iMessage *or* CLI" trivial and the
  project runnable by anyone.

### 3.2 Core schemas
```jsonc
// Message (frontend -> engine)
{
  "text": "add dentist at 3pm friday",
  "sender_id": "ben",
  "thread_id": "group:1303",
  "channel": "imessage" | "cli" | "...",
  "is_direct": true,            // PM/CLI = true; group = false
  "ts": "2026-06-05T16:00:00Z",
  "message_id": "p:42"          // idempotency key for the frontend
}

// Reply (engine -> frontend)
{
  "text": "Added “Dentist” Fri Jun 6, 3:00 PM. ✅",
  "tier": "deterministic" | "local" | "free" | "strong",
  "meta": { "model": "...", "usage": {...}, "cost_usd": 0.0 }  // for logging
}
```

### 3.3 The two-tier rule (most important design principle)
- **Deterministic tier (code, no model):** structured + high-stakes — calendar
  CRUD, explicit commands, schedule queries, the optional briefing. Fast, free,
  *cannot hallucinate*, runs unattended.
- **Model tier (LLM):** only open-ended conversation and fuzzy judgment. In the
  chat path the model has **no tools** and a hard "never fabricate facts/dates"
  guardrail, so it can't invent calendar data.

> Rule: add a *deterministic* handler for anything (a) structured and (b)
> costly-if-wrong. Send to the model only what genuinely needs language.

---

## 4. Model sources — the gateway abstraction (the v2 centerpiece)

"Where do the models come from" is a **swappable source**, chosen at setup and
overridable per tier. Four first-class sources ship in v1; all but local Ollama
are **OpenAI chat-completions compatible**, so a single driver handles them.

| Source | What it is | Base URL | Auth env | Free models? | Best for |
|--------|-----------|----------|----------|--------------|----------|
| **OpenRouter** | Broadest catalog, programmatic `/models` w/ pricing | `https://openrouter.ai/api/v1` | `OPENROUTER_API_KEY` | Yes — filter `pricing==0` | Default; the auto-picker (§7) works cleanly here |
| **OpenCode Zen** | Curated, coding-optimized models, sold at cost | `https://opencode.ai/zen/v1` | `OPENCODE_ZEN_API_KEY` | Yes — rotating, "free for a limited time" (MiMo, Nemotron Ultra, Big Pickle, Qwen Plus Free, MiniMax Free) | Coding-grade free/cheap models; teams |
| **Bring-your-own** | Any OpenAI-compatible endpoint / direct key (OpenAI, Anthropic-compat, Groq, Together, Fireworks, local vLLM, LM Studio) | user-set | user-set | depends | Users with an existing key / their own infra |
| **Local (Ollama)** | On-device models, fully private, free | `http://127.0.0.1:11434` | none | n/a (free) | Privacy; the trivial/Tier-0 slot |

### 4.1 The insight that collapses complexity
OpenRouter, OpenCode Zen, and almost every BYO provider expose
`POST {base}/chat/completions` in the OpenAI shape. So you implement **one**
`openai-compatible` driver, parameterized by config — *not* a bespoke provider
per vendor:

```jsonc
// config/sources.json
{
  "default": "openrouter",
  "sources": {
    "openrouter": {
      "driver": "openai-compatible",
      "base_url": "https://openrouter.ai/api/v1",
      "api_key_env": "OPENROUTER_API_KEY",
      "models_endpoint": "/models",          // used by the auto-picker
      "free_filter": "pricing"               // detect free via pricing fields
    },
    "zen": {
      "driver": "openai-compatible",
      "base_url": "https://opencode.ai/zen/v1",
      "api_key_env": "OPENCODE_ZEN_API_KEY",
      "models_endpoint": "/models",
      "free_filter": "curated"               // Zen free set is curated/rotating, not a pricing flag
    },
    "byo": {
      "driver": "openai-compatible",
      "base_url": "${BYO_BASE_URL}",         // e.g. https://api.groq.com/openai/v1
      "api_key_env": "BYO_API_KEY",
      "models_endpoint": "/models",
      "free_filter": "manual"                // user pins models; no auto-pick
    },
    "local": {
      "driver": "ollama",
      "base_url": "http://127.0.0.1:11434"   // native /api/chat — NOT /v1 (see §17)
    }
  }
}
```

### 4.2 Driver interface (implement two drivers in v1)
```
Driver.chat(messages, model, opts) -> { text, usage } | raises RateLimited | raises ProviderError
Driver.list_models() -> [{ id, context, pricing?, free?, ... }]   # optional; powers §7
```
- **`openai-compatible`** — POST `{base_url}/chat/completions`, body in OpenAI
  shape, `Authorization: Bearer ${api_key_env}`. Covers OpenRouter, Zen, BYO.
  Map HTTP 429 → `RateLimited` so the router can rotate (§7.3).
- **`ollama`** — POST `{base_url}/api/chat`. ⚠️ Native API, **no `/v1`** — `/v1`
  + OpenAI-completions shape *silently breaks tool calling* on Ollama. (Iris's
  single biggest red herring.)

> **Model id note:** the `model` field is the source's native id. OpenRouter:
> `google/gemini-flash-lite`. Zen: in opencode's own config it's `opencode/<id>`;
> when calling the raw `/v1/chat/completions` endpoint, verify whether the field
> wants the bare id (`gpt-5.5`) or the prefixed form — **confirm at build time**
> with one curl. BYO: whatever that endpoint expects.

> **Plugin path:** a new source is a JSON entry (if OpenAI-compatible) or a new
> driver module + registry entry. Community novelty endpoints can be added this
> way; we don't ship them.

---

## 5. Model strategy: free by default, self-upgrading

### 5.1 Roles (tiers) — decoupled from sources
A model is referenced by **role**, and each role maps to a `(source, model)`
pair. This is what lets the same router run on anyone's chosen source.

```jsonc
// config/models.json
{
  "roles": {
    "local":  { "source": "local",      "model": "qwen2.5:7b" },        // Tier 0: trivial, private, free
    "free":   { "source": "openrouter", "model": "<auto>", "constraint": "free" }, // Tier 1: everyday chat (picked each morning)
    "strong": { "source": "openrouter", "model": "<auto-or-pinned>" }   // Tier 2: complex escalation (free if available, else opt-in paid)
  }
}
```

| Tier | Role | Default | Used for |
|------|------|---------|----------|
| 0 | `local`  | Ollama small (free, private) | trivial/transactional, the complexity classifier |
| 1 | `free`   | best free model on the chosen source (auto, §7) | everyday conversation |
| 2 | `strong` | best free strong model, or opt-in cheap paid | complex / ambiguous / multi-step |

Out of the box Tiers 0–1 are 100% free. Tier 2 defaults to the best *free* strong
model; the user may optionally point it at a cheap paid model for better hard-task
reliability. **Paid is never required.** A role can point at any source, so a user
can run e.g. `local` on Ollama, `free` on Zen, `strong` on their own Anthropic key.

---

## 6. The semi-local complexity router (answer to "is that possible?")

**Yes — Iris already runs this.** The dispatcher is cheap/on-device; the strong
model is rented only when needed.

### 6.1 Flow
```
route(message):
  intent = classify_intent(message)            # cheap rules
  if intent is structured/high-stakes:         # calendar add/edit/cancel, command, schedule Q
      return DETERMINISTIC handler             # no model at all
  level = classify_complexity(message)         # simple | complex
  role  = "local" if level == simple else "strong"   # or "free" for the middle
  return model_reply(role, message)
```

### 6.2 `classify_complexity` — cheap heuristics first (no model call to pick a model)
Score, then threshold:
- **simple** (→ `local`/`free`): short (<~15 words), single question,
  transactional, matches a known command, or a direct follow-on to the last turn.
- **complex** (→ `strong`): multi-part, multiple questions, planning/brainstorm,
  ambiguous pronoun/reference resolution, long, or "parse this messy thing."
- **Force-escalate rule:** anything that *looks like* it needs a tool/judgment
  but isn't a clean deterministic match → `strong` (better to spend than to
  fumble).
- **Borderline:** optionally let the **local model** emit a one-token
  `SIMPLE/COMPLEX` verdict — still cheap, still on-device. Keep the dispatcher
  local so you never pay a model just to choose a model.

Maintain a small **golden set** of labeled messages (§15) so changes to the
classifier are regression-tested.

---

## 7. The morning best-free-model picker (headline feature) — now source-aware

A scheduled job that each morning updates the `free` (and optionally `strong`)
role to the best currently-available free model **on the active source**.

### 7.1 Candidate discovery (per source `free_filter`)
- **`pricing`** (OpenRouter): `GET /models` → keep where
  `pricing.prompt == "0" && pricing.completion == "0"`.
- **`curated`** (OpenCode Zen): Zen's free set rotates and isn't a clean pricing
  flag. Maintain a small **known-free allowlist** (config) + optionally probe
  `/models` for ids tagged/ending in a free marker; treat the allowlist as truth.
- **`manual`** (BYO): no auto-discovery — the user pins the model; the picker is a
  no-op (just re-validates it still answers).

### 7.2 Rank → smoke-test → commit
1. **Rank** candidates by a capability heuristic: larger context length; a small
   weighted allowlist of known-capable family substrings; **de-prioritize pure
   "reasoning" models for chat** (slow — Iris measured ~6.6s vs ~1.1s for a flash
   model); penalize models with bad recent latency/error EMA from prior days
   (stored in state).
2. **Smoke-test** the top candidate: one tiny prompt ("reply OK") must return
   non-empty within a timeout.
3. **Commit** the winner to `models.json` `roles.free.model`. On failure, try the
   next candidate. If all fail → **keep yesterday's pick** and log a warning.
   Never leave a role pointing at a dead model.
4. **Log** the choice + reason ("today's free model is X: 1M ctx, passed smoke
   test, p50 latency 1.1s") so the user can see what's driving.

### 7.3 Request-time resilience (independent of the morning job)
Fallback chain on every call: `roles.free` → on `RateLimited`/empty/error →
**next-best free candidate** → `roles.local` → (if configured) `roles.strong`.
A reply must never silently drop. Respect `Retry-After` on 429s.

---

## 8. Conversation state & memory

- **Per-thread history:** keep the last N turns per `thread_id` (ring buffer),
  persisted to `state/` (JSON or SQLite). The CLI and iMessage frontends share
  the same store keyed by thread, so context survives restarts.
- **Context budget:** persona/bootstrap docs + history + the user turn must fit
  the model's context. Inject persona **once per conversation** by default (token
  saver), with an `always` option for stricter models. Trim oldest turns first;
  never trim the persona/guardrail.
- **Summarization (optional, later):** when a thread exceeds budget, summarize
  older turns into a compact "memory" note rather than dropping them.
- **No secrets in history** that gets sent to a hosted source — see §13 privacy.

---

## 9. Frontends

### 9.1 CLI (build first — universal, no Mac needed)
- `abiertoclaw chat` — interactive REPL: read line → `engine.handle()` → print.
- `abiertoclaw say "<text>"` — one-shot.
- Normalized `Message` with `channel:"cli"`, `is_direct:true`. This is the dev
  harness AND a real frontend; everything is testable here.

### 9.2 iMessage (preferred; Mac add-on)
- **Watcher:** poll `chat.db` (or reuse an `imsg`-style CLI) every N seconds; track
  per-thread `last_id` (idempotency — never reprocess).
- **Sender:** send via Messages (Apple Events). Treat a >60s timeout as
  *delivered*, not failed (don't re-send). Subprocess timeout ~180s.
- **Addressing:** answer a direct/PM thread always; in a group, only when
  addressed by the assistant's configured name — keeps it out of human banter.
- **Single-instance lock** so overlapping polls don't double-send.
- Document the Full Disk Access grant for **both** the messaging binary and the
  runtime/python in `docs/SETUP_IMESSAGE.md`.

> Both frontends call the identical engine. Adding Telegram/web later = one
> adapter, zero engine changes.

---

## 10. Calendar & skills (extensibility)

### Calendar (deterministic tier)
- Abstract the calendar behind a skill: `list(range)`, `create(event)`,
  `update(id, patch)`, `cancel(id)` (Iris used a Google `gog`-style CLI with
  file-keyring auth; any backend works behind this interface).
- **Writes go through deterministic handlers**, never raw model output:
  - `add X at TIME on DATE` / invitation → parse → `create` (dedupe via
    `event_exists()`).
  - Edit/cancel → the model may *propose* a structured change **against real
    fetched events** (can't invent IDs); code **validates + executes**, then
    confirms what changed. **Cancel/delete confirms before acting** (§2.5).
  - Schedule questions → fetch real events → answer from data (never let a
    tool-less model freelance dates).

### Skills/plugins
- A **skill** = a documented capability: a manifest declaring its intents + a
  handler the engine dispatches to by intent name. Adding one must not require
  editing the router core.
- Persona/behavior is authored as docs (§12), not code.

---

## 11. Config-driven identity (de-personalize — this is a public repo)

Iris is hardcoded to one household. AbiertoClaw must be **config-driven**.
- `config/identity.json` — assistant name, owner name(s), timezone, locale,
  enabled channels, group/thread ids (iMessage), schedule.
- **Persona as bootstrap docs** auto-injected into the model's system context:
  `persona/SOUL.md` (voice), `persona/AGENTS.md` (rules/guardrails — "never
  fabricate dates"), `persona/USER.md` (people), optional `persona/HEARTBEAT.md`
  (proactive checks).
- Ship **sanitized `*.example`** files; never real personal data.

---

## 12. Secrets, privacy & safety

- **No secret in any committed file.** Keys live at `~/.abiertoclaw/<name>_key`
  (chmod 600) and are read via the `api_key_env` indirection — never written into
  `sources.json`, `models.json`, identity config, logs, or the repo.
- `.gitignore` blocks: `*_key*`, `*_api_key*`, `*keyring*`, `*credentials*`,
  `*.token`, `*.pem`, `*.key`, `state/`, `logs/`, `*.log`, `node_modules/`, OAuth
  client JSON.
- **Privacy is per-source and per-tier** — call it out in the README:
  - `local` (Ollama): text stays on-device.
  - `openrouter`/`zen`/`byo-hosted`: the message + history go to that gateway and
    the underlying model provider. (Note OpenRouter/Zen data-retention settings.)
  - Deterministic tiers (calendar/briefing) stay local regardless of source.
  - Let users choose which tier is allowed to leave the device.
- **Untrusted input:** message bodies may contain prompt-injection; the chat model
  has no tools, and destructive deterministic actions confirm first.

---

## 13. Observability & cost

- **Structured logs** per interaction: timestamp, thread, intent, tier, source,
  model, latency, token usage, est. cost, outcome. One line per turn (JSONL in
  `logs/`), plus human-readable rotation.
- **Cost tracking** (port Iris `iris-cost`): since OpenRouter/Zen/BYO all bill,
  record per-call cost from `usage` × the source's price table; `abiertoclaw cost`
  prints a per-day / per-model rollup. Free models report `$0.00`.
- **Health surface:** `abiertoclaw doctor` validates config + secrets + source
  reachability + Ollama presence; `abiertoclaw model status` shows the active
  role→source→model map and today's free pick.

---

## 14. Testing strategy

The engine is pure, so most of it is unit-testable with no network/Mac:
- **Router/intent tests:** table-driven cases → expected handler/tier.
- **Complexity golden set:** labeled messages → expected `simple/complex`; guards
  classifier regressions.
- **Deterministic calendar tests:** parse → event; idempotency (`event_exists`);
  cancel-confirm flow. Use a fake calendar backend.
- **Provider contract tests:** a **mock `openai-compatible` server** asserting the
  driver sends the right shape and maps 429→`RateLimited`; an Ollama-shape mock.
- **Picker tests:** feed a fake `/models` payload → assert free-filter, ranking,
  smoke-test fallback to "yesterday's pick."
- **Frontend smoke:** CLI end-to-end against a stubbed engine. iMessage is
  manual/documented (needs a Mac); keep its logic thin so little is untested.

---

## 15. Repo layout (proposed)

```
abiertoclaw/
  README.md                 # CLI-first quickstart; iMessage as Mac add-on
  LICENSE                   # MIT (so it's actually reusable)
  setup.(sh|py)             # first-run wizard: pick source, drop key, smoke test
  bin/
    abiertoclaw             # chat | say | watch | model | pick-free | cost | doctor
  src/
    engine/                 # router, handlers, memory, idempotency, state (NO Mac deps)
    drivers/                # openai_compatible.py, ollama.py, base.py
    sources/                # registry + source config loading
    frontends/
      cli.py
      imessage.py
    skills/
      calendar/
    model_picker.py         # morning best-free-model job (§7)
    cost.py                 # §13
  config/
    sources.example.json    # OpenRouter / Zen / BYO / local (§4.1)
    models.example.json     # roles → (source, model) (§5.1)
    identity.example.json
  persona/
    SOUL.example.md  AGENTS.example.md  USER.example.md
  scheduling/
    launchd/                # macOS: watcher, morning picker, (optional) briefing
    systemd/ or cron/       # Linux equivalents (CLI-only deployments)
  tests/                    # §14
  docs/
    ARCHITECTURE.md
    SOURCES.md              # OpenRouter vs Zen vs BYO vs local; how to add one
    SETUP_IMESSAGE.md       # the Mac / Full-Disk-Access saga
    GOTCHAS.md              # §17, kept current
```

---

## 16. First-run wizard (setup UX — make "anyone can run it" true)

`setup` should:
1. Ask which **source** to use (OpenRouter / OpenCode Zen / bring-your-own /
   local-only). Explain free-ness + privacy of each in one line.
2. If hosted: prompt for the API key, write it to `~/.abiertoclaw/<name>_key`
   (chmod 600), set the `api_key_env` mapping. If local: check Ollama is
   installed + pull a small model.
3. Scaffold `sources.json` / `models.json` / `identity.json` from examples.
4. Run `doctor` + one smoke chat. Print "✅ free assistant ready: `abiertoclaw
   chat`."
5. Mention iMessage as an optional Mac step pointing at `docs/SETUP_IMESSAGE.md`.

---

## 17. Gotchas ported from Iris (these save you days)

1. **Ollama uses native `/api/chat`, NO `/v1`.** `/v1` silently breaks tool
   calling. OpenRouter/Zen/BYO are the opposite (`/v1` is correct). The
   `openai-compatible` driver and the `ollama` driver are deliberately separate.
2. **Weak models narrate instead of acting.** Keep high-stakes work deterministic;
   never trust a free/small model with a calendar write.
3. **Local 8B+ + big context doesn't fit 16GB comfortably** → swap/stalls. Set
   `OLLAMA_MAX_LOADED_MODELS=1`, consider `OLLAMA_KV_CACHE_TYPE=q8_0`. Prefer
   hosted for the model tier; local for trivial/private only.
4. **Reasoning models are slow** (~6.6s vs ~1.1s). Don't put one in the everyday
   chat slot; reserve for genuine hard parsing.
5. **macOS TCC:** launchd jobs can't read `chat.db` without Full Disk Access for
   *both* the messaging binary and the runtime/python. Symptom: `authorization
   denied (code 23)`.
6. **iMessage sends are slow from background** (>60s). Timeout ~180s; treat
   timeout as delivered.
7. **Idempotency everywhere unattended:** briefing records the date *before*
   sending (≤1/day); watcher uses per-thread `last_id` + `event_exists()` +
   single-instance lock.
8. **Strict JSON config** + a `validate`/`doctor` command; bad config fails loudly.
9. **Free-model churn + rate limits:** today's pick can be dead/limited tomorrow —
   smoke-test in the picker, and rotate on 429 at request time.
10. **Source id quirks:** confirm the exact `model` field each source's
    `/v1/chat/completions` expects (esp. OpenCode Zen's `opencode/` prefix) with
    one curl before wiring it.

---

## 18. Build phases (execute in order)

> Each phase ends with something runnable. Don't build frontends before the engine
> is testable from the CLI.

**Phase 1 — Engine + CLI + source layer (universal core).**
- `engine.handle(Message)` with the two-tier split + per-thread memory.
- `drivers/openai_compatible.py` + `drivers/ollama.py`; `sources.json` loading.
- `frontends/cli.py`. Goal: `abiertoclaw chat` talks to a model on the chosen
  source (local Ollama with zero keys, or a hosted free model with a key).
- ✅ Done when a stranger on Linux can clone, run `setup`, and chat for free.

**Phase 2 — Complexity router + roles + morning picker.**
- `classify_intent` + `classify_complexity` + role routing + fallback/429 chain.
- `model_picker.py` (source-aware) + a daily schedule entry; smoke-test + fallback.
- ✅ Done when chat is free, escalates on complex input, and self-updates daily.

**Phase 3 — Calendar skill (deterministic).**
- `skills/calendar` + deterministic create/edit/cancel (cancel confirms) +
  schedule Q&A; idempotent.
- ✅ Done when "add dentist at 3pm friday" reliably creates exactly one event via
  CLI.

**Phase 4 — iMessage frontend (Mac add-on).**
- `frontends/imessage.py` watcher+sender, addressing, idempotency, launchd jobs.
- `docs/SETUP_IMESSAGE.md`.
- ✅ Done when the same engine answers over iMessage on a Mac.

**Phase 5 — Observability, cost, tests, polish.**
- Structured logs, `cost`, `doctor`, `model status`; fill out `tests/`.
- ✅ Done when `doctor` is green and the test suite covers router + picker +
  calendar.

**Phase 6 — Identity + docs + publish.**
- Strip personal data; ship `*.example` config + persona; README (CLI-first),
  SOURCES.md, GOTCHAS.md, MIT LICENSE. Optional: morning briefing skill.
- ✅ Done when the public repo is clone-and-run for a stranger.

---

## 19. Reference: the Iris source to mine

Working, battle-tested pieces to port and generalize rather than reinvent:
- `bin/message-watcher.py` — intent + complexity router, deterministic calendar
  handlers, idempotency, model fallback. **The richest source.**
- `bin/iris-model` + `config/model.json` — the registry + hot-swap pattern
  (generalize into the source/role split of §4–§5).
- `bin/morning-briefing.py` — deterministic calendar-read → format → send.
- `bin/iris-cost` — per-interaction cost tracking (→ §13).
- `docs/IRIS_ARCHITECTURE.md` — the full lessons writeup (§17 is condensed from
  it). Read it before Phase 1.

---

## 20. Glossary

- **Source** — where models are fetched from: OpenRouter, OpenCode Zen,
  bring-your-own, or local Ollama. Swappable; chosen at setup, overridable per
  role.
- **Driver** — the HTTP client for a source's API shape: `openai-compatible`
  (OpenRouter/Zen/BYO) or `ollama` (native).
- **Role / tier** — `local` / `free` / `strong`; the router picks a role per
  message, and each role maps to a `(source, model)`.
- **Deterministic tier** — code paths with no model (calendar CRUD, commands);
  for structured, high-stakes work.
- **Skill** — a drop-in capability (manifest + handler) the engine dispatches to
  by intent.
- **The picker** — the morning job that selects the best free model on the active
  source for the `free` role.

---

*End of spec. Build CLI-first, keep high-stakes work out of the model, make the
source swappable, and never let the free-model picker point at something it
didn't just smoke-test.*
