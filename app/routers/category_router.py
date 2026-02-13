"""
Category API router.

Thin router that delegates to CategoryController.
"""
from fastapi import APIRouter, Depends
from typing import List

from app.core.dependencies import get_category_controller
from app.controllers import CategoryController
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse

router = APIRouter(prefix="/api/categories", tags=["Categories"])


@router.post("", response_model=CategoryResponse)
async def create_category(
    request: CategoryCreate,
    controller: CategoryController = Depends(get_category_controller)
):
    """Create a new category."""
    return await controller.create_category(request)


@router.get("", response_model=List[CategoryResponse])
async def list_categories(
    controller: CategoryController = Depends(get_category_controller)
):
    """List all categories."""
    return await controller.list_categories()


@router.get("/{category_id}", response_model=CategoryResponse)
async def get_category(
    category_id: str,
    controller: CategoryController = Depends(get_category_controller)
):
    """Get a specific category."""
    return await controller.get_category(category_id)


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: str,
    request: CategoryUpdate,
    controller: CategoryController = Depends(get_category_controller)
):
    """Update a category (Rename/Description)."""
    return await controller.update_category(
        category_id, 
        name=request.name, 
        description=request.description
    )


@router.delete("/{category_id}")
async def delete_category(
    category_id: str,
    controller: CategoryController = Depends(get_category_controller)
):
    """Delete a category."""
    await controller.delete_category(category_id)
    return {"message": f"Category {category_id} deleted"}
