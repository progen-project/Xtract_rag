"""
Core module for PetroRAG application setup.
"""
from .app import create_app
from .dependencies import get_category_controller, get_document_controller, get_query_controller, get_chat_controller

__all__ = [
    "create_app",
    "get_category_controller",
    "get_document_controller", 
    "get_query_controller",
    "get_chat_controller",
]
