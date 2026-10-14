# AbiertoClaw

A [Hermes Agent](https://github.com/NousResearch/hermes-agent) plugin that
keeps Hermes running on today's best **free** model, with a local model as the
safety net.

Hermes already does the hard parts: chat, memory, persona, tools, and a
fallback chain. AbiertoClaw does the one thing it doesn't: every day it finds a
free model that actually works and points Hermes at it.

## Install

```sh
hermes plugins install be-ns/AbiertoClaw --enable
hermes config set OPENROUTER_API_KEY sk-or-...   # optional, see below
hermes abiertoclaw pick
```

That first `pick` opts you in. From then on, the first session after a pick
goes 20h stale kicks off a background refresh; the new model applies to your
next session.

## How it picks

1. Pull the OpenRouter catalog. Keep models that are free, support tool
   calling, and have 64K+ context (Hermes needs all three).
2. Rank by known-good family and context size.
3. Smoke-test the top picks with a **real tool call**. A model that only
   chats fails. This is the check that keeps free models from breaking Hermes.
4. Best passer becomes `model.default`. The next two passers, then any local
   model, become `fallback_providers`, so a rate limit mid-session rolls over
   instead of dying.
5. No key, or nothing passed? A local model becomes the main model.

Local models are found at Ollama (`127.0.0.1:11434`) and LM Studio
(`127.0.0.1:1234`). Embedding models are skipped.

## Commands

| Command | What it does |
|---------|--------------|
| `hermes abiertoclaw pick` | pick and apply now |
| `hermes abiertoclaw pick --dry-run` | show the pick, change nothing |
| `hermes abiertoclaw status` | what's picked and how long ago |

## It stays out of your way

- Changes go through `hermes config set`, the same path you'd use by hand.
- If you change `model.default` yourself, the daily refresh sees it and stops.
  Run `pick` again to opt back in.
- Refresh output goes to `~/.hermes/plugin-data/abiertoclaw/refresh.log`.
- Under `plugins.isolation: host`, Hermes doesn't wire plugin CLI commands;
  use the default in-process mode.

## Development

```sh
python3 -m unittest discover -s tests
hermes plugins validate .
```

Stdlib only; the tests mock HTTP and the `hermes` CLI and run with no network.

## License

[MIT](./LICENSE)
