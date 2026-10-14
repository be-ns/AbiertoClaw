"""AbiertoClaw: a Hermes Agent plugin that keeps you on the best free model.

`hermes abiertoclaw pick` finds today's best free, tool-capable OpenRouter
model, smoke-tests it, and makes it Hermes' main model. Runners-up and any
local Ollama / LM Studio model become the fallback chain. After that first
pick, a stale pick (20h+) refreshes in the background at session start.
"""

import argparse
import os
import subprocess
import time
from pathlib import Path

from . import hermes_config, picker

PLUGIN = "abiertoclaw"


def _data_dir():
    try:
        from plugins.plugin_storage import plugin_data_dir
        return plugin_data_dir(PLUGIN)
    except ImportError:
        return Path(os.path.expanduser("~/.hermes/plugin-data")) / PLUGIN


def _home():
    """This profile's Hermes home (<home>/plugin-data/abiertoclaw)."""
    return _data_dir().parent.parent


def _run(*args):
    return hermes_config.run_hermes(*args, home=_home())


def _state():
    return hermes_config.State(_data_dir() / "state.json")


def _openrouter_key():
    try:
        from agent.secret_scope import get_secret
        return get_secret("OPENROUTER_API_KEY")
    except ImportError:
        return os.environ.get("OPENROUTER_API_KEY")


def _cmd_pick(args):
    state = _state()
    state.save(checked_at=time.time())
    if args.auto and state.user_took_over(hermes_config.current_model(_run)):
        print("abiertoclaw: model was changed by hand; leaving it alone. "
              "Run `hermes abiertoclaw pick` to opt back in.")
        return 0
    print("abiertoclaw: picking today's model...")
    pick = picker.plan(_openrouter_key())
    if pick is None:
        print("❌ No free model passed and no local model found.\n"
              "   Set OPENROUTER_API_KEY (hermes config set OPENROUTER_API_KEY ...) "
              "or start Ollama with a pulled model.")
        return 1
    if args.dry_run:
        print("primary:   %s" % pick["primary"])
        print("fallbacks: %s" % pick["fallbacks"])
        return 0
    ours = pick["fallbacks"]
    users = hermes_config.users_own_fallbacks(state.load().get("fallbacks", []), pick, _run)
    try:
        hermes_config.apply(dict(pick, fallbacks=ours + users), _run)
    except RuntimeError as e:
        print("❌ could not update Hermes config: %s" % e)
        return 1
    state.save(model=pick["primary"]["model"], picked_at=time.time(),
               primary=pick["primary"], fallbacks=ours)  # only ours: users' stay theirs
    n = len(ours) + len(users)
    print("✅ %s/%s is now the main model (%d fallback%s%s)."
          % (pick["primary"]["provider"], pick["primary"]["model"], n, "" if n == 1 else "s",
             ", %d of them yours" % len(users) if users else ""))
    return 0


def _cmd_status(args):
    data = _state().load()
    if not data.get("model"):
        print("No pick yet. Run `hermes abiertoclaw pick`.")
        return 0
    age = (time.time() - data.get("picked_at", 0)) / 3600
    print("primary:   %s (picked %.1fh ago)" % (data["primary"], age))
    for fb in data.get("fallbacks", []):
        print("fallback:  %s" % fb)
    return 0


def _setup_cli(parser):
    sub = parser.add_subparsers(dest="abiertoclaw_cmd")
    pick = sub.add_parser("pick", help="pick today's best free model and apply it")
    pick.add_argument("--dry-run", action="store_true", help="show the pick, change nothing")
    pick.add_argument("--auto", action="store_true", help=argparse.SUPPRESS)
    sub.add_parser("status", help="show the current pick")


def _handle(args):
    if getattr(args, "abiertoclaw_cmd", None) == "pick":
        return _cmd_pick(args)
    return _cmd_status(args)


def _on_session_start(**kwargs):
    """Refresh a stale pick in a detached `hermes` process; applies next session."""
    try:
        state = _state()
        if not state.due():
            return
        state.save(checked_at=time.time())  # claim the slot before spawning
        with open(_data_dir() / "refresh.log", "a") as log:
            subprocess.Popen(hermes_config.hermes_argv(PLUGIN, "pick", "--auto"),
                             stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                             env=hermes_config.child_env(_home()),
                             start_new_session=True)
    except Exception:  # a hook must never break a session
        pass


def register(ctx):
    ctx.register_cli_command(
        name=PLUGIN,
        help="Keep Hermes on the best free model, with local fallback",
        setup_fn=_setup_cli,
        handler_fn=_handle,
    )
    ctx.register_hook("on_session_start", _on_session_start)
