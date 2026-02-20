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
        # Use indexer's sparse model
        self.sparse_embed_model = indexer.sparse_embed_model
        self.qdrant_client = indexer.qdrant_client
        self.settings = indexer.settings
        self.rerank_service = get_rerank_service()
    
    def search(
        self,
        query_text: str,
        query_image_data: Optional[str] = None,  # Base64 for image query
        top_k: int = get_settings().top_k,
        document_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None,
        search_text: bool = True,
        search_tables: bool = True,
        search_images: bool = True,
        alpha_text: float = 0.5,  # Weight for text results
        alpha_tables: float = 0.3,  # Weight for table results
        alpha_images: float = 0.2   # Weight for image results
    ) -> List[SearchResult]:
        """
        Unified search across all collections.
        
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
        
        # Calculate per-collection top_k
        active_searches = sum([search_text, search_tables, search_images])
        if active_searches == 0:
            return []
        
        per_collection_k = max(3, top_k // active_searches)
        
        # Build filters once
        filters = self._build_filters(document_ids, category_ids)
        
        # Search text chunks
        if search_text:
            text_results = self._search_text(
                query_text, per_collection_k, filters
            )
            # Apply weight
            for result in text_results:
                result.score *= alpha_text
            all_results.extend(text_results)
            logger.info(f"Text search: {len(text_results)} results")
        
        # Search tables
        if search_tables:
            table_results = self._search_tables(
                query_text, per_collection_k, filters
            )
            for result in table_results:
                result.score *= alpha_tables
            all_results.extend(table_results)
            logger.info(f"Table search: {len(table_results)} results")
        
        # Search images
        if search_images:
            image_results = self._search_images(
                query_text, query_image_data, per_collection_k, filters
            )
            for result in image_results:
                result.score *= alpha_images
            all_results.extend(image_results)
            logger.info(f"Image search: {len(image_results)} results")
        
        # Determine final result count
        final_top_k = self.settings.rerank_top_k
        
        # Sort by weighted score and return top results for reranking
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # In this new logic, top_k IS the initial search limit (candidates to consider)
        candidates = all_results[:top_k]
        
        # Apply Reranking if enabled
        if self.settings.use_reranker and candidates:
            logger.info(f"Reranking {len(candidates)} candidates...")
            self.rerank_service.initialize()
            
            # Prepare texts for reranker
            doc_texts = [res.content for res in candidates]
            
            # Get new scores
            rerank_scores = self.rerank_service.rerank(query_text, doc_texts)
            
            # Update scores
            for i, score in enumerate(rerank_scores):
                candidates[i].score = score
            
            # Sort again by new scores
            candidates.sort(key=lambda x: x.score, reverse=True)
            logger.info("Reranking completed")
        
        # Apply similarity threshold if configured
        threshold = self.settings.similarity_threshold
        if threshold > 0:
            initial_count = len(candidates)
            candidates = [res for res in candidates if res.score >= threshold]
            if len(candidates) < initial_count:
                logger.info(f"Filtered out {initial_count - len(candidates)} results below threshold {threshold}")
        
        # Finally, slice by rerank_top_k which is the expected FINAL result count
        final_results = candidates[:final_top_k]
        logger.info(f"Unified search returned {len(final_results)} results (from {len(all_results)} initial candidates)")
        
        return final_results
    
    def _build_filters(
        self,
        document_ids: Optional[List[str]],
        category_ids: Optional[List[str]]
    ):
        """Build Qdrant filters for document/category."""
        if not document_ids and not category_ids:
            return None
        
        from qdrant_client.models import Filter, FieldCondition, MatchAny
        
        conditions = []
        
        if document_ids:
            conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=document_ids)
                )
            )
        
        if category_ids:
            conditions.append(
                FieldCondition(
                    key="category_id",
                    match=MatchAny(any=category_ids)
                )
            )
        
        return Filter(must=conditions) if conditions else None
    
    def _search_text(
        self,
        query: str,
        top_k: int,
        filters
    ) -> List[SearchResult]:
        """Search text chunks collection."""
        try:
            # Generate query embeddings
            dense_embedding = self.embed_model.get_text_embedding(query)
            sparse_gen = list(self.sparse_embed_model.embed([query]))[0]
            sparse_vector = SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist()
            )
            
            # Hybrid Query with Fusion (RRF)
            from qdrant_client.models import Prefetch, FusionQuery
            
            results = self.qdrant_client.query_points(
                collection_name=self.settings.qdrant_collection,
                prefetch=[
                    Prefetch(
                        query=dense_embedding,
                        using="dense",
                        filter=filters,
                        limit=top_k
                    ),
                    Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        filter=filters,
                        limit=top_k
                    )
                ],
                query=FusionQuery(fusion="rrf"),
                limit=top_k
            )
            
            points = results.points if hasattr(results, "points") else results
            
            search_results = []
            for point in points:
                payload = point.payload
                
                # Parse image_ids and table_ids from payload
                image_ids = []
                table_ids = []
                
                if payload.get("image_ids"):
                    image_ids = payload["image_ids"].split(",") if isinstance(
                        payload["image_ids"], str
                    ) else payload["image_ids"]
                
                if payload.get("table_ids"):
                    table_ids = payload["table_ids"].split(",") if isinstance(
                        payload["table_ids"], str
                    ) else payload["table_ids"]
                
                search_results.append(SearchResult(
                    content=payload.get("text", ""),
                    score=point.score,
                    source_type="text",
                    document_id=payload.get("document_id", ""),
                    page_number=payload.get("page_start", 0),
                    section_title=payload.get("section_title", ""),
                    chunk_id=payload.get("chunk_id", ""),
                    related_image_ids=image_ids,
                    related_table_ids=table_ids
                ))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []
    
    def _search_tables(
        self,
        query: str,
        top_k: int,
        filters
    ) -> List[SearchResult]:
        """Search tables collection."""
        try:
            table_collection = f"{self.settings.qdrant_collection}_tables"
            
            # Generate query embeddings
            dense_embedding = self.embed_model.get_text_embedding(query)
            sparse_gen = list(self.sparse_embed_model.embed([query]))[0]
            sparse_vector = SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist()
            )
            
            from qdrant_client.models import Prefetch, FusionQuery
            
            results = self.qdrant_client.query_points(
                collection_name=table_collection,
                prefetch=[
                    Prefetch(
                        query=dense_embedding,
                        using="dense",
                        filter=filters,
                        limit=top_k
                    ),
                    Prefetch(
                        query=sparse_vector,
                        using="sparse",
                        filter=filters,
                        limit=top_k
                    )
                ],
                query=FusionQuery(fusion="rrf"),
                limit=top_k
            )
            
            points = results.points if hasattr(results, "points") else results
            
            search_results = []
            for point in points:
                payload = point.payload
                
                # Build table content representation
                content = f"[Table on page {payload.get('page_number', '?')}]\n"
                if payload.get("section_title"):
                    content += f"Section: {payload['section_title']}\n"
                if payload.get("markdown"):
                    content += payload["markdown"][:1000]  # Limit size
                
                search_results.append(SearchResult(
                    content=content,
                    score=point.score,
                    source_type="table",
                    document_id=payload.get("document_id", ""),
                    page_number=payload.get("page_number", 0),
                    section_title=payload.get("section_title", ""),
                    table_id=payload.get("table_id", "")
                ))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Table search failed: {e}")
            return []
    
    def _search_images(
        self,
        query_text: Optional[str],
        query_image_data: Optional[str],
        top_k: int,
        filters
    ) -> List[SearchResult]:
        """Search images collection."""
        try:
            image_collection = f"{self.settings.qdrant_collection}_images"
            
            # Get embedding from query
            embedding = None
            
            if query_image_data:
                # Use image embedder for image query
                from app.services.image_embedder import get_image_embedder
                embedder = get_image_embedder()
                embedder.initialize()
                
                # Combined image + text query if both present
                embedding = embedder.embed_image(
                    query_image_data,
                    text=query_text
                )
            elif query_text:
                # Text-to-image search
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
                query_filter=filters
            )
            
            points = results.points if hasattr(results, "points") else results
            
            search_results = []
            for point in points:
                payload = point.payload
                
                # Build image description
                content = f"[Image on page {payload.get('page_number', '?')}]"
                if payload.get("caption"):
                    content += f"\nCaption: {payload['caption']}"
                if payload.get("section_title"):
                    content += f"\nSection: {payload['section_title']}"
                
                search_results.append(SearchResult(
                    content=content,
                    score=point.score,
                    source_type="image",
                    document_id=payload.get("document_id", ""),
                    page_number=payload.get("page_number", 0),
                    section_title=payload.get("section_title", ""),
                    image_id=payload.get("image_id", ""),
                    image_path=payload.get("image_path", "")
                ))
            
            return search_results
            
        except Exception as e:
            logger.error(f"Image search failed: {e}")
            return []
