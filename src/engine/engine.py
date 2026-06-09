"""The engine: handle(Message) -> Reply. Pure, frontend-agnostic, no Mac deps.

Two-tier rule (SPEC §3.3): structured/high-stakes work runs as deterministic
code; only open-ended language reaches a model. The model tier has no tools,
so it cannot act — only talk.

Fallback chain (SPEC §7.3): a reply must never silently drop. On a rate
limit, an error, or an empty reply we rotate to the next role's model.
"""

from ..config import ConfigError
from ..drivers import ProviderError, RateLimited
from . import persona, router
from .memory import ThreadMemory
from .types import Reply

# Role order tried after the routed role fails: free -> local -> strong.
FALLBACK_ORDER = ("free", "local", "strong")


class Engine:
    def __init__(self, registry, models_cfg, identity, memory=None):
        self.registry = registry
        self.roles = models_cfg["roles"]
        self.identity = identity
        self.memory = memory or ThreadMemory()
        self.system_prompt = persona.build_system_prompt(identity)

    # -- public entry point ---------------------------------------------------

    def handle(self, msg):
        intent = router.classify_intent(msg.text)
        if intent == "command":
            return self._handle_command(msg)
        return self._handle_chat(msg)

    # -- deterministic tier ---------------------------------------------------

    def _handle_command(self, msg):
        cmd = msg.text.strip().split()[0].lower()
        if cmd in ("/help", "/?"):
            text = (
                "Commands: /help, /status, /reset, /exit\n"
                "Everything else is conversation. Short messages stay on the "
                "everyday model; complex ones escalate automatically."
            )
        elif cmd == "/status":
            text = "\n".join(
                "%-7s -> %s / %s" % (role, spec["source"], spec["model"])
                for role, spec in self.roles.items()
            )
        elif cmd == "/reset":
            self.memory.reset(msg.thread_id)
            text = "Thread memory cleared."
        else:
            text = "Unknown command %s. Try /help." % cmd
        return Reply(text=text, tier="deterministic")

    # -- model tier -----------------------------------------------------------

    def _handle_chat(self, msg):
        level = router.classify_complexity(msg.text)
        first_role = "strong" if level == "complex" else self._everyday_role()
        chain = self._role_chain(first_role)

        messages = [{"role": "system", "content": self.system_prompt}]
        messages += self.memory.history(msg.thread_id)
        messages.append({"role": "user", "content": msg.text})

        errors = []
        for role in chain:
            spec = self.roles[role]
            source = self.registry.get(spec["source"])
            if source is None:
                errors.append("%s: source %r not configured" % (role, spec["source"]))
                continue
            try:
                result = source.driver.chat(messages, spec["model"])
            except RateLimited:
                errors.append("%s: rate limited (%s)" % (role, spec["model"]))
                continue
            except (ProviderError, ConfigError) as e:
                errors.append("%s: %s" % (role, e))
                continue
            if not result["text"]:
                errors.append("%s: empty reply from %s" % (role, spec["model"]))
                continue
            self.memory.append(msg.thread_id, "user", msg.text)
            self.memory.append(msg.thread_id, "assistant", result["text"])
            meta = {
                "source": spec["source"],
                "model": spec["model"],
                "usage": result.get("usage", {}),
                "complexity": level,
            }
            if errors:
                # Roles we rotated past; frontends can surface degradation
                # instead of it staying invisible until everything fails.
                meta["skipped"] = errors
            return Reply(text=result["text"], tier=role, meta=meta)

        return Reply(
            text=(
                "I couldn't reach any configured model. Run `abiertoclaw doctor` "
                "to see what's wrong.\nDetails: " + "; ".join(errors)
            ),
            tier="deterministic",
            meta={"errors": errors},
        )

    # -- helpers --------------------------------------------------------------

    def _everyday_role(self):
        return "free" if "free" in self.roles else next(iter(self.roles))

    def _role_chain(self, first_role):
        chain = [first_role] if first_role in self.roles else []
        for role in FALLBACK_ORDER:
            if role in self.roles and role not in chain:
                chain.append(role)
        return chain
