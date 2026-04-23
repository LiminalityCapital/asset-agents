"""Second LLM call: chunks + confirmed price data + template -> alert message string."""

import json
import logging
import os
from pathlib import Path

from openai import AzureOpenAI

log = logging.getLogger(__name__)


def synthesize(trigger: dict, chunks: list[dict], hypothesis: str, agent_dir: Path) -> str:
    template = (agent_dir / "synthesis_template.md").read_text(encoding="utf-8")

    chunks_text = "\n\n".join(
        f"[{c['id']}] {c['parent_document_name']} (date: {c.get('report_date', 'n/a')})\n{c['content']}"
        for c in chunks
    )

    prompt = (
        "TRIGGER (confirmed price data):\n"
        f"{json.dumps(trigger, indent=2)}\n\n"
        f"HYPOTHESIS: {hypothesis}\n\n"
        "RESEARCH CHUNKS:\n"
        f"{chunks_text}\n\n"
        "OUTPUT TEMPLATE:\n"
        f"{template}\n\n"
        "Write the Teams alert message following the template. Do not mention document "
        "names, file names, or PDF filenames in the output. Do not recommend trades, "
        "positioning, or price targets."
    )

    log.info("synthesis: calling LLM with %d chunks", len(chunks))
    client = AzureOpenAI(
        azure_endpoint=os.environ["ENDPOINT_URL"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["API_VERSION"],
    )
    resp = client.chat.completions.create(
        model=os.environ["DEPLOYMENT_NAME"],
        messages=[{"role": "user", "content": prompt}],
    )
    result = resp.choices[0].message.content.strip()
    log.info("synthesis: LLM returned %d chars", len(result))
    return result
