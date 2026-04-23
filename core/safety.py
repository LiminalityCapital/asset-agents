"""Compliance gate: strip sentences with prohibited terms, append staleness caveat if needed."""

import logging
import re

log = logging.getLogger(__name__)


_PROHIBITED_PATTERNS = [
    r"\bbuy\b", r"\bsell\b",
    r"\brecommend\b", r"\brecommends\b", r"\bsuggest\b", r"\bsuggests\b",
    r"\bshould\b", r"\bmust\b",
    r"price target", r"will reach", r"could hit \d",
]


def check(message: str, assessment: str) -> tuple[str, bool]:
    """Returns (cleaned_message, gate_triggered)."""
    gate_triggered = False
    redacted_count = 0
    sentences = re.split(r"(?<=[.!?])\s+", message)
    cleaned_sentences: list[str] = []
    for s in sentences:
        if any(re.search(p, s, re.IGNORECASE) for p in _PROHIBITED_PATTERNS):
            gate_triggered = True
            redacted_count += 1
            cleaned_sentences.append("[REDACTED BY SAFETY GATE]")
        else:
            cleaned_sentences.append(s)
    cleaned = " ".join(cleaned_sentences)

    if assessment == "stale":
        cleaned += "\n\n_Caveat: latest supporting research is >14 days old._"

    if gate_triggered:
        log.warning("safety gate: redacted %d sentence(s)", redacted_count)
    else:
        log.info("safety gate: clean")

    return cleaned, gate_triggered
