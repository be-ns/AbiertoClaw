"""Write a pick into Hermes' config through the public `hermes config` CLI.

Plugins may only write their own settings subtree via ctx, so model and
fallback changes go through `hermes config set`, the same path a user would.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REFRESH_AFTER = 20 * 3600  # "daily", with slack so a 9am habit doesn't drift


def hermes_argv(*args):
    """Re-enter the Hermes install we're running inside, whatever PATH says."""
    return [sys.executable, "-m", "hermes_cli.main", *args]


def child_env(home):
    """Pin the child to this profile's home; a gateway may serve several."""
    env = dict(os.environ)
    if home:
        env["HERMES_HOME"] = str(home)
    return env


def run_hermes(*args, home=None):
    return subprocess.run(hermes_argv(*args), capture_output=True, text=True,
                          timeout=60, env=child_env(home))


def current_model(run=run_hermes):
    proc = run("config", "get", "model.default", "--json")
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return proc.stdout.strip() or None


def users_own_fallbacks(ours_before, pick, run=run_hermes):
    """Fallback entries the user added themselves, to keep after ours.

    Anything we didn't write last time and isn't already in the new pick
    belongs to the user (a paid backstop, a work endpoint) and survives.
    """
    proc = run("config", "get", "fallback_providers", "--json")
    if proc.returncode != 0:
        return []
    try:
        current = json.loads(proc.stdout)
    except ValueError:
        return []
    if not isinstance(current, list):
        return []
    new = [pick["primary"]] + pick["fallbacks"]
    return [e for e in current
            if isinstance(e, dict) and e not in ours_before and e not in new]


def apply(pick, run=run_hermes):
    """Point Hermes at pick["primary"] with pick["fallbacks"] as its chain."""
    primary = pick["primary"]
    steps = [
        ("config", "set", "model.provider", primary["provider"]),
        ("config", "set", "model.default", primary["model"]),
        ("config", "set", "fallback_providers", json.dumps(pick["fallbacks"])),
    ]
    if primary.get("base_url"):
        steps.append(("config", "set", "model.base_url", primary["base_url"]))
    for step in steps:
        proc = run(*step)
        if proc.returncode != 0:
            raise RuntimeError("hermes %s failed: %s" % (" ".join(step[:3]),
                                                         (proc.stderr or proc.stdout).strip()))
    if not primary.get("base_url"):
        # A stale local base_url would send OpenRouter traffic to localhost.
        run("config", "unset", "model.base_url")


class State:
    """What we last wrote and when. Lives in the plugin's data dir."""

    def __init__(self, path):
        self.path = Path(path)

    def load(self):
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def save(self, **fields):
        data = self.load()
        data.update(fields)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.path)

    def due(self, now=None):
        """True when a prior pick exists and the last attempt is stale."""
        data = self.load()
        if "model" not in data:
            return False  # never opted in; only an explicit `pick` starts this
        now = time.time() if now is None else now
        return now - data.get("checked_at", 0) >= REFRESH_AFTER

    def user_took_over(self, model_now):
        """The user changed the model by hand since our last pick: stop touching it."""
        ours = self.load().get("model")
        return bool(ours) and model_now is not None and model_now != ours
