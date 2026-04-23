"""Per-agent append-only JSONL feedback store + 30-day rollup.

MVP ingestion is CLI-only (see run.py `feedback` subcommand). Deferred
sources (Teams reaction webhook, Bagel engagement) append to the same
file with different `source` tags; no schema change needed."""

import json
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

_ROOT = Path(os.getenv("MEMORY_ROOT", "audit_logs/memory"))

VALID_RATINGS = (-1, 0, 1)
VALID_SOURCES = ("cli", "teams_reaction", "bagel_engagement", "implicit_no_click")


def _feedback_path(agent: str) -> Path:
    p = _ROOT / agent / "feedback.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(
    *,
    agent: str,
    run_id: str,
    rating: int,
    tags: list[str],
    note: str = "",
    source: str = "cli",
    actor: str = "unknown",
    tag_vocab: list[str] | None = None,
) -> dict:
    """Append one feedback event. Unknown tags warn but are accepted so
    analysts can surface new patterns without a config change."""
    if rating not in VALID_RATINGS:
        raise ValueError(f"rating must be one of {VALID_RATINGS} (got {rating!r})")
    if source not in VALID_SOURCES:
        raise ValueError(f"source must be one of {VALID_SOURCES} (got {source!r})")

    if tag_vocab is not None:
        unknown = [t for t in tags if t not in tag_vocab]
        if unknown:
            log.warning(
                "feedback: unknown tag(s) %s — accepted (vocab drift expected)",
                unknown,
            )

    event = {
        "feedback_id": f"fb_{uuid.uuid4().hex}",
        "run_id": run_id,
        "agent": agent,
        "rating": rating,
        "tags": list(tags),
        "note": note,
        "source": source,
        "actor": actor,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _feedback_path(agent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")
    log.info(
        "feedback: recorded %s run=%s rating=%d source=%s",
        event["feedback_id"], run_id, rating, source,
    )
    return event


def rollup(agent: str, window_days: int = 30) -> dict:
    """Summarize recent feedback for injection into the synthesis prompt.

    Returns n, noise %, actionable %, and top 5 tags by frequency.
    Empty rollup (n=0) when no feedback exists — synthesis should skip it."""
    path = _feedback_path(agent)
    empty = {"n": 0, "noise_pct": 0.0, "actionable_pct": 0.0, "top_tags": []}
    if not path.exists():
        return empty

    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                received = datetime.fromisoformat(row["received_at"])
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
            if received >= cutoff:
                rows.append(row)

    n = len(rows)
    if n == 0:
        return empty

    noise = sum(1 for r in rows if r.get("rating") == -1)
    actionable = sum(1 for r in rows if r.get("rating") == 1)

    tag_counts: dict[str, int] = {}
    for r in rows:
        for t in r.get("tags", []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top = sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]

    return {
        "n": n,
        "noise_pct": round(noise / n, 2),
        "actionable_pct": round(actionable / n, 2),
        "top_tags": top,
    }
