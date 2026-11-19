"""Minimal robots.txt matcher (RFC 9309) with ``*`` and ``$`` support.

The standard library's ``urllib.robotparser`` treats ``*`` literally, which would
silently ignore rules such as SUUMO's ``Disallow: /*?*sort=``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str
    regex: re.Pattern[str]


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(regex + ("$" if anchored else ""))


class Robots:
    def __init__(self, text: str, product: str) -> None:
        self.product = product.lower()
        groups: list[tuple[list[str], list[Rule]]] = []
        agents: list[str] = []
        rules: list[Rule] = []
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (part.strip() for part in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and agents:
                    groups.append((agents, rules))
                    agents, rules = [], []
                agents.append(value.lower())
                last_was_agent = True
            elif key in ("allow", "disallow"):
                last_was_agent = False
                if agents and value:
                    rules.append(Rule(key == "allow", value, _compile(value)))
            else:
                last_was_agent = False
        if agents:
            groups.append((agents, rules))

        own = [r for names, rs in groups if self.product in names for r in rs]
        self.rules: list[Rule] = own or [r for names, rs in groups if "*" in names for r in rs]

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: Rule | None = None
        for rule in self.rules:
            if rule.regex.match(target) is None:
                continue
            if (
                best is None
                or len(rule.pattern) > len(best.pattern)
                or (len(rule.pattern) == len(best.pattern) and rule.allow)
            ):
                best = rule
        return best is None or best.allow

    def disallowed(self, urls: list[str]) -> list[str]:
        return [url for url in urls if not self.allowed(url)]
