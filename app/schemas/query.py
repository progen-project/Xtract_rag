"""
Query schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List

from .document import ExtractedImage, ExtractedTable


class QueryRequest(BaseModel):
    """Request for RAG query."""
    query: str
    category_ids: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)
    include_images: bool = True
    include_tables: bool = True


class RetrievedChunk(BaseModel):
    """A chunk retrieved from the index."""
    chunk_id: str
    content: str
    score: float
    section_title: str
    page_start: int
    page_end: int
    image_ids: List[str] = Field(default_factory=list)
    images: List[ExtractedImage] = Field(default_factory=list)
    tables: List[ExtractedTable] = Field(default_factory=list)


class QueryResponse(BaseModel):
    """Response from RAG query."""
    query: str
    answer: str
    retrieved_chunks: List[RetrievedChunk]
    sources: List[str]


class MultimodalQueryRequest(BaseModel):
    """Request for multimodal query (with image)."""
    query: str
    image_ids: Optional[List[str]] = None
    category_ids: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)


class ImageSearchRequest(BaseModel):
    """Request for image-based search."""
    query_text: Optional[str] = None
    query_image_base64: Optional[str] = None
    category_ids: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)


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
    results: List[ImageSearchResult]
    count: int
