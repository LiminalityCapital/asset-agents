"""Retrieval client. Mock mode returns fixed strategist-report chunks; live mode hits Azure AI Search (hybrid semantic+vector)."""

import logging
import os

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizableTextQuery


_TIER0_CHUNKS = [
    {
        "id": "gs_fx_weekly_0418",
        "parent_document_name": "Goldman_FX_Weekly_2026-04-18.pdf",
        "report_date": "2026-04-18",
        "score": 2.4,
        "content": (
            "GS FX maintains a long USD/JPY bias into Q2, anchored on sticky US services "
            "inflation and a BoJ that has telegraphed patience on normalization. The conviction "
            "is on the rate-differential trajectory. Alt-trade menu discussed: long USD/CHF as "
            "a dollar expression with less BoJ-intervention tail risk; long 1m USD/JPY risk "
            "reversals as a skew hedge."
        ),
    },
    {
        "id": "ms_fx_alpha_0417",
        "parent_document_name": "MorganStanley_FX_Alpha_2026-04-17.pdf",
        "report_date": "2026-04-17",
        "score": 2.2,
        "content": (
            "MS FX strategy holds a constructive USD/JPY view premised on widening 10y yield "
            "spreads and resilient US carry. A dovish-BoJ counter-scenario is sketched: in that "
            "state the preferred expressions are long JPY calls vs AUD (carry-to-haven switch) "
            "and long JPY vs KRW."
        ),
    },
    {
        "id": "jpm_fx_monthly_0410",
        "parent_document_name": "JPMorgan_FX_Monthly_2026-04-10.pdf",
        "report_date": "2026-04-10",
        "score": 1.9,
        "content": (
            "JPM retains a long USD/JPY stance with conviction around rate-differential "
            "persistence. Tail-risk menu flagged: long 2m 25-delta JPY calls and long JPY vs "
            "EM Asia FX into any risk-off flare."
        ),
    },
]

_TIER1_DESK_CHUNKS = [
    {
        "id": "gs_fx_weekly_0418_alt",
        "parent_document_name": "Goldman_FX_Weekly_2026-04-18.pdf",
        "report_date": "2026-04-18",
        "score": 2.1,
        "content": (
            "Conditional on yen strength materializing, GS has three pre-pitched hedges in its "
            "alt book: (1) long USD/CHF as a pure dollar play that sidesteps BoJ/MoF "
            "intervention risk, (2) long JPY calls vs AUD to monetize the carry-to-haven "
            "rotation, (3) receiver swaptions on USD rates."
        ),
    },
    {
        "id": "ms_fx_playbook_0414",
        "parent_document_name": "MorganStanley_FX_Playbook_2026-04-14.pdf",
        "report_date": "2026-04-14",
        "score": 2.0,
        "content": (
            "MS 'weaker-dollar' playbook: preferred expressions are long JPY vs AUD and KRW, "
            "long EUR/USD on the ECB–Fed convergence narrative, and an underweight in USD "
            "high-yield credit."
        ),
    },
]


_SEMANTIC_CONFIG = "my-semantic-config"
_VECTOR_FIELD = "content_vector"
_SELECT_FIELDS = ["id", "content", "parent_document_name", "last_modified"]
_SEARCH_TIMEOUT_S = 30

log = logging.getLogger(__name__)


class BagelClient:
    def __init__(self, use_mock: bool = True):
        self.use_mock = use_mock
        if use_mock:
            log.info("BagelClient: mock mode")
            return
        endpoint = os.environ["SEARCH_ENDPOINT"]
        key = os.environ["SEARCH_KEY"]
        index = os.environ["SEARCH_INDEX_NAME"]
        self.top_k = int(os.getenv("RETRIEVAL_DEFAULT_TOP_K", "20"))
        self.mode = os.getenv("RETRIEVAL_MODE", "hybrid").lower()
        log.info(
            "BagelClient: live index=%s mode=%s top_k=%d endpoint=%s",
            index, self.mode, self.top_k, endpoint,
        )
        self.client = SearchClient(
            endpoint=endpoint,
            index_name=index,
            credential=AzureKeyCredential(key),
        )

    def query(self, q: str) -> list[dict]:
        mode = "mock" if self.use_mock else "live"
        log.info("[%s] query: %r", mode, q)
        chunks = self._mock_query(q) if self.use_mock else self._live_query(q)
        log.info(
            "[%s] got %d chunks: %s",
            mode, len(chunks), [c["id"] for c in chunks],
        )
        return chunks

    def _mock_query(self, q: str) -> list[dict]:
        ql = q.lower()
        if "strategist" in ql or ("long usd" in ql and "jpy" in ql):
            return list(_TIER0_CHUNKS)
        if any(k in ql for k in (
            "goldman", "morgan stanley", "jp morgan", "jpmorgan",
            "alt", "alternative", "hedge", "playbook", "calls",
        )):
            return list(_TIER1_DESK_CHUNKS)
        return []

    def _live_query(self, q: str) -> list[dict]:
        kwargs = {
            "search_text": q,
            "query_type": "semantic",
            "semantic_configuration_name": _SEMANTIC_CONFIG,
            "top": self.top_k,
            "select": _SELECT_FIELDS,
        }
        if self.mode == "hybrid":
            kwargs["vector_queries"] = [
                VectorizableTextQuery(text=q, k=self.top_k, fields=_VECTOR_FIELD)
            ]
        results = self.client.search(timeout=_SEARCH_TIMEOUT_S, **kwargs)
        chunks: list[dict] = []
        for r in results:
            last_modified = r.get("last_modified")
            chunks.append({
                "id": r.get("id"),
                "parent_document_name": r.get("parent_document_name") or "Unknown",
                "report_date": last_modified[:10] if isinstance(last_modified, str) else None,
                "score": r.get("@search.reranker_score") or r.get("@search.score") or 0.0,
                "content": r.get("content") or "",
            })
        return chunks
