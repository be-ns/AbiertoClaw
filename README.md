# AbiertoClaw

> A capable, **free-by-default** personal AI assistant — a "claw" — that you talk
> to over **iMessage or a CLI**, with a model layer you can swap between
> OpenRouter, OpenCode Zen, your own API key, or a fully-local model.

**Status: early.** This repo currently holds the build spec — **[`SPEC.md`](./SPEC.md)**.
Code lands phase by phase (see [Build phases](./SPEC.md#18-build-phases-execute-in-order)).
The CLI is the universal path; iMessage is an opt-in macOS add-on.

## What it is

A free-by-default personal assistant with an iMessage frontend and a CLI
frontend, calendar support, and a semi-local router that runs cheap/free for
everyday chat and **automatically upgrades to a stronger model only when a
request is genuinely complex** — with model access swappable between OpenRouter,
OpenCode Zen, your own API key, or a fully-local model.

- **Free by default.** Runs on local (Ollama) and/or a free hosted tier — no credit card to get a working assistant.
- **Your choice of model source.** OpenRouter, OpenCode Zen, bring-your-own OpenAI-compatible endpoint, or local Ollama. Mix sources per tier.
- **Self-upgrading on complexity.** A semi-local router classifies each message and escalates only the hard ones.
- **A "best free model" picker.** A daily job smoke-tests candidate free models, picks the strongest that works, and falls back/rotates when one is rate-limited or pulled.
- **Two frontends, one brain.** Same engine, handlers, and memory behind both iMessage and the CLI.
- **Deterministic where it counts.** High-stakes actions (calendar writes) run as plain code — no hallucinated events.
- **Publishable.** Clone, run a setup wizard, and have a working CLI assistant in minutes.

## How it works (at a glance)

- **Source layer** — a single OpenAI-compatible driver (plus a separate Ollama driver) sits behind a pluggable source registry, so swapping providers is config, not code.
- **Complexity router** — classifies intent + difficulty locally and routes to a free everyday model or a stronger one as needed.
- **Morning picker** — refreshes today's best free model, smoke-tested with fallbacks.
- **Deterministic tier** — anything costly-if-wrong bypasses the model entirely.

See [`SPEC.md`](./SPEC.md) for the full architecture, schemas, gotchas, and the phased build plan.

## Getting started

Not yet runnable — **Phase 1** (engine + CLI + source layer) is the first milestone.
The planned flow:

```sh
abiertoclaw setup    # pick a source, drop a key (or go local), smoke-test
abiertoclaw chat     # talk to it — free, on the source you chose
```

For now, read [`SPEC.md`](./SPEC.md).

## Why "AbiertoClaw"?

*Abierto* is Spanish for *open*. AbiertoClaw is an open, free-by-default take on
the "claw" assistant pattern — spiritually inspired by `cyberpapiii/chipotlai-max`,
but built as a **reusable assistant layer** (not a runtime fork) and shipped as a
public repo that uses **legitimate model sources only** (local + free/paid APIs).
It distills hard-won lessons from a working predecessor assistant so this one
doesn't have to re-learn them.

## License

[MIT](./LICENSE).
