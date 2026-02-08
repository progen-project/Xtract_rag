"""
Category controller with business logic.
"""
from typing import List, Optional
import logging

from app.repositories import CategoryRepository
from app.schemas import Category, CategoryCreate, CategoryResponse
from app.utils.exceptions import CategoryNotFoundError

logger = logging.getLogger(__name__)


class CategoryController:
    """Controller for category operations."""
    
    def __init__(self, category_repo: CategoryRepository):
        self.category_repo = category_repo
    
    async def create_category(self, request: CategoryCreate) -> CategoryResponse:
        """Create a new category."""
        category = await self.category_repo.create(
            name=request.name,
            description=request.description
        )
        return CategoryResponse(
            category_id=category.category_id,
            name=category.name,
            description=category.description,
            document_count=category.document_count,
            created_at=category.created_at
        )
    
    async def get_category(self, category_id: str) -> CategoryResponse:
        """Get a category by ID."""
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise CategoryNotFoundError(category_id)
        
        return CategoryResponse(
            category_id=category.category_id,
            name=category.name,
            description=category.description,
            document_count=category.document_count,
            created_at=category.created_at
        )
    
    async def list_categories(self) -> List[CategoryResponse]:
        """Get all categories."""
        categories = await self.category_repo.get_all()
        return [
            CategoryResponse(
                category_id=cat.category_id,
                name=cat.name,
                description=cat.description,
                document_count=cat.document_count,
                created_at=cat.created_at
            )
            for cat in categories
        ]
    
    async def update_category(
        self,
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> CategoryResponse:
        """Update a category."""
        category = await self.category_repo.update(category_id, name, description)
        if not category:
            raise CategoryNotFoundError(category_id)
        
        return CategoryResponse(
            category_id=category.category_id,
            name=category.name,
            description=category.description,
            document_count=category.document_count,
            created_at=category.created_at
        )
    
    async def delete_category(self, category_id: str) -> bool:
        """Delete a category."""
        # Check if category exists
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise CategoryNotFoundError(category_id)
        
        return await self.category_repo.delete(category_id)
