"""Config loading and validation. Bad config fails loudly (SPEC gotcha #8)."""

import json
import os
import re

from . import paths

_VAR_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigError(Exception):
    pass


def expand_vars(value):
    """Expand ${ENV_VAR} references in a string. Missing vars expand to ""."""
    if not isinstance(value, str):
        return value
    return _VAR_RE.sub(lambda m: os.environ.get(m.group(1), ""), value)


def load_json(path):
    if not os.path.isfile(path):
        raise ConfigError(
            "missing config file: %s (run `abiertoclaw setup` to create it)" % path
        )
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError("invalid JSON in %s: %s" % (path, e))


def load_sources():
    cfg = load_json(paths.config_path("sources.json"))
    if "sources" not in cfg or not isinstance(cfg["sources"], dict):
        raise ConfigError("sources.json needs a 'sources' object")
    default = cfg.get("default")
    if default not in cfg["sources"]:
        raise ConfigError("sources.json 'default' (%r) is not a defined source" % default)
    for name, src in cfg["sources"].items():
        if src.get("driver") not in ("openai-compatible", "ollama"):
            raise ConfigError(
                "source %r has unknown driver %r" % (name, src.get("driver"))
            )
        if not src.get("base_url"):
            raise ConfigError("source %r is missing base_url" % name)
    return cfg


def load_models():
    cfg = load_json(paths.config_path("models.json"))
    roles = cfg.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise ConfigError("models.json needs a non-empty 'roles' object")
    for role, spec in roles.items():
        if not spec.get("source") or not spec.get("model"):
            raise ConfigError("role %r needs both 'source' and 'model'" % role)
    return cfg


def load_identity():
    cfg = load_json(paths.config_path("identity.json"))
    cfg.setdefault("assistant_name", "Claw")
    cfg.setdefault("owner_name", "you")
    cfg.setdefault("timezone", "UTC")
    return cfg


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
