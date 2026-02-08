"""
Schemas module for PetroRAG.
"""
from .common import DocumentStatus
from .category import Category, CategoryCreate, CategoryResponse
from .document import (
    TOCEntry,
    DocumentMetadata,
    DocumentUploadResponse,
    ExtractedImage,
    ExtractedTable,
    ParsedSection,
    ParsedDocument
)
from .chunk import ChunkMetadata, Chunk
from .query import (
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    MultimodalQueryRequest,
    ImageSearchRequest,
    ImageSearchResult,
    ImageSearchResponse
)
from .chat import (
    ChatMessage,
    ChatSession,
    ChatRequest,
    ChatResponse
)

__all__ = [
    # Common
    "DocumentStatus",
    # Category
    "Category",
    "CategoryCreate",
    "CategoryResponse",
    # Document
    "TOCEntry",
    "DocumentMetadata",
    "DocumentUploadResponse",
    "ExtractedImage",
    "ExtractedTable",
    "ParsedSection",
    "ParsedDocument",
    # Chunk
    "ChunkMetadata",
    "Chunk",
    # Query
    "QueryRequest",
    "QueryResponse",
    "RetrievedChunk",
    "MultimodalQueryRequest",
    "ImageSearchRequest",
    "ImageSearchResult",
    "ImageSearchResponse",
    # Chat
    "ChatMessage",
    "ChatSession",
    "ChatRequest",
    "ChatResponse",
]
