"""
Chat Data Transfer Objects.
Strict schemas for Chat operations (Session, Message).
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class InlineCitation(BaseModel):
    """A structured inline citation linking answer parts to specific sources."""
    source_number: int = Field(..., description="Source index (1-based)")
    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Document filename")
    section_title: str = Field("", description="Section title")
    pages: List[int] = Field(default_factory=list, description="Page numbers")


class ChatMessage(BaseModel):
    """A single message in a chat history."""
    role: str = Field(..., description="Role: 'user' or 'ai'")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sources: Optional[dict] = Field(default=None, description="Sources map")
    image_paths: List[str] = Field(default_factory=list, description="List of image paths")


class ChatSession(BaseModel):
    """Chat Session Metadata."""
    chat_id: str = Field(..., description="Unique chat session ID")
    title: Optional[str] = Field(None, description="Chat title/summary")
    category_ids: Optional[List[str]] = Field(None, description="Linked category IDs")
    document_ids: Optional[List[str]] = Field(None, description="Linked document IDs")
    created_at: datetime = Field(..., description="Creation timestamp")
    messages: List[ChatMessage] = Field(default=[], description="Chat history")


class ChatRequest(BaseModel):
    """Payload for sending a message."""
    message: str = Field(..., description="User message")
    chat_id: Optional[str] = Field(None, description="Existing chat ID")
    category_ids: Optional[List[str]] = Field(None, description="Filter by categories")
    document_ids: Optional[List[str]] = Field(None, description="Filter by documents")
    top_k: int = Field(5, description="Number of context chunks to retrieve")


class ImageSearchResult(BaseModel):
    """A single image search result."""
    image_id: str
    document_id: str
    page_number: int
    section_title: Optional[str] = None
    caption: Optional[str] = None
    image_path: str
    score: float


class ChatResponse(BaseModel):
    """Response from AI."""
    chat_id: str
    message_id: str
    answer: str
    sources: dict = Field(default_factory=dict, description="Sources map: document_id -> {filename, pages, ...}")
    inline_citations: List[InlineCitation] = Field(default_factory=list, description="Structured inline citations")
    image_results: List[ImageSearchResult] = Field(default_factory=list)
