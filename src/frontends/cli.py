"""CLI frontend: the universal path and the dev harness (SPEC §9.1).

Thin by design — it normalizes input into a Message, calls the engine, and
prints the Reply. All logic lives in the engine, which is what keeps
iMessage-or-CLI a frontend decision instead of a fork.
"""

import getpass
import sys

from ..engine.types import Message

THREAD_ID = "cli:%s" % getpass.getuser()


def _message(text):
    return Message(
        text=text,
        sender_id=getpass.getuser(),
        thread_id=THREAD_ID,
        channel="cli",
        is_direct=True,
    )


def say(engine, text):
    """One-shot: abiertoclaw say "<text>"."""
    reply = engine.handle(_message(text))
    print(reply.text)
    return 0


def repl(engine, identity):
    """Interactive: abiertoclaw chat."""
    try:
        import readline  # noqa: F401  (line editing + history, if available)
    except ImportError:
        pass
    name = identity.get("assistant_name", "Claw")
    print("%s ready. /help for commands, /exit to leave." % name)
    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line.lower() in ("/exit", "/quit", "exit", "quit"):
            return 0
        reply = engine.handle(_message(line))
        tag = "" if reply.tier == "deterministic" else "  [%s: %s]" % (
            reply.tier, reply.meta.get("model", ""))
        print("%s> %s%s" % (name.lower(), reply.text, tag), file=sys.stdout)
