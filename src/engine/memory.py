"""Per-thread conversation memory (SPEC §8).

A ring buffer of recent turns per thread_id, persisted as JSON under
state/threads/ so context survives restarts. CLI and iMessage share this
store; the key is the thread, not the channel.
"""

import json
import os
import re

from .. import paths

MAX_TURNS = 40  # stored messages per thread (user + assistant combined)

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _thread_path(thread_id):
    return os.path.join(paths.THREADS_DIR, _SAFE.sub("_", thread_id) + ".json")


class ThreadMemory:
    def __init__(self, max_turns=MAX_TURNS):
        self.max_turns = max_turns
        paths.ensure_dirs()

    def history(self, thread_id):
        path = _thread_path(thread_id)
        if not os.path.isfile(path):
            return []
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []  # corrupt memory is dropped, not fatal

    def append(self, thread_id, role, content):
        turns = self.history(thread_id)
        turns.append({"role": role, "content": content})
        turns = turns[-self.max_turns:]  # trim oldest first
        with open(_thread_path(thread_id), "w") as f:
            json.dump(turns, f, indent=2)

    def reset(self, thread_id):
        path = _thread_path(thread_id)
        if os.path.isfile(path):
            os.remove(path)
