"""
Category repository for database operations.
"""
from typing import Optional, List
import logging
import uuid
from datetime import datetime

from app.schemas import Category

logger = logging.getLogger(__name__)


class CategoryRepository:
    """Repository for category CRUD operations."""
    
    def __init__(self, db):
        self.db = db
        self.settings = None
    
    def set_settings(self, settings):
        self.settings = settings
    
    @property
    def collection(self):
        return self.db[self.settings.categories_collection]
    
    async def create(self, name: str, description: Optional[str] = None) -> Category:
        """Create a new category."""
        category_id = f"cat_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        
        category = Category(
            category_id=category_id,
            name=name,
            description=description,
            created_at=now,
            document_count=0
        )
        
        await self.collection.insert_one({
            "_id": category_id,
            **category.model_dump(exclude={"category_id"})
        })
        
        logger.info(f"Created category: {category_id} - {name}")
        return category
    
    async def get_by_id(self, category_id: str) -> Optional[Category]:
        """Get a category by ID."""
        doc = await self.collection.find_one({"_id": category_id})
        if doc:
            doc["category_id"] = doc.pop("_id")
            return Category(**doc)
        return None
    
    async def get_all(self) -> List[Category]:
        """Get all categories."""
        cursor = self.collection.find()
        categories = []
        async for doc in cursor:
            doc["category_id"] = doc.pop("_id")
            categories.append(Category(**doc))
        return categories
    
    async def update(
        self,
        category_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Category]:
        """Update a category."""
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        
        if not update_data:
            return await self.get_by_id(category_id)
        
        result = await self.collection.update_one(
            {"_id": category_id},
            {"$set": update_data}
        )
        
        if result.modified_count > 0:
            logger.info(f"Updated category: {category_id}")
        
        return await self.get_by_id(category_id)
    
    async def delete(self, category_id: str) -> bool:
        """Delete a category."""
        result = await self.collection.delete_one({"_id": category_id})
        if result.deleted_count > 0:
            logger.info(f"Deleted category: {category_id}")
            return True
        return False
    
    async def increment_document_count(self, category_id: str, delta: int = 1) -> None:
        """Increment or decrement document count."""
        await self.collection.update_one(
            {"_id": category_id},
            {"$inc": {"document_count": delta}}
        )
