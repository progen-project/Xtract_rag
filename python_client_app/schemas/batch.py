"""
Batch Data Transfer Objects.
Strict schemas for Batch operations (Status, Progress).
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from datetime import datetime


class FileProcessStatus(BaseModel):
    """Granular status of a single file in a batch."""
    status: str = Field(..., description="Current step (e.g., parsing, chunking)")
    detail: Optional[str] = Field(None, description="Detailed progress message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class BatchStatusResponse(BaseModel):
    """Snapshot response for a Batch."""
    batch_id: str = Field(..., description="Batch Unique ID")
    files: Dict[str, FileProcessStatus] = Field(..., description="Map of filename to status")
    timestamp: datetime = Field(..., description="Snapshot timestamp")


class TerminateBatchResponse(BaseModel):
    """Response for batch termination."""
    batch_id: str
    total_documents: int
    kept_completed: int
    deleted_incomplete: int
