"""Query-planning loop: tier-0 strategist probe, single LLM call for hypothesis + tier-1 queries, eval."""

import json
import logging
import os
from pathlib import Path

from openai import AzureOpenAI

from core.bagel_client import BagelClient
from core.audit import AuditLog

RELEVANCE_THRESHOLD = 1.5

log = logging.getLogger(__name__)


def run(trigger: dict, agent_dir: Path, audit: AuditLog, use_mock: bool = True) -> dict:
    skills = (agent_dir / "skills.md").read_text(encoding="utf-8")
    bagel = BagelClient(use_mock=use_mock)

    tier0_query = (
        f"banks long USD/JPY strategist thesis "
        f"{trigger['last_move_date']}..{trigger['t_date']}"
    )
    log.info("tier-0 probe starting")
    audit.add_query(tier0_query, tier=0)
    tier0_chunks = bagel.query(tier0_query)
    audit.add_chunks(tier0_chunks)

    log.info("calling LLM for plan (%d tier-0 chunks as context)", len(tier0_chunks))
    plan = _call_plan(skills, trigger, tier0_chunks)
    audit.set_plan(plan)
    log.info(
        "plan: desks=%s, %d tier-1 queries",
        plan.get("desks_identified", []),
        len(plan.get("queries", [])),
    )

    all_chunks = list(tier0_chunks)
    for i, q in enumerate(plan["queries"], 1):
        log.info("tier-1 %d/%d", i, len(plan["queries"]))
        audit.add_query(q, tier=1)
        chunks = bagel.query(q)
        audit.add_chunks(chunks)
        all_chunks.extend(chunks)

    unique_chunks = _dedupe(all_chunks)
    assessment = _evaluate(unique_chunks)
    audit.set_assessment(assessment)
    log.info(
        "after dedupe: %d unique chunks, assessment=%s",
        len(unique_chunks), assessment,
    )

    return {
        "chunks": unique_chunks,
        "hypothesis": plan["hypothesis"],
        "assessment": assessment,
    }


def _call_plan(skills: str, trigger: dict, tier0_chunks: list[dict]) -> dict:
    chunks_text = "\n\n".join(
        f"[{c['id']}] {c['parent_document_name']} (date: {c.get('report_date', 'n/a')}, score: {c.get('score', 'n/a')})\n{c['content']}"
        for c in tier0_chunks
    ) or "(no tier-0 chunks returned — BagelAI has no recent coverage)"

    user_msg = (
        "TRIGGER:\n"
        f"{json.dumps(trigger, indent=2)}\n\n"
        "TIER-0 CONTEXT CHUNKS:\n"
        f"{chunks_text}\n\n"
        "Follow your instructions. Return ONLY the JSON — no prose, no code fences."
    )

    client = AzureOpenAI(
        azure_endpoint=os.environ["ENDPOINT_URL"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["API_VERSION"],
    )
    resp = client.chat.completions.create(
        model=os.environ["DEPLOYMENT_NAME"],
        messages=[
            {"role": "system", "content": skills},
            {"role": "user", "content": user_msg},
        ],
        response_format={"type": "json_object"},
    )
    return _parse_json(resp.choices[0].message.content)


def _parse_json(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
        t = t.strip()
    return json.loads(t)


def _dedupe(chunks: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for c in chunks:
        if c["id"] in seen:
            continue
        seen.add(c["id"])
        out.append(c)
    return out


def _evaluate(chunks: list[dict]) -> str:
    relevant = [c for c in chunks if c.get("score", 0) > RELEVANCE_THRESHOLD]
    if not relevant:
        return "poor"
    if len(relevant) == 1:
        return "thin"
    if any(c.get("stale") for c in relevant):
        return "stale"
    return "good"
