"""Per-agent append-only JSONL memory for prior signals.

MVP backend is a flat file at MEMORY_ROOT/<agent>/signals.jsonl.
The skill interface (record / recall) is backend-agnostic — swap to
SQLite or Postgres later without touching callers."""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from core.models import Signal

log = logging.getLogger(__name__)

_ROOT = Path(os.getenv("MEMORY_ROOT", "audit_logs/memory"))


def _signals_path(agent: str) -> Path:
    p = _ROOT / agent / "signals.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(agent: str, run_id: str, signal: Signal, output: dict) -> None:
    """Append one line capturing the signal + what was delivered."""
    row = {
        "run_id": run_id,
        "agent": agent,
        "signal": signal.to_dict(),
        "output": output,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    path = _signals_path(agent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    log.info("memory: recorded run=%s → %s", run_id, path)


def recall(agent: str, fingerprint: str, n: int = 5) -> list[dict]:
    """Return up to `n` prior hits with matching fingerprint, newest first."""
    path = _signals_path(agent)
    if not path.exists():
        log.info("memory: no file for agent=%s — 0 prior hits", agent)
        return []

    hits: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("memory: skipping malformed line in %s", path)
                continue
            if row.get("signal", {}).get("fingerprint") == fingerprint:
                hits.append(row)

    log.info(
        "memory: recall agent=%s fingerprint=%s → %d prior hit(s)",
        agent, fingerprint, len(hits),
    )
    return list(reversed(hits))[:n]
