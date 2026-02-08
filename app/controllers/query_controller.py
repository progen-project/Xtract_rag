"""
Query controller with business logic.
"""
from typing import List, Optional
import logging

from app.schemas import (
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    ImageSearchRequest,
    ImageSearchResult,
    ImageSearchResponse
)
from app.utils.exceptions import ValidationError

logger = logging.getLogger(__name__)


class QueryController:
    """Controller for query operations."""
    
    def __init__(self, indexer, llm_service, document_repo):
        self.indexer = indexer
        self.llm = llm_service
        self.document_repo = document_repo
    
    async def query(self, request: QueryRequest) -> QueryResponse:
        """Perform a RAG query."""
        # Initialize services
        self.indexer.initialize()
        self.llm.initialize()
        
        # Retrieve relevant chunks
        retrieved_chunks = self.indexer.query(
            query_text=request.query,
            top_k=request.top_k,
            document_ids=request.document_ids,
            category_ids=request.category_ids
        )
        
        if not retrieved_chunks:
            return QueryResponse(
                query=request.query,
                answer="No relevant information found in the indexed documents.",
                retrieved_chunks=[],
                sources=[]
            )
        
        # Enrich with images and tables
        for chunk in retrieved_chunks:
            if request.include_images:
                images = await self.document_repo.get_images_by_document(
                    chunk.chunk_id.split("_chunk_")[0]
                )
                chunk.images = [img for img in images if img.image_id in (chunk.image_ids or [])]
            
            if request.include_tables:
                tables = await self.document_repo.get_tables_by_document(
                    chunk.chunk_id.split("_chunk_")[0]
                )
                chunk.tables = [tbl for tbl in tables if tbl.table_id in (chunk.table_ids or [])]
        
        # Generate response
        try:
            answer = await self.llm.generate_response(
                query=request.query,
                context_chunks=retrieved_chunks
            )
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            answer = "Unable to generate response. Please review the retrieved chunks below."
        
        # Collect sources
        sources = list(set(
            chunk.chunk_id.split("_chunk_")[0]
            for chunk in retrieved_chunks
        ))
        
        return QueryResponse(
            query=request.query,
            answer=answer,
            retrieved_chunks=retrieved_chunks,
            sources=sources
        )
    
    async def search_images(self, request: ImageSearchRequest) -> ImageSearchResponse:
        """Search for images using text or image query."""
        if not request.query_text and not request.query_image_base64:
            raise ValidationError(
                "At least one of 'query_text' or 'query_image_base64' must be provided"
            )
        
        self.indexer.initialize()
        
        results = []
        if request.query_image_base64:
            results = self.indexer.search_images_by_image(
                image_data=request.query_image_base64,
                text=request.query_text,
                top_k=request.top_k,
                document_ids=request.document_ids,
                category_ids=request.category_ids
            )
        elif request.query_text:
            results = self.indexer.search_images_by_text(
                query_text=request.query_text,
                top_k=request.top_k,
                document_ids=request.document_ids,
                category_ids=request.category_ids
            )
        
        image_results = [
            ImageSearchResult(
                image_id=r.get("image_id", ""),
                document_id=r.get("document_id", ""),
                page_number=r.get("page_number", 0),
                section_title=r.get("section_title"),
                caption=r.get("caption"),
                image_path=r.get("image_path", ""),
                score=r.get("score", 0.0)
            )
            for r in results
        ]
        
        return ImageSearchResponse(
            query_text=request.query_text,
            has_query_image=request.query_image_base64 is not None,
            results=image_results,
            count=len(image_results)
        )
