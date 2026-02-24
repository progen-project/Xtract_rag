"""
Chat repository for database operations.
"""
from typing import Optional, List
import logging
from datetime import datetime

from app.schemas import ChatMessage, ChatSession

logger = logging.getLogger(__name__)


class ChatRepository:
    """Repository for chat CRUD operations."""
    
    def __init__(self, db):
        self.db = db
        self.settings = None
    
    def set_settings(self, settings):
        self.settings = settings
    
    @property
    def collection(self):
        return self.db[self.settings.chats_collection]
    
    async def create(
        self,
        chat_id: str,
        username: str,
        title: Optional[str] = None,
        category_ids: Optional[List[str]] = None,
        document_ids: Optional[List[str]] = None
    ) -> ChatSession:
        """Create a new chat session."""
        now = datetime.utcnow()
        chat = ChatSession(
            chat_id=chat_id,
            username=username,
            title=title,
            category_ids=category_ids,
            document_ids=document_ids,
            messages=[],
            created_at=now,
            updated_at=now
        )
        
        await self.collection.insert_one({
            "_id": chat_id,
            **chat.model_dump(exclude={"chat_id"})
        })
        
        logger.info(f"Created chat session: {chat_id}")
        return chat
    
    async def get_by_id(self, chat_id: str, username: Optional[str] = None) -> Optional[ChatSession]:
        """Get a chat session by ID, optionally filtered by username."""
        query = {"_id": chat_id}
        if username:
            query["username"] = username
            
        doc = await self.collection.find_one(query)
        if doc:
            doc["chat_id"] = doc.pop("_id")
            return ChatSession(**doc)
        return None
    
    async def add_message(self, chat_id: str, message: ChatMessage) -> bool:
        """Add a message to a chat session (autosave)."""
        result = await self.collection.update_one(
            {"_id": chat_id},
            {
                "$push": {"messages": message.model_dump()},
                "$set": {"updated_at": datetime.utcnow()}
            }
        )
        return result.modified_count > 0
    
    async def get_recent_messages(
        self,
        chat_id: str,
        limit: int = 10
    ) -> List[ChatMessage]:
        """Get the most recent messages from a chat (for context window)."""
        chat = await self.get_by_id(chat_id)
        if not chat:
            return []
        return chat.messages[-limit:]
    
    async def get_all_by_user(self, username: str, limit: int = 50) -> List[ChatSession]:
        """List all chat sessions for a specific user (most recent first)."""
        cursor = self.collection.find({"username": username}).sort("updated_at", -1).limit(limit)
        chats = []
        async for doc in cursor:
            doc["chat_id"] = doc.pop("_id")
            chats.append(ChatSession(**doc))
        return chats
    
    async def delete(self, chat_id: str, username: str) -> bool:
        """Delete a chat session."""
        result = await self.collection.delete_one({"_id": chat_id, "username": username})
        if result.deleted_count > 0:
            logger.info(f"Deleted chat: {chat_id} for user: {username}")
            return True
        return False
        
    async def update_title(self, chat_id: str, username: str, title: str) -> bool:
        """Update the title of a chat session."""
        result = await self.collection.update_one(
            {"_id": chat_id, "username": username},
            {"$set": {"title": title, "updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0
