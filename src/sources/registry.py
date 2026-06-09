"""Source registry: turns sources.json entries into ready-to-call drivers.

Adding an OpenAI-compatible source is a JSON entry; adding a new API shape
is one driver module plus a DRIVERS entry. No engine changes either way.
"""

from .. import config as config_mod
from .. import secrets
from ..drivers import DRIVERS


class Source:
    def __init__(self, name, cfg):
        self.name = name
        self.cfg = cfg
        self.driver_name = cfg["driver"]
        self.base_url = config_mod.expand_vars(cfg["base_url"])
        self.api_key_env = cfg.get("api_key_env")
        self.api_key = secrets.resolve_api_key(name, self.api_key_env)
        self._driver = None

    @property
    def needs_key(self):
        return bool(self.api_key_env)

    @property
    def driver(self):
        if self._driver is None:
            if not self.base_url:
                # e.g. byo's "${BYO_BASE_URL}" with the env var unset; fail
                # with the fix instead of urllib's "unknown url type".
                raise config_mod.ConfigError(
                    "source %r has an empty base_url after expanding %r — set "
                    "the env var or put the URL in config/sources.json"
                    % (self.name, self.cfg["base_url"])
                )
            cls = DRIVERS[self.driver_name]
            self._driver = cls(
                base_url=self.base_url,
                api_key=self.api_key,
                models_endpoint=config_mod.expand_vars(
                    self.cfg.get("models_endpoint", "/models")
                ),
                extra_headers=self.cfg.get("extra_headers"),
            )
        return self._driver


def build_registry(sources_cfg):
    return {name: Source(name, cfg) for name, cfg in sources_cfg["sources"].items()}
