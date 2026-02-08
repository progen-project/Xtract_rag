"""
Document repository for database operations.
"""
from typing import Optional, List
import logging
from datetime import datetime

from app.schemas import DocumentMetadata, DocumentStatus, ExtractedImage, ExtractedTable

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for document CRUD operations."""
    
    def __init__(self, db):
        self.db = db
        self.settings = None
    
    def set_settings(self, settings):
        self.settings = settings
    
    @property
    def documents_collection(self):
        return self.db[self.settings.documents_collection]
    
    @property
    def images_collection(self):
        return self.db[self.settings.images_collection]
    
    @property
    def tables_collection(self):
        return self.db[self.settings.tables_collection]
    
    async def create(self, document: DocumentMetadata) -> DocumentMetadata:
        """Create a new document record."""
        await self.documents_collection.insert_one({
            "_id": document.document_id,
            **document.model_dump(exclude={"document_id"})
        })
        logger.info(f"Created document: {document.document_id}")
        return document
    
    async def get_by_id(self, document_id: str) -> Optional[DocumentMetadata]:
        """Get a document by ID."""
        doc = await self.documents_collection.find_one({"_id": document_id})
        if doc:
            doc["document_id"] = doc.pop("_id")
            return DocumentMetadata(**doc)
        return None
    
    async def get_by_category(self, category_id: str) -> List[DocumentMetadata]:
        """Get all documents in a category."""
        cursor = self.documents_collection.find({"category_id": category_id})
        documents = []
        async for doc in cursor:
            doc["document_id"] = doc.pop("_id")
            documents.append(DocumentMetadata(**doc))
        return documents
    
    async def get_all(self) -> List[DocumentMetadata]:
        """Get all documents."""
        cursor = self.documents_collection.find()
        documents = []
        async for doc in cursor:
            doc["document_id"] = doc.pop("_id")
            documents.append(DocumentMetadata(**doc))
        return documents
    
    async def update_status(
        self,
        document_id: str,
        status: DocumentStatus,
        error: Optional[str] = None
    ) -> bool:
        """Update document processing status."""
        update_data = {"status": status.value}
        if error:
            update_data["$push"] = {"processing_errors": error}
        
        result = await self.documents_collection.update_one(
            {"_id": document_id},
            {"$set": {"status": status.value}}
        )
        
        if error:
            await self.documents_collection.update_one(
                {"_id": document_id},
                {"$push": {"processing_errors": error}}
            )
        
        return result.modified_count > 0
    
    async def delete(self, document_id: str) -> bool:
        """Delete a document and all related data."""
        # Delete images
        await self.images_collection.delete_many({"document_id": document_id})
        # Delete tables
        await self.tables_collection.delete_many({"document_id": document_id})
        # Delete document
        result = await self.documents_collection.delete_one({"_id": document_id})
        
        if result.deleted_count > 0:
            logger.info(f"Deleted document: {document_id}")
            return True
        return False
    
    # Image operations
    async def store_images(self, images: List[ExtractedImage]) -> None:
        """Store extracted images."""
        if not images:
            return
        
        docs = []
        for img in images:
            doc = img.model_dump()
            doc["_id"] = doc.pop("image_id")
            doc.pop("base64_data", None)  # Don't store base64 in DB
            docs.append(doc)
        
        await self.images_collection.insert_many(docs)
        logger.info(f"Stored {len(images)} images")
    
    async def get_images_by_document(self, document_id: str) -> List[ExtractedImage]:
        """Get all images for a document."""
        cursor = self.images_collection.find({"document_id": document_id})
        images = []
        async for doc in cursor:
            doc["image_id"] = doc.pop("_id")
            images.append(ExtractedImage(**doc))
        return images
    
    async def get_image_by_id(self, image_id: str) -> Optional[ExtractedImage]:
        """Get an image by ID."""
        doc = await self.images_collection.find_one({"_id": image_id})
        if doc:
            doc["image_id"] = doc.pop("_id")
            return ExtractedImage(**doc)
        return None
    
    # Table operations
    async def store_tables(self, tables: List[ExtractedTable]) -> None:
        """Store extracted tables."""
        if not tables:
            return
        
        docs = []
        for tbl in tables:
            doc = tbl.model_dump()
            doc["_id"] = doc.pop("table_id")
            docs.append(doc)
        
        await self.tables_collection.insert_many(docs)
        logger.info(f"Stored {len(tables)} tables")
    
    async def get_tables_by_document(self, document_id: str) -> List[ExtractedTable]:
        """Get all tables for a document."""
        cursor = self.tables_collection.find({"document_id": document_id})
        tables = []
        async for doc in cursor:
            doc["table_id"] = doc.pop("_id")
            tables.append(ExtractedTable(**doc))
        return tables
