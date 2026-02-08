"""
Routers module for PetroRAG.
"""
from . import category_router
from . import document_router
from . import query_router
from . import chat_router

__all__ = [
    "category_router",
    "document_router",
    "query_router",
    "chat_router",
]
