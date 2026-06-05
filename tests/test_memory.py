import os
import tempfile
import unittest
from unittest import mock

from src import paths
from src.engine.memory import ThreadMemory


class TestThreadMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.multiple(
            paths,
            STATE_DIR=self.tmp.name,
            THREADS_DIR=os.path.join(self.tmp.name, "threads"),
            LOGS_DIR=os.path.join(self.tmp.name, "logs"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_round_trip(self):
        memory = ThreadMemory()
        memory.append("cli:ben", "user", "hi")
        memory.append("cli:ben", "assistant", "hello")
        self.assertEqual(
            memory.history("cli:ben"),
            [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
        )

    def test_trims_oldest_first(self):
        memory = ThreadMemory(max_turns=4)
        for i in range(6):
            memory.append("t", "user", "msg %d" % i)
        history = memory.history("t")
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["content"], "msg 2")

    def test_threads_are_isolated(self):
        memory = ThreadMemory()
        memory.append("a", "user", "for a")
        self.assertEqual(memory.history("b"), [])

    def test_reset(self):
        memory = ThreadMemory()
        memory.append("t", "user", "hi")
        memory.reset("t")
        self.assertEqual(memory.history("t"), [])

    def test_weird_thread_ids_are_safe_filenames(self):
        memory = ThreadMemory()
        memory.append("group:+1 (555) 123/456", "user", "hi")
        self.assertEqual(len(memory.history("group:+1 (555) 123/456")), 1)


if __name__ == "__main__":
    unittest.main()
