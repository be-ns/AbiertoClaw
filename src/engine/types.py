"""Core schemas (SPEC §3.2). Frontends speak Message in, Reply out."""

import datetime
from dataclasses import dataclass, field


@dataclass
class Message:
    text: str
    sender_id: str
    thread_id: str
    channel: str = "cli"
    is_direct: bool = True
    ts: str = ""
    message_id: str = ""

    def __post_init__(self):
        if not self.ts:
            self.ts = datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass
class Reply:
    text: str
    tier: str  # deterministic | local | free | strong
    meta: dict = field(default_factory=dict)
