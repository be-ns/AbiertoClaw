"""Per-thread conversation memory (SPEC §8).

A ring buffer of recent turns per thread_id, persisted as JSON under
state/threads/ so context survives restarts. CLI and iMessage share this
store; the key is the thread, not the channel.
"""

import json
import os
import re
import tempfile

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
                turns = json.load(f)
        except (ValueError, OSError):
            # Corrupt memory (bad JSON or bad encoding) is dropped, not fatal.
            # ValueError covers JSONDecodeError and UnicodeDecodeError both.
            return []
        if not isinstance(turns, list):
            return []  # same policy for valid JSON that isn't a turn list
        return turns

    def append(self, thread_id, role, content):
        turns = self.history(thread_id)
        turns.append({"role": role, "content": content})
        turns = turns[-self.max_turns:]  # trim oldest first
        path = _thread_path(thread_id)
        # A unique temp name per writer: concurrent appends to one thread
        # (say + an open chat REPL share a thread_id) must not collide.
        fd, tmp = tempfile.mkstemp(dir=paths.THREADS_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(turns, f, indent=2)
            os.replace(tmp, path)  # atomic: a crash can't corrupt history
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)  # don't litter the dir when the write fails

    def reset(self, thread_id):
        path = _thread_path(thread_id)
        if os.path.isfile(path):
            os.remove(path)
