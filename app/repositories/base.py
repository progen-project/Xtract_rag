"""
Base repository with common MongoDB operations.
"""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import logging

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base class for all repositories with MongoDB connection."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client: Optional[AsyncIOMotorClient] = None
        self.db: Optional[AsyncIOMotorDatabase] = None
    
    async def connect(self) -> None:
        """Establish connection to MongoDB."""
        try:
            self.client = AsyncIOMotorClient(self.settings.mongodb_uri)
            self.db = self.client[self.settings.mongodb_database]
            await self.client.admin.command('ping')
            logger.info(f"Connected to MongoDB: {self.settings.mongodb_database}")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            logger.info("Disconnected from MongoDB")
    
    @property
    def is_connected(self) -> bool:
        """Check if connected to MongoDB."""
        return self.client is not None and self.db is not None
