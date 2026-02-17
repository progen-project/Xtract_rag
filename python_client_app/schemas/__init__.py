"""
Client Schemas package.
Exports all DTOs for the PetroRAG Python Client Proxy.
"""
from .category import CategoryBase, CategoryCreate, CategoryUpdate, CategoryResponse
from .document import DocumentStatus, DocumentResponse, UploadResponse
from .batch import FileProcessStatus, BatchStatusResponse, TerminateBatchResponse
from .chat import InlineCitation, ChatMessage, ChatSession, ChatRequest, ChatResponse, ImageSearchResult as ChatImageSearchResult
from .query import (
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
    ImageSearchRequest,
    ImageSearchResult,
    ImageSearchResponse,
)

__all__ = [
    # Category
    "CategoryBase", "CategoryCreate", "CategoryUpdate", "CategoryResponse",
    # Document
    "DocumentStatus", "DocumentResponse", "UploadResponse",
    # Batch
    "FileProcessStatus", "BatchStatusResponse", "TerminateBatchResponse",
    # Chat
    "ChatMessage", "ChatSession", "ChatRequest", "ChatResponse", "ChatImageSearchResult",
    # Query
    "QueryRequest", "QueryResponse", "RetrievedChunk",
    "ImageSearchRequest", "ImageSearchResult", "ImageSearchResponse",
]
