# AbiertoClaw

A personal AI assistant that costs nothing to run. Clone the repo, answer four
questions, and you're chatting. The model runs on a free hosted service, your
own API key, or locally so nothing leaves your machine.

The name: *abierto* is Spanish for open. This is an open, free-by-default take
on the "claw" assistant pattern. It's a reusable assistant layer, not a fork of
someone else's agent runtime.

## Quickstart

You need Python 3.9+, which macOS and most Linux distros already include.
Nothing to install beyond that... no pip, no node, no containers.

```sh
git clone https://github.com/be-ns/AbiertoClaw.git
cd AbiertoClaw
./setup
```

The wizard asks what to call the assistant, your name, and where models should
come from:

| Source | What you need | Who sees your messages |
|--------|---------------|------------------------|
| OpenRouter | a free account and API key | OpenRouter, then whichever provider runs the model |
| OpenCode Zen | an API key | Zen, then whichever provider runs the model |
| Bring your own | any OpenAI-compatible endpoint (Groq, Together, a vLLM box) | wherever that endpoint lives |
| Local (Ollama) | Ollama installed | nowhere... it all stays on your machine |

Pick OpenRouter and the wizard finds today's best free model for you. It pulls
the catalog, keeps the genuinely free entries, and smoke-tests the top picks
until one answers. Pick local and it uses whatever you've already pulled into
Ollama.

Setup ends with a health check and one real reply from your chosen model. If
something is broken, it says exactly what to fix.

Then talk to it:

```sh
bin/abiertoclaw chat
```

## What you get

| Command | What it does |
|---------|--------------|
| `bin/abiertoclaw chat` | interactive REPL with per-thread memory |
| `bin/abiertoclaw say "<text>"` | one-shot question, prints the answer |
| `bin/abiertoclaw doctor` | validates config, keys, and source reachability |
| `bin/abiertoclaw model status` | shows which model each role points to |

Add `bin/` to your PATH if you'd rather type `abiertoclaw` bare.

Conversation memory survives restarts (it lives in `state/`, which is
gitignored). Inside chat, `/reset` clears the thread and `/status` shows the
live model map.

## How it routes

**Cheap by default, strong when it matters.** Every message gets a complexity
score from local heuristics: word count, multi-part structure, planning
keywords. Simple messages stay on the everyday free model; complex ones
escalate to the strong role. No model is ever called just to choose a model.

**A reply never silently drops.** Free models get rate-limited, deprecated, and
pulled without notice. When a call fails or comes back empty, the engine
rotates through the remaining roles (free, then local, then strong) and only
reports failure, with a diagnosis, after everything has been tried.

High-stakes structured work, like the calendar writes coming in Phase 3, won't
touch a model at all. It runs as deterministic code... a model that narrates
"I added the event" without adding it is worse than no assistant.

## Make it yours

Setup scaffolds three markdown files in `persona/`. Edit them. They're yours,
and gitignored:

- `SOUL.md`: voice and style
- `AGENTS.md`: hard rules (the "never fabricate dates" guardrail lives here)
- `USER.md`: who the assistant should know about

Keys live at `~/.abiertoclaw/<source>_key` (chmod 600), outside the repo.
Config files holding your info are gitignored too; the repo only ships
`*.example` versions.

## Where this is going

This is Phase 1 of the build plan in [SPEC.md](./SPEC.md): engine, CLI, source
layer, setup wizard. Next, in order: the morning free-model picker as a
scheduled job, the deterministic calendar skill, and an iMessage frontend for
Macs. The engine is frontend-agnostic on purpose. iMessage will be an adapter,
not a rewrite.

## Development

```sh
python3 -m unittest discover -s tests
```

The engine is pure and the drivers are mocked, so the suite runs in under a
second with no network. The complexity classifier has a golden set in
`tests/test_router.py`. If your change flips a case, that's a regression to
explain, not a test to delete.

## License

[MIT](./LICENSE)
