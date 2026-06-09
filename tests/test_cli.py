"""CLI frontend: say's exit code is script-visible behavior, so pin it."""

import contextlib
import io
import unittest

from src.engine.types import Reply
from src.frontends import cli


class FakeEngine:
    def __init__(self, reply):
        self.reply = reply

    def handle(self, message):
        return self.reply


def run_say(reply):
    with contextlib.redirect_stdout(io.StringIO()):
        return cli.say(FakeEngine(reply), "hello")


class TestSayExitCode(unittest.TestCase):
    def test_answer_exits_zero(self):
        self.assertEqual(run_say(Reply(text="hi", tier="free")), 0)

    def test_deterministic_reply_exits_zero(self):
        self.assertEqual(run_say(Reply(text="ok", tier="deterministic")), 0)

    def test_total_failure_exits_one(self):
        reply = Reply(text="no model answered", tier="deterministic",
                      meta={"errors": ["free: down"]})
        self.assertEqual(run_say(reply), 1)


if __name__ == "__main__":
    unittest.main()
