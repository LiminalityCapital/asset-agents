"""Domain-free data contracts that flow through the agent pipeline.

Kept dependency-light on purpose: no I/O, no logging, no business logic.
Every skill consumes or produces one of these; every agent composes them."""

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Observation:
    """A single numeric data point produced by an agent-specific probe.

    `value` is the quantity under test (signed). `context` carries the
    raw payload the agent needs later (prices, dates, labels — anything).
    Skills treat `context` as opaque; only the agent reads from it."""
    timestamp: str
    value: float
    context: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Rule:
    """Parameters for a threshold-evaluation rule. `name` keys the registry
    in core.skills.threshold; `params` is rule-specific and validated there."""
    name: str
    params: dict[str, Any]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Signal:
    """Structured output of threshold.evaluate when a rule fires.

    `fingerprint` is the stable key memory.recall uses to pull prior hits
    — same asset + same direction bucket should collide on purpose."""
    agent: str
    fingerprint: str
    rule: Rule
    observation: Observation
    history: list[Observation] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "fingerprint": self.fingerprint,
            "rule": self.rule.to_dict(),
            "observation": self.observation.to_dict(),
            "history": [o.to_dict() for o in self.history],
            "extra": self.extra,
        }
