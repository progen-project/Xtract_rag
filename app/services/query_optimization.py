"""
RAG Query Optimization Service
--------------------------------
Executes intent detection, query rewriting, HyDE, sub-query decomposition,
and metadata filter extraction in a single LLM call.

Exposes `run_optimized_search()` which handles:
  - Multi-query parallel search (if sub-queries are detected)
  - Result deduplication by chunk_id
  - Reranking via the existing RerankService
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from app.services.search_service import SearchResult, UnifiedSearchService

logger = logging.getLogger(__name__)


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class OptimizedQuery:
    """Holds the LLM-produced optimization outputs for a user query."""
    original_query: str
    is_searchable: bool = True
    rewritten_query: str = ""
    sub_queries: List[str] = field(default_factory=list)
    hyde_document: str = ""
    metadata_filters: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.rewritten_query:
            self.rewritten_query = self.original_query

    @property
    def all_search_queries(self) -> List[str]:
        """
        All query variants to run through the vector store.
        For multi-query: deduplicated sub-queries combined with HyDE text.
        For simple queries: single combined string of rewritten + HyDE.
        """
        if self.sub_queries:
            queries = list(dict.fromkeys(self.sub_queries))  # preserve order, deduplicate
            if self.hyde_document:
                queries.append(self.hyde_document)
            return queries

        # Single query: combine rewritten + HyDE for richer semantic signal
        combined = self.rewritten_query
        if self.hyde_document:
            combined = f"{self.rewritten_query}\n\n{self.hyde_document}"
        return [combined]


# ── Prompt ───────────────────────────────────────────────────────────────────

_OPTIMIZATION_SYSTEM = """\
You are an expert RAG query optimizer for a petroleum engineering document system.
Analyze the user's raw query and return ONLY a JSON object — no markdown, no extra text.

Fields:
1. is_searchable (bool): true if the query needs document retrieval; false for greetings/chitchat.
2. rewritten_query (str): concise, instruction-free search phrase.
   Strip words like "list", "summarize", "explain", "tell me about", "what is".
   Examples:
     "list all information about onboarding process" → "onboarding process"
     "can you summarize the refund policy"           → "refund policy"
3. sub_queries (list[str]): if the query is complex or comparative, break into ≤3 focused sub-queries.
   If not needed, return [].
   Example: "Compare drilling fluid types A and B" → ["drilling fluid type A", "drilling fluid type B"]
4. hyde_document (str): a 2-3 sentence hypothetical document excerpt that would answer the query.
   Write as if it were a passage found in a petroleum engineering report.
5. metadata_filters (dict): year, author, status, category, etc. extracted from the query. {} if none.

