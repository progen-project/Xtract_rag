"""
Category API router.

Thin router that delegates to CategoryController.
"""
from fastapi import APIRouter, Depends
from typing import List

from app.core.dependencies import get_category_controller, get_document_controller
from app.controllers import CategoryController, DocumentController
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse, DocumentMetadata

router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.post("", response_model=CategoryResponse)
async def create_category(
    request: CategoryCreate,
    controller: CategoryController = Depends(get_category_controller)
):
    """Create a new category."""
    category = await controller.create_category(request)
    return category


@router.get("", response_model=List[CategoryResponse])
async def list_categories(
    controller: CategoryController = Depends(get_category_controller)
):
    """List all categories."""
    """List all categories."""
    """List all categories."""
    return await controller.list_categories()


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    controller: CategoryController = Depends(get_category_controller)
):
    """Get a specific category."""
    """Get a specific category."""
    return await controller.get_category(category_id)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    request: CategoryUpdate,
    controller: CategoryController = Depends(get_category_controller)
):
    """Update a category (Rename/Description)."""
    category = await controller.update_category(
        category_id, 
        name=request.name, 
        description=request.description
    )
    return category


@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    controller: CategoryController = Depends(get_category_controller)
):
    """Delete a category."""
    """Delete a category."""
    await controller.delete_category(category_id)
    return {"message": f"Category {category_id} deleted"}


@router.get("/{category_id}/documents", response_model=List[DocumentMetadata])
async def list_category_documents(
    category_id: str,
    doc_controller: DocumentController = Depends(get_document_controller)
):
    """List all documents in a specific category."""
    """List all documents in a specific category."""
    return await doc_controller.list_documents(category_id)
