"""
Query & Image Search Data Transfer Objects.
Strict schemas for Query and Image Search operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, List


class QueryRequest(BaseModel):
    """Payload for a RAG query."""
    query: str = Field(..., description="The search/query text")
    category_ids: Optional[List[str]] = Field(None, description="Filter by category IDs")
    document_ids: Optional[List[str]] = Field(None, description="Filter by document IDs")
    include_images: bool = Field(True, description="Include related images in results")
    include_tables: bool = Field(True, description="Include related tables in results")


class RetrievedChunk(BaseModel):
    """A single chunk retrieved from the vector index."""
    chunk_id: str
    content: str
    score: float
    section_title: str
    page_start: int
    page_end: int
    image_ids: List[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """Response from a RAG query."""
    query: str
    answer: str
    retrieved_chunks: List[RetrievedChunk] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)
    inline_citations: List[dict] = Field(default_factory=list, description="Structured inline citations")


class ImageSearchRequest(BaseModel):
    """Payload for image-based search."""
    query_text: Optional[str] = Field(None, description="Text to search images by")
    query_image_base64: Optional[str] = Field(None, description="Base64-encoded image to search by")
    category_ids: Optional[List[str]] = Field(None, description="Filter by categories")
    document_ids: Optional[List[str]] = Field(None, description="Filter by documents")


class ImageSearchResult(BaseModel):
    """A single image search result."""
    image_id: str
    document_id: str
    page_number: int
    section_title: Optional[str] = None
    caption: Optional[str] = None
    image_path: str
    score: float


class ImageSearchResponse(BaseModel):
    """Response from image search."""
    query_text: Optional[str] = None
    has_query_image: bool = False
    results: List[ImageSearchResult] = Field(default_factory=list)
    count: int = 0
