"""
Document Data Transfer Objects.
Strict schemas for Document operations (Upload, Read, Status).
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime


class DocumentStatus(str, Enum):
    """High-level document status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentResponse(BaseModel):
    """Response DTO for Document Metadata."""
    document_id: str = Field(..., description="Unique document ID")
    category_id: str = Field(..., description="Parent category ID")
    filename: str = Field(..., description="Original filename")
    status: DocumentStatus = Field(..., description="Current processing status")
    upload_date: datetime = Field(..., description="Upload timestamp")
    batch_id: Optional[str] = Field(None, description="Batch ID if part of a batch")
    is_daily: bool = Field(False, description="True if document is temporary (24h)")
    error_message: Optional[str] = Field(None, description="Error details if failed")


class UploadResponse(BaseModel):
    """Response DTO for File Upload."""
    document_id: str
    category_id: str
    filename: str
    status: str
    batch_id: str
    message: str
