"""
Category schemas.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class Category(BaseModel):
    """Category for organizing documents."""
    category_id: str
    name: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    document_count: int = 0


class CategoryCreate(BaseModel):
    """Request to create a category."""
    name: str
    description: Optional[str] = None


class CategoryUpdate(BaseModel):
    """Request to update a category."""
    name: Optional[str] = None
    description: Optional[str] = None


class CategoryResponse(BaseModel):
    """Response for category operations."""
    category_id: str
    name: str
    description: Optional[str] = None
    document_count: int
    created_at: datetime
