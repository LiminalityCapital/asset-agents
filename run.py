"""Dispatcher.

Two subcommands:
  python run.py <agent>                           # normal cron-style run
  python run.py <agent> feedback <run_id> ...     # record analyst feedback

The normal run:
  1. threshold.evaluate(probe, rule)          → Signal | None
  2. memory.recall(fingerprint)               → prior hits (future: synthesis ctx)
  3. orchestrate(trigger) + synthesize + safety   (downstream unchanged)
  4. deliver (Teams + Bagel) if configured
  5. memory.record(signal, output)            → JSONL
"""

import argparse
import importlib
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Quiet third-party SDK chatter; keep our modules at the configured level.
for noisy in ("azure", "openai", "httpx", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from core.orchestrator import run as orchestrate
from core.synthesis import synthesize
from core.safety import check as safety_check
from core.audit import AuditLog
from core.skills import threshold, memory
from core.skills import feedback as feedback_skill
from core.teams import send as send_to_teams, TeamsError
from core.bagel_chat import precreate_session as precreate_bagel_session, BagelError

log = logging.getLogger("run")


def _resolve_agent_dir(agent_name: str) -> Path:
    agent_dir = Path(__file__).parent / "agents" / agent_name
    if not agent_dir.is_dir():
        print(f"Agent '{agent_name}' not found at {agent_dir}", file=sys.stderr)
        sys.exit(1)
    return agent_dir


def _load_agent_config(agent_name: str):
    try:
        return importlib.import_module(f"agents.{agent_name}.config")
    except ModuleNotFoundError:
        print(f"No config module for agent '{agent_name}'", file=sys.stderr)
        sys.exit(1)


def _trigger_dict_from_signal(signal) -> dict:
    """Translate a Signal into the legacy trigger dict that orchestrator/
    synthesis/audit currently consume. Keeps downstream untouched during
    the threshold-skill migration."""
    ctx = signal.observation.context
    pair_raw = ctx.get("pair", "")
    pair_display = (
        f"{pair_raw[:3]}/{pair_raw[3:]}" if len(pair_raw) == 6 else pair_raw
    )
    base_ccy = pair_raw[:3] if len(pair_raw) == 6 else pair_raw
    quote_ccy = pair_raw[3:] if len(pair_raw) == 6 else ""
    asset = quote_ccy or base_ccy

    direction_raw = signal.extra.get("direction", "up")
    direction_label = "USD_strong" if direction_raw == "up" else "USD_weak"

    return {
        "pair": pair_display,
        "asset": asset,
        "direction": direction_label,
        "pct_change": round(signal.observation.value, 2),
        "price": ctx.get("t_close"),
        "prior_price": ctx.get("t1_close"),
        "t_date": ctx.get("t_date"),
        "last_move_date": ctx.get("t1_date"),
    }


def cmd_run(agent_name: str) -> None:
    agent_dir = _resolve_agent_dir(agent_name)
    config = _load_agent_config(agent_name)

    use_mock = os.getenv("USE_MOCK", "1") == "1"
    log.info("start: agent=%s use_mock=%s", agent_name, use_mock)

    signal = threshold.evaluate(agent_name, config.PROBE, config.RULE)
    if signal is None:
        log.info("threshold not fired for %s — no alert", config.PRICE_KEY)
        print(f"[{agent_name}] threshold not fired — no alert.")
        return

    log.info(
        "signal: fingerprint=%s direction=%s value=%+.4f",
        signal.fingerprint,
        signal.extra.get("direction"),
        signal.observation.value,
    )

    prior_hits = memory.recall(agent_name, signal.fingerprint, n=5)
    log.info(
        "memory: %d prior hit(s) available (future: inject into synthesis)",
        len(prior_hits),
    )

    trigger = _trigger_dict_from_signal(signal)
    log.info(
        "trigger: %s %+.2f%% (%.2f on %s → %.2f on %s)",
        trigger["pair"], trigger["pct_change"],
        trigger["prior_price"], trigger["last_move_date"],
        trigger["price"], trigger["t_date"],
    )

    audit = AuditLog(trigger)
    plan = orchestrate(trigger, agent_dir, audit, use_mock=use_mock)
    raw = synthesize(trigger, plan["chunks"], plan["hypothesis"], agent_dir)
    message, gate_triggered = safety_check(raw, plan["assessment"])
    audit.set_gate(gate_triggered)
    audit.set_final(message)

    sep = "=" * 60
    print(sep)
    print("TEAMS ALERT MESSAGE")
    print(sep)
    print(message)
    print()

    bagel_session_id: str | None = None
    if os.getenv("TEAMS_WEBHOOK_URL"):
        direction = "down" if trigger["pct_change"] < 0 else "up"
        title = f"{trigger['pair']} {direction} {abs(trigger['pct_change']):.2f}%"
        facts = {
            "Latest": f"{trigger['price']} ({trigger['t_date']})",
            "Prior": f"{trigger['prior_price']} ({trigger['last_move_date']})",
            "Change": f"{trigger['pct_change']:+.2f}%",
        }
        footer = f"asset-agents · run {audit.data['run_id']}"

        bagel_base = os.getenv("BAGEL_CHAT_URL", "").rstrip("/")
        link = None
        if bagel_base:
            question_template = getattr(config, "BAGEL_FOLLOWUP_QUESTION", None)
            if question_template and os.getenv("BAGEL_USER_ID"):
                try:
                    question = question_template.format(
                        pair=trigger["pair"],
                        direction=direction,
                        pct_abs=f"{abs(trigger['pct_change']):.2f}",
                        t_date=trigger["t_date"],
                    )
                    bagel_session_id = precreate_bagel_session(question)
                    link = ("Explore in Bagel", f"{bagel_base}/?session={bagel_session_id}")
                    log.info("bagel: pre-created session %s", bagel_session_id)
                except BagelError as e:
                    log.warning("bagel: pre-create failed, using home URL: %s", e)
                    link = ("Explore in Bagel", bagel_base)
            else:
                link = ("Explore in Bagel", bagel_base)

        try:
            send_to_teams(message, title=title, facts=facts, footer=footer, link=link)
            log.info("teams: posted via webhook")
        except TeamsError as e:
            log.error("teams: send failed: %s", e)
    else:
        log.info("teams: TEAMS_WEBHOOK_URL not set; skipping send")

    memory.record(
        agent=agent_name,
        run_id=audit.data["run_id"],
        signal=signal,
        output={
            "hypothesis": plan.get("hypothesis"),
            "assessment": plan.get("assessment"),
            "message_final": message,
            "gate_triggered": gate_triggered,
            "bagel_session_id": bagel_session_id,
        },
    )

    print(sep)
    print("AUDIT LOG")
    print(sep)
    print(audit.to_json())


def cmd_feedback(agent_name: str, argv: list[str]) -> None:
    """python run.py <agent> feedback <run_id> --rating -1 --tag noise --note "..." """
    config = _load_agent_config(agent_name)

    p = argparse.ArgumentParser(prog=f"run.py {agent_name} feedback")
    p.add_argument("run_id")
    p.add_argument("--rating", type=int, required=True, choices=[-1, 0, 1])
    p.add_argument(
        "--tag",
        action="append",
        default=[],
        dest="tags",
        help="Repeatable (--tag noise --tag boj_regime).",
    )
    p.add_argument("--note", default="")
    p.add_argument(
        "--source", default="cli", choices=list(feedback_skill.VALID_SOURCES)
    )
    p.add_argument(
        "--actor",
        default=os.getenv("USER") or os.getenv("USERNAME") or "unknown",
    )
    args = p.parse_args(argv)

    event = feedback_skill.record(
        agent=agent_name,
        run_id=args.run_id,
        rating=args.rating,
        tags=args.tags,
        note=args.note,
        source=args.source,
        actor=args.actor,
        tag_vocab=getattr(config, "FEEDBACK_TAG_VOCAB", None),
    )
    print(f"recorded feedback {event['feedback_id']} for run {args.run_id}")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage:\n"
            "  python run.py <agent_name>\n"
            "  python run.py <agent_name> feedback <run_id> "
            "--rating {-1|0|1} [--tag T]* [--note \"...\"]",
            file=sys.stderr,
        )
        sys.exit(1)

    agent_name = sys.argv[1]
    rest = sys.argv[2:]

    if rest and rest[0] == "feedback":
        cmd_feedback(agent_name, rest[1:])
    else:
        cmd_run(agent_name)


if __name__ == "__main__":
    main()
