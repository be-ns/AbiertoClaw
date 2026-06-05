"""Engine behavior: routing, fallback chain, memory, deterministic commands."""

import unittest

from src.drivers import ProviderError, RateLimited
from src.engine import Engine, Message
from src.engine.memory import ThreadMemory


class FakeMemory(ThreadMemory):
    """In-process memory; no filesystem."""

    def __init__(self):
        self.store = {}

    def history(self, thread_id):
        return list(self.store.get(thread_id, []))

    def append(self, thread_id, role, content):
        self.store.setdefault(thread_id, []).append(
            {"role": role, "content": content}
        )

    def reset(self, thread_id):
        self.store.pop(thread_id, None)


class FakeDriver:
    def __init__(self, behavior):
        self.behavior = behavior  # model -> text | Exception
        self.calls = []

    def chat(self, messages, model, opts=None):
        self.calls.append(model)
        result = self.behavior[model]
        if isinstance(result, Exception):
            raise result
        return {"text": result, "usage": {}}


class FakeSource:
    def __init__(self, driver):
        self.driver = driver


def make_engine(behavior, roles):
    driver = FakeDriver(behavior)
    engine = Engine(
        registry={"test": FakeSource(driver)},
        models_cfg={"roles": roles},
        identity={"assistant_name": "Claw", "owner_name": "Ben"},
        memory=FakeMemory(),
    )
    return engine, driver


ROLES = {
    "local": {"source": "test", "model": "tiny"},
    "free": {"source": "test", "model": "everyday"},
    "strong": {"source": "test", "model": "big"},
}


def msg(text):
    return Message(text=text, sender_id="ben", thread_id="t1")


class TestRouting(unittest.TestCase):
    def test_simple_message_uses_free_role(self):
        engine, driver = make_engine({"everyday": "hi!"}, ROLES)
        reply = engine.handle(msg("hello"))
        self.assertEqual(reply.tier, "free")
        self.assertEqual(driver.calls, ["everyday"])

    def test_complex_message_escalates_to_strong(self):
        engine, driver = make_engine({"big": "deep answer"}, ROLES)
        reply = engine.handle(msg("brainstorm a plan to compare three options"))
        self.assertEqual(reply.tier, "strong")
        self.assertEqual(driver.calls, ["big"])


class TestFallback(unittest.TestCase):
    def test_rate_limit_rotates_to_next_role(self):
        engine, driver = make_engine(
            {"everyday": RateLimited("429"), "tiny": "backup answer"}, ROLES
        )
        reply = engine.handle(msg("hello"))
        self.assertEqual(reply.tier, "local")
        self.assertEqual(driver.calls, ["everyday", "tiny"])

    def test_empty_reply_counts_as_failure(self):
        engine, driver = make_engine({"everyday": "", "tiny": "ok"}, ROLES)
        reply = engine.handle(msg("hello"))
        self.assertEqual(reply.tier, "local")

    def test_all_failures_returns_diagnostic_not_silence(self):
        engine, _ = make_engine(
            {
                "everyday": ProviderError("down"),
                "tiny": ProviderError("down"),
                "big": ProviderError("down"),
            },
            ROLES,
        )
        reply = engine.handle(msg("hello"))
        self.assertEqual(reply.tier, "deterministic")
        self.assertIn("doctor", reply.text)


class TestMemory(unittest.TestCase):
    def test_successful_turn_is_remembered(self):
        engine, driver = make_engine({"everyday": "hi!"}, ROLES)
        engine.handle(msg("hello"))
        engine.handle(msg("again"))
        # Second call must include the first exchange as history.
        self.assertEqual(len(engine.memory.history("t1")), 4)

    def test_failed_turn_is_not_remembered(self):
        engine, _ = make_engine(
            {"everyday": ProviderError("x"), "tiny": ProviderError("x"),
             "big": ProviderError("x")},
            ROLES,
        )
        engine.handle(msg("hello"))
        self.assertEqual(engine.memory.history("t1"), [])


class TestCommands(unittest.TestCase):
    def test_status_never_touches_a_model(self):
        engine, driver = make_engine({}, ROLES)
        reply = engine.handle(msg("/status"))
        self.assertEqual(reply.tier, "deterministic")
        self.assertIn("everyday", reply.text)
        self.assertEqual(driver.calls, [])

    def test_reset_clears_thread(self):
        engine, _ = make_engine({"everyday": "hi"}, ROLES)
        engine.handle(msg("hello"))
        engine.handle(msg("/reset"))
        self.assertEqual(engine.memory.history("t1"), [])


if __name__ == "__main__":
    unittest.main()
