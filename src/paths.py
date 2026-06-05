"""Filesystem layout. One place to answer "where does X live?"."""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
PERSONA_DIR = os.path.join(ROOT, "persona")
STATE_DIR = os.path.join(ROOT, "state")
THREADS_DIR = os.path.join(STATE_DIR, "threads")
LOGS_DIR = os.path.join(ROOT, "logs")

# Secrets live outside the repo so they can never be committed.
HOME_DIR = os.path.expanduser("~/.abiertoclaw")


def config_path(name):
    return os.path.join(CONFIG_DIR, name)


def ensure_dirs():
    for d in (STATE_DIR, THREADS_DIR, LOGS_DIR):
        os.makedirs(d, exist_ok=True)
