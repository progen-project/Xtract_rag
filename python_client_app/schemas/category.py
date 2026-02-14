"""
Category Data Transfer Objects.
Strict schemas for Category operations (Create, Read, Update, Delete).
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class CategoryBase(BaseModel):
    """Base fields for Category."""
    name: str = Field(..., description="Name of the category")
    description: Optional[str] = Field(None, description="Optional description")


class CategoryCreate(CategoryBase):
    """Payload for creating a new category."""
    pass


class CategoryUpdate(BaseModel):
    """Payload for updating a category."""
    name: Optional[str] = Field(None, description="New name")
    description: Optional[str] = Field(None, description="New description")


class CategoryResponse(CategoryBase):
    """Response DTO for Category."""
    category_id: str = Field(..., description="Unique identifier")
    document_count: int = Field(0, description="Number of documents in category")
    created_at: datetime = Field(..., description="Creation timestamp")
