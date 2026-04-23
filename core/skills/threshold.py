"""Reusable threshold evaluator.

Takes an agent-supplied `probe` (callable returning numeric observations)
and a `Rule`. Returns a Signal when the rule fires, else None.

Rule logic lives in a registry — add a new metric by dropping one function
and one entry in `_RULES`. No caller changes."""

import logging
from typing import Callable

from core.models import Observation, Rule, Signal

log = logging.getLogger(__name__)

Probe = Callable[[], list[Observation]]


def _fingerprint(agent: str, observation: Observation, direction: str) -> str:
    """Stable key memory.recall groups prior hits by. Same asset + same
    direction bucket collide intentionally so the LLM sees related history."""
    pair = observation.context.get("pair", "?")
    return f"{agent}:{pair}:{direction}"


def _crosses_signed_threshold(
    agent: str, observations: list[Observation], rule: Rule
) -> Signal | None:
    """Sign of `threshold` picks direction:
      threshold > 0 → fire when value >= threshold (up move)
      threshold < 0 → fire when value <= threshold (down move)."""
    if not observations:
        log.info("threshold: probe returned no observations — aborting")
        return None

    threshold = float(rule.params["threshold"])
    obs = observations[0]
    log.info(
        "threshold: value=%+.4f threshold=%+.2f", obs.value, threshold
    )

    fired_up = threshold >= 0 and obs.value >= threshold
    fired_down = threshold < 0 and obs.value <= threshold
    if not (fired_up or fired_down):
        log.info("threshold: NOT fired (move within threshold)")
        return None

    direction = "up" if fired_up else "down"
    log.info(
        "threshold: FIRED (direction=%s, value=%+.4f)", direction, obs.value
    )

    return Signal(
        agent=agent,
        fingerprint=_fingerprint(agent, obs, direction),
        rule=rule,
        observation=obs,
        history=observations[1:],
        extra={"direction": direction},
    )


_RULES: dict[str, Callable[[str, list[Observation], Rule], Signal | None]] = {
    "crosses_signed_threshold": _crosses_signed_threshold,
}


def evaluate(agent: str, probe: Probe, rule: Rule) -> Signal | None:
    log.info(
        "threshold: evaluate agent=%s rule=%s params=%s",
        agent, rule.name, rule.params,
    )
    fn = _RULES.get(rule.name)
    if fn is None:
        raise ValueError(
            f"Unknown threshold rule: {rule.name!r}. "
            f"Known rules: {sorted(_RULES)}"
        )
    observations = probe()
    log.info("threshold: probe returned %d observation(s)", len(observations))
    return fn(agent, observations, rule)
