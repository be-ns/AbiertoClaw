"""Golden set for the complexity classifier (SPEC §6.2, §14).

Change the heuristics, run this. If a case here flips, that's a regression
to explain, not a test to delete.
"""

import unittest

from src.engine import router

SIMPLE = [
    "what time is it",
    "thanks!",
    "is the meeting still on?",
    "remind me what we said about dinner",
    "yes",
]

COMPLEX = [
    "compare openrouter and opencode zen for me and tell me which to use",
    "help me plan a three day trip to portland with my parents, "
    "they don't walk much and we need vegetarian food options",
    "what's the tradeoff here? and which one is cheaper? and why?",
    "1. fix the budget\n2. email sarah\n3. what order should I do these in",
    "brainstorm names for a coffee shop",
]


class TestComplexity(unittest.TestCase):
    def test_simple_cases(self):
        for text in SIMPLE:
            self.assertEqual(
                router.classify_complexity(text), "simple", "case: %r" % text
            )

    def test_complex_cases(self):
        for text in COMPLEX:
            self.assertEqual(
                router.classify_complexity(text), "complex", "case: %r" % text
            )


class TestIntent(unittest.TestCase):
    def test_commands(self):
        self.assertEqual(router.classify_intent("/help"), "command")
        self.assertEqual(router.classify_intent("  /status"), "command")

    def test_chat(self):
        self.assertEqual(router.classify_intent("hello there"), "chat")


if __name__ == "__main__":
    unittest.main()
