"""
Chat schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from .query import ImageSearchResult


class InlineCitation(BaseModel):
    """A structured inline citation linking a part of the answer to a specific source."""
    source_number: int = Field(..., description="Source index (1-based) in the context chunks")
    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    section_title: str = Field("", description="Section title")
    pages: List[int] = Field(default_factory=list, description="Page numbers referenced")


class ChatMessage(BaseModel):
    """A single message in a chat session."""
    message_id: str
    role: str  # "user" or "assistant"
    content: str
    image_paths: List[str] = Field(default_factory=list)
    sources: Optional[dict] = Field(default=None, description="Sources map: document_id -> list of page numbers")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(BaseModel):
    """A chat session with message history."""
    chat_id: str
    category_ids: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    messages: List[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


from app.config.settings import get_settings

class ChatRequest(BaseModel):
    """Request for chat endpoint (used with form-data)."""
    chat_id: Optional[str] = None
    message: str
    category_ids: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    top_k: int = Field(default_factory=lambda: get_settings().top_k, ge=1, le=100)


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    chat_id: str
    message_id: str
    answer: str
    sources: dict = Field(default_factory=dict, description="Sources map: document_id -> {filename, pages, ...}")
    inline_citations: List[InlineCitation] = Field(default_factory=list, description="Structured inline citations linking answer parts to specific sources")
    image_results: List[ImageSearchResult] = Field(default_factory=list)
