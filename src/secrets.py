"""API key resolution.

Keys are never written into config files. A source declares an env var name
(`api_key_env`); we resolve it from the environment first, then from a
key file at ~/.abiertoclaw/<source>_key (chmod 600).
"""

import os

from . import paths


def key_file(source_name):
    return os.path.join(paths.HOME_DIR, "%s_key" % source_name)


def resolve_api_key(source_name, api_key_env):
    """Return the API key for a source, or None if not configured."""
    if api_key_env:
        value = os.environ.get(api_key_env)
        if value:
            return value.strip()
    path = key_file(source_name)
    if os.path.isfile(path):
        with open(path) as f:
            value = f.read().strip()
        if value:
            return value
    return None


def store_api_key(source_name, value):
    """Write a key file with owner-only permissions."""
    os.makedirs(paths.HOME_DIR, exist_ok=True)
    path = key_file(source_name)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(value.strip() + "\n")
    os.chmod(path, 0o600)  # O_CREAT mode only applies to new files
    return path
