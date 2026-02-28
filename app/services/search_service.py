"""
Unified search service across text, tables, and images collections.
Handles retrieval from all Qdrant collections and merging results.
"""
from typing import List, Optional, Dict, Any
import logging
from dataclasses import dataclass
from qdrant_client.models import SparseVector
from fastembed import SparseTextEmbedding

from app.services.rerank_service import get_rerank_service
from app.services.indexer import get_indexer
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Unified search result from any collection."""
    content: str
    score: float
    source_type: str  # "text", "table", "image"
    document_id: str
    page_number: int
    section_title: str = ""
    similarity_score: float = 0.0  # Original pre-rerank score

    # Type-specific fields
    chunk_id: Optional[str] = None
    table_id: Optional[str] = None
    image_id: Optional[str] = None
    image_path: Optional[str] = None

    # Associated IDs
    related_image_ids: List[str] = None
    related_table_ids: List[str] = None

    def __post_init__(self):
        if self.related_image_ids is None:
            self.related_image_ids = []
        if self.related_table_ids is None:
            self.related_table_ids = []


class UnifiedSearchService:
    """
    Performs unified search across text chunks, tables, and images.
    Merges and ranks results by relevance.
    """

    def __init__(self, indexer, embed_model):
        self.indexer = indexer
        self.embed_model = indexer.embed_model
        self.sparse_embed_model = indexer.sparse_embed_model
        self.qdrant_client = indexer.qdrant_client
        self.settings = indexer.settings
        self.rerank_service = get_rerank_service()

    def search(
        self,
        query_text: str,
        query_image_data: Optional[str] = None,
        top_k: int = get_settings().top_k,
        document_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None,
        search_text: bool = True,
        search_tables: bool = True,
        search_images: bool = True,
        alpha_text: float = 0.5,
        alpha_tables: float = 0.3,
        alpha_images: float = 0.2,
    ) -> List[SearchResult]:
        """
        Unified search across all collections.

        Pipeline:
            1. Search all collections (similarity scores)
            2. Apply weighted scores
            3. Filter by similarity threshold  ← على scores أصلية
            4. Rerank filtered candidates       ← ترتيب فقط
            5. Slice final top_k
            6. Fallback لو النتائج صفر

        Args:
            query_text: Text query
            query_image_data: Optional base64 image for image search
            top_k: Total number of results to return
            document_ids: Filter by documents
            category_ids: Filter by categories
            search_text: Include text chunks
            search_tables: Include tables
            search_images: Include images
            alpha_*: Weights for each type (should sum to 1.0)

        Returns:
            List of unified SearchResult objects sorted by score
        """
        all_results = []

        active_searches = sum([search_text, search_tables, search_images])
        if active_searches == 0:
            return []

        per_collection_k = max(3, top_k // active_searches)
        filters = self._build_filters(document_ids, category_ids)

        # ── 1. Search all collections ──────────────────────────────────────
        if search_text:
            text_results = self._search_text(query_text, per_collection_k, filters)
            for result in text_results:
                result.score *= alpha_text
            all_results.extend(text_results)
            logger.info(f"Text search: {len(text_results)} results")

        if search_tables:
            table_results = self._search_tables(query_text, per_collection_k, filters)
            for result in table_results:
                result.score *= alpha_tables
            all_results.extend(table_results)
            logger.info(f"Table search: {len(table_results)} results")

        if search_images:
            image_results = self._search_images(
                query_text, query_image_data, per_collection_k, filters
            )
            for result in image_results:
                result.score *= alpha_images
            all_results.extend(image_results)
            logger.info(f"Image search: {len(image_results)} results")

        if not all_results:
            logger.info("Unified search returned 0 results (no collection results)")
            return []

        # Sort by weighted similarity score
        all_results.sort(key=lambda x: x.score, reverse=True)
        candidates = all_results[:top_k]

        # ── 2. Filter by similarity threshold BEFORE reranking ────────────
        # الـ threshold ينطبق هنا على الـ similarity scores الأصلية (موثوقة)
        # مش على الـ cross-encoder scores اللي ممكن تكون في range مختلف
        threshold = self.settings.similarity_threshold
        if threshold > 0:
            initial_count = len(candidates)
            candidates = [res for res in candidates if res.score >= threshold]
            removed = initial_count - len(candidates)
            if removed > 0:
                logger.info(
                    f"Filtered out {removed} results below similarity threshold {threshold}"
                )

        # ── 3. Fallback: لو الـ threshold شيل الكل ────────────────────────
        # نرجع أفضل 3 على الأقل بدون فلترة بدل ما نرجع صفر
        if not candidates and all_results:
            fallback_n = min(3, len(all_results))
            candidates = all_results[:fallback_n]
            logger.warning(
                f"All results below threshold {threshold} — "
                f"using top-{fallback_n} fallback (no threshold applied)"
            )

        # ── 4. Rerank الـ candidates المتبقية ─────────────────────────────
        # الـ reranker بيرتب فقط — مش بيفلتر
        # الـ sigmoid normalized scores (0-1) بتُستخدم للترتيب مش للـ threshold
        if self.settings.use_reranker and candidates:
            logger.info(f"Reranking {len(candidates)} candidates...")
            self.rerank_service.initialize()

            doc_texts = [res.content for res in candidates]
            rerank_scores = self.rerank_service.rerank(query_text, doc_texts)

            for i, score in enumerate(rerank_scores):
                candidates[i].similarity_score = candidates[i].score  # preserve original
                candidates[i].score = score

            candidates.sort(key=lambda x: x.score, reverse=True)
            logger.info("Reranking completed")

        # ── 5. Final slice ─────────────────────────────────────────────────
        final_top_k = self.settings.rerank_top_k
        final_results = candidates[:final_top_k]
        logger.info(
            f"Unified search returned {len(final_results)} results "
            f"(from {len(all_results)} initial candidates)"
        )

        return final_results

    def _build_filters(
        self,
        document_ids: Optional[List[str]],
        category_ids: Optional[List[str]],
    ):
        """
        Build Qdrant filters for document/category.
        
        Priority: document_ids > category_ids > None
        The controller resolves ambiguity before this point via
        _resolve_search_filters(), so typically only one of these
        will be non-empty.
        """
        from qdrant_client.models import Filter, FieldCondition, MatchAny

        # Document-level filter takes priority (most specific)
        if document_ids:
            return Filter(must=[
                FieldCondition(key="document_id", match=MatchAny(any=document_ids))
            ])

        # Category-level filter as fallback
        if category_ids:
            return Filter(must=[
                FieldCondition(key="category_id", match=MatchAny(any=category_ids))
            ])

        # No filter — search everything
        return None

    def _search_text(
        self,
        query: str,
        top_k: int,
        filters,
    ) -> List[SearchResult]:
        """Search text chunks collection using hybrid RRF."""
        try:
            dense_embedding = self.embed_model.get_text_embedding(query)
            sparse_gen = list(self.sparse_embed_model.embed([query]))[0]
            sparse_vector = SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist(),
            )

            from qdrant_client.models import Prefetch, FusionQuery

            results = self.qdrant_client.query_points(
                collection_name=self.settings.qdrant_collection,
                prefetch=[
                    Prefetch(
                        query=dense_embedding,
                        using="dense",
                        filter=filters,
                        limit=top_k,
                    ),
                    Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        filter=filters,
                        limit=top_k,
                    ),
                ],
                query=FusionQuery(fusion="rrf"),
                limit=top_k,
            )

            points = results.points if hasattr(results, "points") else results

            search_results = []
            for point in points:
                payload = point.payload

                image_ids = []
                table_ids = []

                if payload.get("image_ids"):
                    image_ids = (
                        payload["image_ids"].split(",")
                        if isinstance(payload["image_ids"], str)
                        else payload["image_ids"]
                    )

                if payload.get("table_ids"):
                    table_ids = (
                        payload["table_ids"].split(",")
                        if isinstance(payload["table_ids"], str)
                        else payload["table_ids"]
                    )

                search_results.append(
                    SearchResult(
                        content=payload.get("text", ""),
                        score=point.score,
                        source_type="text",
                        document_id=payload.get("document_id", ""),
                        page_number=payload.get("page_start", 0),
                        section_title=payload.get("section_title", ""),
                        chunk_id=payload.get("chunk_id", ""),
                        related_image_ids=image_ids,
                        related_table_ids=table_ids,
                    )
                )

            return search_results

        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []

    def _search_tables(
        self,
        query: str,
        top_k: int,
        filters,
    ) -> List[SearchResult]:
        """Search tables collection using hybrid RRF."""
        try:
            table_collection = f"{self.settings.qdrant_collection}_tables"

            dense_embedding = self.embed_model.get_text_embedding(query)
            sparse_gen = list(self.sparse_embed_model.embed([query]))[0]
            sparse_vector = SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist(),
            )

            from qdrant_client.models import Prefetch, FusionQuery

            results = self.qdrant_client.query_points(
                collection_name=table_collection,
                prefetch=[
                    Prefetch(
                        query=dense_embedding,
                        using="dense",
                        filter=filters,
                        limit=top_k,
                    ),
                    Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        filter=filters,
                        limit=top_k,
                    ),
                ],
                query=FusionQuery(fusion="rrf"),
                limit=top_k,
            )

            points = results.points if hasattr(results, "points") else results

            search_results = []
            for point in points:
                payload = point.payload

                content = f"[Table on page {payload.get('page_number', '?')}]\n"
                if payload.get("section_title"):
                    content += f"Section: {payload['section_title']}\n"
                if payload.get("markdown"):
                    content += payload["markdown"][:1000]

                search_results.append(
                    SearchResult(
                        content=content,
                        score=point.score,
                        source_type="table",
                        document_id=payload.get("document_id", ""),
                        page_number=payload.get("page_number", 0),
                        section_title=payload.get("section_title", ""),
                        table_id=payload.get("table_id", ""),
                    )
                )

            return search_results

        except Exception as e:
            logger.error(f"Table search failed: {e}")
            return []

    def _search_images(
        self,
        query_text: Optional[str],
        query_image_data: Optional[str],
        top_k: int,
        filters,
    ) -> List[SearchResult]:
        """Search images collection."""
        try:
            image_collection = f"{self.settings.qdrant_collection}_images"

            embedding = None

            if query_image_data:
                from app.services.image_embedder import get_image_embedder
                embedder = get_image_embedder()
                embedder.initialize()
                # Image-only embedding for visual similarity search
                embedding = embedder.embed_image(query_image_data)
            elif query_text:
                from app.services.image_embedder import get_image_embedder
                embedder = get_image_embedder()
                embedder.initialize()
                embedding = embedder.embed_text(query_text)

            if not embedding:
                return []

            results = self.qdrant_client.query_points(
                collection_name=image_collection,
                query=embedding,
                limit=top_k,
                query_filter=filters,
            )

            points = results.points if hasattr(results, "points") else results

            search_results = []
            for point in points:
                payload = point.payload

                # ── بناء content غني للـ reranker ──────────────────────────
                # الـ cross-encoder محتاج نص كافي عشان يقدر يحكم على الـ relevance
                # بدون analysis/caption، الـ image content هزيل → score سالب جداً
                content_parts = [
                    f"[Image on page {payload.get('page_number', '?')}]"
                ]
                if payload.get("section_title"):
                    content_parts.append(f"Section: {payload['section_title']}")
                if payload.get("caption"):
                    content_parts.append(f"Caption: {payload['caption']}")
                if payload.get("analysis"):
                    # الـ analysis هو الأغنى — بيحتوي على وصف تفصيلي من الـ vision model
                    content_parts.append(f"Analysis: {payload['analysis']}")

                content = "\n".join(content_parts)

                search_results.append(
                    SearchResult(
                        content=content,
                        score=point.score,
                        source_type="image",
                        document_id=payload.get("document_id", ""),
                        page_number=payload.get("page_number", 0),
                        section_title=payload.get("section_title", ""),
                        image_id=payload.get("image_id", ""),
                        image_path=payload.get("image_path", ""),
                    )
                )

            return search_results

        except Exception as e:
            logger.error(f"Image search failed: {e}")
            return []

indexer = get_indexer()
search_service = UnifiedSearchService(indexer, indexer.embed_model)

def get_search_service() -> UnifiedSearchService:
    """Dependency for search service."""
    return search_service

