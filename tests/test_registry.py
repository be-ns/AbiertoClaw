"""Source registry: config -> driver wiring, and loud failures for bad config."""

import unittest
from unittest import mock

from src.config import ConfigError
from src.drivers import OllamaDriver, OpenAICompatibleDriver
from src.sources import build_registry


def cfg(sources):
    return {"default": next(iter(sources)), "sources": sources}


class TestBuildRegistry(unittest.TestCase):
    def test_builds_the_right_driver_per_source(self):
        registry = build_registry(cfg({
            "hosted": {"driver": "openai-compatible",
                       "base_url": "https://example.test/v1"},
            "local": {"driver": "ollama", "base_url": "http://127.0.0.1:11434"},
        }))
        self.assertIsInstance(registry["hosted"].driver, OpenAICompatibleDriver)
        self.assertIsInstance(registry["local"].driver, OllamaDriver)

    def test_env_vars_expand_in_base_url(self):
        with mock.patch.dict("os.environ", {"MY_BASE": "https://example.test/v1"}):
            registry = build_registry(cfg({
                "byo": {"driver": "openai-compatible", "base_url": "${MY_BASE}"},
            }))
        self.assertEqual(registry["byo"].base_url, "https://example.test/v1")

    def test_unset_env_var_fails_loudly_with_the_fix(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            registry = build_registry(cfg({
                "byo": {"driver": "openai-compatible", "base_url": "${MY_BASE}"},
            }))
            with self.assertRaises(ConfigError) as ctx:
                registry["byo"].driver
        self.assertIn("byo", str(ctx.exception))
        self.assertIn("${MY_BASE}", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
