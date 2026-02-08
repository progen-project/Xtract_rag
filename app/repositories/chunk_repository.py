"""
Chunk repository for database operations.
"""
from typing import Optional, List
import logging

from app.schemas import Chunk

logger = logging.getLogger(__name__)


class ChunkRepository:
    """Repository for chunk CRUD operations."""
    
    def __init__(self, db):
        self.db = db
        self.settings = None
    
    def set_settings(self, settings):
        self.settings = settings
    
    @property
    def collection(self):
        return self.db[self.settings.chunks_collection]
    
    async def store_chunks(self, chunks: List[Chunk]) -> None:
        """Store chunks in MongoDB."""
        if not chunks:
            return
        
        docs = []
        for chunk in chunks:
            doc = chunk.model_dump()
            doc["_id"] = doc.pop("chunk_id")
            doc.pop("embedding", None)  # Don't store embeddings in MongoDB
            docs.append(doc)
        
        await self.collection.insert_many(docs)
        logger.info(f"Stored {len(chunks)} chunks")
    
    async def get_by_id(self, chunk_id: str) -> Optional[Chunk]:
        """Get a chunk by ID."""
        doc = await self.collection.find_one({"_id": chunk_id})
        if doc:
            doc["chunk_id"] = doc.pop("_id")
            return Chunk(**doc)
        return None
    
    async def get_by_document(self, document_id: str) -> List[Chunk]:
        """Get all chunks for a document."""
        cursor = self.collection.find({"document_id": document_id})
        chunks = []
        async for doc in cursor:
            doc["chunk_id"] = doc.pop("_id")
            chunks.append(Chunk(**doc))
        return chunks
    
    async def delete_by_document(self, document_id: str) -> int:
        """Delete all chunks for a document."""
        result = await self.collection.delete_many({"document_id": document_id})
        logger.info(f"Deleted {result.deleted_count} chunks for document {document_id}")
        return result.deleted_count
    
    async def get_images_by_chunk(self, chunk_id: str) -> List[str]:
        """Get image IDs for a chunk."""
        chunk = await self.get_by_id(chunk_id)
        return chunk.image_ids if chunk else []
    
    async def get_tables_by_chunk(self, chunk_id: str) -> List[str]:
        """Get table IDs for a chunk."""
        chunk = await self.get_by_id(chunk_id)
        return chunk.table_ids if chunk else []
