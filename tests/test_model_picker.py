"""Picker tests (SPEC §14): free filter, ranking, smoke-test fallback."""

import unittest

from src import model_picker


def m(mid, prompt="0", completion="0", context=100_000):
    return {
        "id": mid,
        "pricing": {"prompt": prompt, "completion": completion},
        "context_length": context,
    }


class FakeDriver:
    def __init__(self, models, answers):
        self.models = models
        self.answers = answers  # model id -> text

    def list_models(self):
        return self.models

    def chat(self, messages, model, opts=None):
        return {"text": self.answers.get(model, ""), "usage": {}}


class FakeSource:
    name = "fake"

    def __init__(self, driver):
        self.driver = driver


class TestFreeFilter(unittest.TestCase):
    def test_paid_models_are_excluded(self):
        self.assertTrue(model_picker.is_free(m("a")))
        self.assertFalse(model_picker.is_free(m("b", prompt="0.000001")))
        self.assertFalse(model_picker.is_free({"id": "c"}))  # no pricing info


class TestRanking(unittest.TestCase):
    def test_known_family_beats_unknown(self):
        ranked = model_picker.rank([m("x/mystery-1b"), m("google/gemini-thing")])
        self.assertEqual(ranked[0]["id"], "google/gemini-thing")

    def test_reasoning_models_sink(self):
        ranked = model_picker.rank(
            [m("a/qwen-reasoning", context=1_000_000), m("b/qwen-chat")]
        )
        self.assertEqual(ranked[0]["id"], "b/qwen-chat")


class TestPick(unittest.TestCase):
    def test_falls_back_when_top_pick_fails_smoke_test(self):
        models = [m("google/gemini-x", context=1_000_000), m("meta/llama-y")]
        driver = FakeDriver(models, {"meta/llama-y": "OK"})  # gemini stays silent
        picked = model_picker.pick_free(FakeSource(driver), log=lambda *_: None)
        self.assertEqual(picked, "meta/llama-y")

    def test_returns_none_when_nothing_answers(self):
        driver = FakeDriver([m("a/x")], {})
        picked = model_picker.pick_free(FakeSource(driver), log=lambda *_: None)
        self.assertIsNone(picked)


if __name__ == "__main__":
    unittest.main()
