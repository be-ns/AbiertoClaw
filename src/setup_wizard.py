"""First-run wizard (SPEC §16): pick a source, drop a key, smoke test, chat.

The whole point of this file is that a stranger who just cloned the repo
answers a few prompts and ends up with a working, validated assistant. Every
exit path either succeeds or says exactly what to fix.
"""

import getpass
import os
import shutil
import sys

from . import config as config_mod
from . import model_picker, paths, secrets
from .doctor import run as run_doctor
from .sources import build_registry

SOURCE_MENU = (
    ("openrouter", "OpenRouter — biggest catalog, real free tier; messages go to "
                   "OpenRouter + the model provider"),
    ("zen", "OpenCode Zen — curated coding models, rotating free set; messages go "
            "to Zen + the model provider"),
    ("byo", "Bring your own — any OpenAI-compatible endpoint you already pay for "
            "or host"),
    ("local", "Local only (Ollama) — fully private and free; needs Ollama "
              "installed, no key"),
)


def _ask(prompt, default=None):
    suffix = " [%s]" % default if default else ""
    answer = input("%s%s: " % (prompt, suffix)).strip()
    return answer or (default or "")


def _ask_choice():
    print("\nWhere should models come from?\n")
    for i, (name, blurb) in enumerate(SOURCE_MENU, 1):
        print("  %d. %-11s %s" % (i, name, blurb))
    while True:
        raw = _ask("\nPick 1-4", "1")
        if raw.isdigit() and 1 <= int(raw) <= len(SOURCE_MENU):
            return SOURCE_MENU[int(raw) - 1][0]
        print("Enter a number 1-%d." % len(SOURCE_MENU))


def _scaffold(name):
    """Copy config/<name>.example.json -> config/<name>.json if missing."""
    dst = paths.config_path(name + ".json")
    if not os.path.isfile(dst):
        shutil.copy(paths.config_path(name + ".example.json"), dst)
    return config_mod.load_json(dst)


def _scaffold_persona():
    for name in ("SOUL.md", "AGENTS.md", "USER.md"):
        dst = os.path.join(paths.PERSONA_DIR, name)
        src = os.path.join(paths.PERSONA_DIR, name.replace(".md", ".example.md"))
        if not os.path.isfile(dst) and os.path.isfile(src):
            shutil.copy(src, dst)


def _collect_key(source_name, env_name, optional=False):
    if secrets.resolve_api_key(source_name, env_name):
        print("Found an existing key for %s." % source_name)
        return
    print("\nPaste your %s API key (stored at ~/.abiertoclaw/%s_key, chmod 600;"
          % (source_name, source_name))
    print("never committed, never logged).")
    sys.stdout.flush()  # getpass writes to the tty; keep the explainer ahead of it
    while True:
        value = getpass.getpass("key%s: " % (" (Enter to skip)" if optional else "")).strip()
        if value or optional:
            break
        print("Key can't be empty.")
    if not value:
        print("Skipped — assuming your endpoint doesn't need auth.")
        return
    path = secrets.store_api_key(source_name, value)
    print("Saved to %s" % path)


def _detect_timezone():
    try:
        link = os.readlink("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/")[-1]
    except OSError:
        pass
    return "UTC"


def _pick_local_model(source):
    try:
        installed = [m["id"] for m in source.driver.list_models()]
    except Exception:
        print("\n❌ Can't reach Ollama at %s." % source.base_url)
        print("Install it from https://ollama.com, run `ollama serve`, then "
              "re-run setup.")
        return None
    if not installed:
        print("\nOllama is running but has no models. In another terminal:")
        print("  ollama pull qwen2.5:7b")
        input("Press Enter once the pull finishes...")
        installed = [m["id"] for m in source.driver.list_models()]
        if not installed:
            return None
    default = next((m for m in installed if "qwen" in m), installed[0])
    print("\nInstalled Ollama models: %s" % ", ".join(installed))
    return _ask("Which model should I use", default)


def run():
    print("AbiertoClaw setup — a few questions and you're chatting.\n")
    paths.ensure_dirs()

    # 1. Identity: who is this assistant, and whose is it?
    assistant = _ask("Name your assistant", "Claw")
    owner = _ask("Your name", getpass.getuser())
    timezone = _ask("Timezone", _detect_timezone())

    # 2. Source choice.
    choice = _ask_choice()

    sources_cfg = _scaffold("sources")
    sources_cfg["default"] = choice

    if choice == "byo":
        base_url = _ask("Base URL (e.g. https://api.groq.com/openai/v1)")
        sources_cfg["sources"]["byo"]["base_url"] = base_url

    config_mod.save_json(paths.config_path("sources.json"), sources_cfg)
    registry = build_registry(sources_cfg)
    source = registry[choice]

    # 3. Key (hosted sources only; BYO endpoints may not need one).
    if source.needs_key:
        _collect_key(choice, source.api_key_env, optional=(choice == "byo"))
        registry = build_registry(sources_cfg)  # re-resolve with the new key
        source = registry[choice]

    # 4. Pick the everyday model.
    models_cfg = _scaffold("models")
    if choice == "openrouter":
        print("\nFinding today's best free model on OpenRouter...")
        model = model_picker.pick_free(source)
        if not model:
            model = _ask("Auto-pick failed. Enter a model id to use")
    elif choice == "zen":
        print("\nZen's free set rotates; check https://opencode.ai/zen for "
              "what's currently free.")
        model = _ask("Model id to use")
    elif choice == "byo":
        model = _ask("Model id your endpoint serves (e.g. llama-3.3-70b-versatile)")
    else:  # local
        model = _pick_local_model(source)
        if not model:
            return 1

    if not model:
        print("No model selected; re-run setup when you have one.")
        return 1

    # One model id can serve all three roles on day one; the morning picker
    # and per-role overrides differentiate them later (SPEC §5.1).
    for role in models_cfg["roles"]:
        models_cfg["roles"][role]["source"] = choice
        models_cfg["roles"][role]["model"] = model
    config_mod.save_json(paths.config_path("models.json"), models_cfg)

    identity = _scaffold("identity")
    identity.update(
        {"assistant_name": assistant, "owner_name": owner, "timezone": timezone}
    )
    config_mod.save_json(paths.config_path("identity.json"), identity)
    _scaffold_persona()

    # 5. Validate, then prove it with one real reply.
    print("\nRunning doctor...")
    if run_doctor() != 0:
        return 1

    print("\nSmoke chat...")
    if not model_picker.smoke_test(source.driver, model):
        print("❌ %s didn't answer. Try another model: edit config/models.json "
              "or re-run setup." % model)
        return 1
    print("✅ %s answered." % model)

    print(
        "\n✅ %s is ready. Talk to it:\n"
        "   bin/abiertoclaw chat\n\n"
        "Optional next steps:\n"
        "   - edit persona/SOUL.md to change its voice\n"
        "   - iMessage frontend (macOS) lands in Phase 4 — see SPEC.md §18\n"
        % assistant
    )
    return 0
