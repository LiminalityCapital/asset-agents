"""Audit log record: run_id, trigger, queries, chunks, assessment, gate, final message."""

import json
import uuid
from datetime import datetime, timezone


class AuditLog:
    def __init__(self, trigger: dict):
        self.data = {
            "run_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "trigger_values": trigger,
            "queries_tried": [],
            "chunks_retrieved": [],
            "hypothesis": None,
            "desks_identified": None,
            "reasoning": None,
            "eval_assessment": None,
            "safety_gate_triggered": None,
            "final_message": None,
        }

    def add_query(self, q: str, tier: int) -> None:
        self.data["queries_tried"].append({"tier": tier, "query": q})

    def add_chunks(self, chunks: list[dict]) -> None:
        for c in chunks:
            self.data["chunks_retrieved"].append({
                "id": c["id"],
                "parent_document_name": c.get("parent_document_name"),
                "report_date": c.get("report_date"),
                "score": c.get("score"),
            })

    def set_plan(self, plan: dict) -> None:
        self.data["hypothesis"] = plan.get("hypothesis")
        self.data["desks_identified"] = plan.get("desks_identified")
        self.data["reasoning"] = plan.get("reasoning")

    def set_assessment(self, a: str) -> None:
        self.data["eval_assessment"] = a

    def set_gate(self, triggered: bool) -> None:
        self.data["safety_gate_triggered"] = triggered

    def set_final(self, msg: str) -> None:
        self.data["final_message"] = msg

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2)
