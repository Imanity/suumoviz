"""Persistent crawler state: rotation offsets, cooldown, robots.txt digest."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9))  # Japan has no DST
STATE_FILE = "state.json"
FIRST_COOLDOWN = timedelta(hours=24)
REPEAT_COOLDOWN = timedelta(hours=72)
REPEAT_WINDOW = timedelta(days=7)


def now_jst() -> datetime:
    return datetime.now(JST)


@dataclass
class State:
    offsets: dict[str, int] = field(default_factory=dict)
    cooldown_until: datetime | None = None
    cooldown_reason: str | None = None
    blocks: list[datetime] = field(default_factory=list)
    robots_sha256: str | None = None
    last_run: dict[str, Any] | None = None

    @classmethod
    def load(cls, path: Path) -> State:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        until = raw.get("cooldown_until")
        return cls(
            offsets={k: int(v) for k, v in raw.get("offsets", {}).items()},
            cooldown_until=datetime.fromisoformat(until) if until else None,
            cooldown_reason=raw.get("cooldown_reason"),
            blocks=[datetime.fromisoformat(b) for b in raw.get("blocks", [])],
            robots_sha256=raw.get("robots_sha256"),
            last_run=raw.get("last_run"),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "offsets": dict(sorted(self.offsets.items())),
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "cooldown_reason": self.cooldown_reason,
            "blocks": [b.isoformat() for b in self.blocks],
            "robots_sha256": self.robots_sha256,
            "last_run": self.last_run,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    def in_cooldown(self, now: datetime) -> bool:
        return self.cooldown_until is not None and now < self.cooldown_until

    def start_cooldown(self, now: datetime, reason: str, retry_after: int | None) -> datetime:
        repeated = any(now - b < REPEAT_WINDOW for b in self.blocks)
        length = REPEAT_COOLDOWN if repeated else FIRST_COOLDOWN
        if retry_after is not None:
            length = max(length, timedelta(seconds=retry_after))
        self.cooldown_until = now + length
        self.cooldown_reason = reason
        self.blocks = [*self.blocks, now][-20:]
        return self.cooldown_until
