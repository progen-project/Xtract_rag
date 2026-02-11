"""
Document schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from .common import DocumentStatus


class TOCEntry(BaseModel):
    """Table of Contents entry."""
    title: str
    level: int
    page_number: int
    page_end: Optional[int] = None


class DocumentMetadata(BaseModel):
    """Metadata for uploaded documents."""
    document_id: str
    category_id: str
    filename: str
    file_path: str
    file_size: int
    page_count: int
    upload_date: datetime = Field(default_factory=datetime.utcnow)
    status: DocumentStatus = DocumentStatus.PENDING
    batch_id: Optional[str] = None
    is_daily: bool = Field(default=False, description="If True, document is deleted after 24 hours")
    toc: List[TOCEntry] = Field(default_factory=list)
    processing_errors: List[str] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""
    document_id: str
    category_id: str
    filename: str
    message: str
    status: DocumentStatus
    batch_id: Optional[str] = None


class ExtractedImage(BaseModel):
    """Extracted image from PDF (metadata only, content on disk)."""
    image_id: str
    document_id: str
    category_id: str = ""
    page_number: int
    image_path: str
    image_format: str
    width: int
    height: int
    caption: Optional[str] = None
    section_title: Optional[str] = None
    chunk_ids: List[str] = Field(default_factory=list)
    analysis: Optional[str] = None


class ExtractedTable(BaseModel):
    """Extracted table from PDF."""
    table_id: str
    document_id: str
    category_id: str = ""
    page_number: int
    section_title: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    chunk_ids: List[str] = Field(default_factory=list)
    markdown_content: Optional[str] = None


class ParsedSection(BaseModel):
    """A section of a parsed document."""
    title: str
    level: int
    content: str
    page_start: int
    page_end: int
    tables: List[ExtractedTable] = Field(default_factory=list)
    images: List[ExtractedImage] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    """A fully parsed document."""
    document_id: str
    filename: str
    page_count: int
    toc: List[TOCEntry]
    sections: List[ParsedSection]
    all_images: List[ExtractedImage]
    all_tables: List[ExtractedTable]
