"""
Chunk schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChunkMetadata(BaseModel):
    """Metadata for a text chunk."""
    document_id: str
    category_id: str
    section_title: str
    page_start: int
    page_end: int
    chunk_index: int
    has_tables: bool = False
    has_images: bool = False


class Chunk(BaseModel):
    """A text chunk with metadata and associations."""
    chunk_id: str
    document_id: str
    category_id: str = ""
    section_title: str
    content: str
    page_start: int
    page_end: int
    chunk_index: int
    image_ids: List[str] = Field(default_factory=list)
    table_ids: List[str] = Field(default_factory=list)
    overlap_start: Optional[str] = None
    overlap_end: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