Output format (strict JSON):
{
  "is_searchable": true,
  "rewritten_query": "<concise search phrase>",
  "sub_queries": [],
  "hyde_document": "<hypothetical passage>",
  "metadata_filters": {}
}
"""


# ── Service ──────────────────────────────────────────────────────────────────

class QueryOptimizationService:
    """
    Optimizes a user query before retrieval, then orchestrates
    multi-query search with deduplication using existing infrastructure.
    """

    def __init__(self, llm_service):
        self.llm = llm_service

    # ------------------------------------------------------------------
    # Public: optimize
    # ------------------------------------------------------------------

    async def optimize_query(self, user_query: str) -> OptimizedQuery:
        """
        Call the LLM once to produce all optimization signals.
        Falls back to trivial pass-through on any failure.
        """
        try:
            raw = await self.llm.generate_direct_response(
                query=f'User question: "{user_query}"',
                system_prompt=_OPTIMIZATION_SYSTEM,
            )
            data = self._parse_json(raw)
            result = OptimizedQuery(
                original_query=user_query,
                is_searchable=bool(data.get("is_searchable", True)),
                rewritten_query=data.get("rewritten_query", "") or user_query,
                sub_queries=data.get("sub_queries", []),
                hyde_document=data.get("hyde_document", ""),
                metadata_filters=data.get("metadata_filters", {}),
            )
            logger.info(
                "Query optimized | searchable=%s | rewritten='%s' | "
                "sub_queries=%d | hyde=%s | filters=%s",
                result.is_searchable,
                result.rewritten_query,
                len(result.sub_queries),
                bool(result.hyde_document),
                result.metadata_filters or "none",
            )
            return result

        except Exception as exc:
            logger.warning("Query optimization failed (%s) — using original query.", exc)
            return OptimizedQuery(original_query=user_query)

    # ------------------------------------------------------------------
    # Public: optimized search (multi-query + dedup + rerank)
    # ------------------------------------------------------------------

    async def run_optimized_search(
        self,
        optimized: OptimizedQuery,
        search_service: "UnifiedSearchService",
        query_image_data: Optional[str] = None,
        top_k: int = 10,
        document_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None,
    ) -> "List[SearchResult]":
        """
        Run one search per query variant, merge results by identity,
        deduplicate by chunk_id, then rerank the merged pool.

        The caller's original `message` is NOT used here — only the
        optimized search queries are sent to the vector store.
        """
        queries = optimized.all_search_queries
        metadata_filters = optimized.metadata_filters or None

        # ── 1. Search for every query variant in parallel ─────────────
        tasks = [
            asyncio.to_thread(
                search_service.search,
                query_text=q,
                query_image_data=query_image_data,
                top_k=top_k,
                document_ids=document_ids,
                category_ids=category_ids,
                metadata_filters=metadata_filters,
                search_text=True,
                search_tables=True,
                search_images=True,
            )
            for q in queries
        ]
        batches: list[list] = await asyncio.gather(*tasks, return_exceptions=True)

        # ── 2. Merge + deduplicate by chunk_id (highest score wins) ──
        seen: Dict[str, "SearchResult"] = {}
        for batch in batches:
            if isinstance(batch, Exception):
                logger.warning("One search variant failed: %s", batch)
                continue
            for result in batch:
                key = result.chunk_id or result.image_id or result.table_id or result.content[:64]
                if key not in seen or result.score > seen[key].score:
                    seen[key] = result

        merged = sorted(seen.values(), key=lambda r: r.score, reverse=True)
        logger.info("Multi-query merge: %d unique results from %d queries", len(merged), len(queries))

        if not merged:
            return []

        # ── 3. Rerank merged pool using existing RerankService ────────
        from app.services.rerank_service import get_rerank_service
        reranker = get_rerank_service()
        if reranker.settings.use_reranker and merged:
            reranker.initialize()
            # Rerank against the rewritten query (not the noisy original)
            scores = reranker.rerank(
                query=optimized.rewritten_query,
                documents=[r.content for r in merged],
            )
            for result, score in zip(merged, scores):
                result.similarity_score = result.score  # preserve similarity
                result.score = score
            merged.sort(key=lambda r: r.score, reverse=True)
            logger.info("Reranking completed on merged multi-query pool.")

        # ── 4. Slice to final top-k ───────────────────────────────────
        final = merged[:reranker.settings.rerank_top_k if reranker.settings.use_reranker else top_k]
        logger.info("Optimized search returning %d results.", len(final))
        return final

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from potentially markdown-wrapped LLM output."""
        text = text.strip()
        # Strip <think> blocks from reasoning models
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        # Strip ```json ... ``` fences
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()
        return json.loads(text)


# ── Singleton ─────────────────────────────────────────────────────────────────

_optimizer: Optional[QueryOptimizationService] = None


def get_query_optimizer() -> QueryOptimizationService:
    """Return (lazily created) singleton optimizer, sharing the global LLM service."""
    global _optimizer
    if _optimizer is None:
        from app.services.llm_service import get_llm_service
        _optimizer = QueryOptimizationService(get_llm_service())
    return _optimizer
