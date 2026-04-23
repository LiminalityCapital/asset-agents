# asset-agents

Event-triggered RAG pipeline. A coded threshold fires on a market move; an LLM plans retrieval queries against internal research (Azure AI Search); a second LLM narrates a compliance-gated Teams alert. Per-run memory and analyst feedback persist in JSONL.

See [docs/architecture.md](docs/architecture.md) for the system design, data contracts, and extension guide.

## Layout

```
asset-agents/
  core/
    tools/           thin I/O wrappers (postgres, …)
    skills/          reusable capabilities (threshold, memory, feedback)
    orchestrator.py  RAG planning + query loop
    synthesis.py     LLM message synthesis
    safety.py        compliance gate
    teams.py, bagel_chat.py, bagel_client.py   delivery + retrieval
    audit.py, models.py
  agents/
    jpy/             JPY agent: probe + config + templates
  run.py             dispatcher: python run.py <agent> [feedback <run_id> …]
```

Per-agent folders hold the probe, rule, tag vocab, and templates. Everything reusable sits in `core/`.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # fill in keys — see Environment below
python run.py jpy
```

## Environment

Minimum for an end-to-end run:

- **Azure OpenAI** — `ENDPOINT_URL`, `AZURE_OPENAI_API_KEY`, `DEPLOYMENT_NAME`, `API_VERSION`.
- **Azure AI Search** — `SEARCH_ENDPOINT`, `SEARCH_KEY`, `SEARCH_INDEX_NAME`.
- **Postgres** (optional) — `DATABASE_URL` for the live FX probe. If unset, the probe falls back to an in-repo mock series so the pipeline still runs end-to-end locally.

Optional:

- `USE_MOCK=1` — swap retrieval to hardcoded strategist-report chunks (still calls Azure OpenAI).
- `TEAMS_WEBHOOK_URL` — Power Automate webhook. Unset → alert just prints locally.
- `BAGEL_CHAT_URL` + `BAGEL_USER_ID` — pre-creates a Bagel chat session seeded with a templated follow-up question so the Teams "Explore in Bagel" button lands on a chat that already has Q and A.
- `LOG_LEVEL` — default `INFO`. Set `DEBUG` for verbose probe / retrieval / safety traces.

## Subcommands

```
python run.py <agent>                                                  # normal run
python run.py <agent> feedback <run_id> --rating {-1,0,1} \
    --tag <tag> --note "..." [--source cli|teams_reaction|...]         # analyst feedback
```

Feedback appends to `audit_logs/memory/<agent>/feedback.jsonl` and rolls up into 30-day noise/actionable rates intended for future synthesis prompts (plumbing in place, LLM injection pending — see [docs/architecture.md §8](docs/architecture.md#8-deferred--not-yet-built)).

## Retrieval

Currently calls Azure AI Search (`liminality-chunk-index`) directly via [core/bagel_client.py](core/bagel_client.py). Planned migration: swap to a BagelAI `/retrieve` endpoint once exposed so agents inherit query expansion, hybrid search, and access control centrally.
