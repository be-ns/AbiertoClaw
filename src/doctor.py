"""abiertoclaw doctor: validate config, secrets, and source reachability.

Bad config fails loudly here instead of mysteriously at chat time
(SPEC gotcha #8).
"""

from . import config as config_mod
from .config import ConfigError
from .drivers import ProviderError, RateLimited
from .sources import build_registry


def _check(ok, label, detail=""):
    mark = "✅" if ok else "❌"
    print("%s %s%s" % (mark, label, (" — " + detail) if detail else ""))
    return ok


def run():
    healthy = True

    try:
        sources_cfg = config_mod.load_sources()
        _check(True, "sources.json loads")
    except ConfigError as e:
        _check(False, "sources.json", str(e))
        return 1

    try:
        models_cfg = config_mod.load_models()
        _check(True, "models.json loads")
    except ConfigError as e:
        _check(False, "models.json", str(e))
        return 1

    try:
        config_mod.load_identity()
        _check(True, "identity.json loads")
    except ConfigError as e:
        healthy = _check(False, "identity.json", str(e)) and healthy

    registry = build_registry(sources_cfg)

    # Roles must point at defined sources, and used hosted sources need keys.
    used = set()
    for role, spec in models_cfg["roles"].items():
        ok = spec["source"] in registry
        healthy = _check(ok, "role %r -> source %r" % (role, spec["source"]),
                         "" if ok else "not defined in sources.json") and healthy
        if ok:
            used.add(spec["source"])

    for name in sorted(used):
        source = registry[name]
        try:
            source.driver.list_models()
            reachable, detail = True, ""
        except RateLimited:
            reachable, detail = True, "reachable (rate limited)"
        except ProviderError as e:
            reachable, detail = False, str(e)

        if source.needs_key:
            if source.api_key is not None:
                _check(True, "key for %r" % name, "found")
            elif reachable:
                # e.g. a BYO endpoint that doesn't require auth.
                _check(True, "key for %r" % name,
                       "none set, but the endpoint answers without one")
            else:
                healthy = _check(False, "key for %r" % name,
                                 "set $%s or run setup" % source.api_key_env) and healthy

        healthy = _check(reachable, "reach %s (%s)" % (name, source.base_url),
                         detail) and healthy

    print("\n%s" % ("all good." if healthy else "fix the ❌ items above, then re-run."))
    return 0 if healthy else 1
