"""Config validation: bad config fails loudly, with the role and key named."""

import json
import os
import tempfile
import unittest
from unittest import mock

from src import config, paths
from src.config import ConfigError


class TestLoadModels(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(paths, "CONFIG_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _write(self, roles):
        with open(os.path.join(self.tmp.name, "models.json"), "w") as f:
            json.dump({"roles": roles}, f)

    def test_valid_roles_load(self):
        self._write({"free": {"source": "s", "model": "m"}})
        self.assertEqual(config.load_models()["roles"]["free"]["model"], "m")

    def test_non_string_model_is_rejected(self):
        self._write({"free": {"source": "s", "model": 123}})
        with self.assertRaises(ConfigError) as ctx:
            config.load_models()
        self.assertIn("free", str(ctx.exception))

    def test_missing_source_is_rejected(self):
        self._write({"free": {"model": "m"}})
        with self.assertRaises(ConfigError):
            config.load_models()


if __name__ == "__main__":
    unittest.main()
