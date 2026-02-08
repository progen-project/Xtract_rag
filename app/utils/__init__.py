"""
Utilities module for PetroRAG.
"""
from .file_utils import save_uploaded_file, generate_unique_filename
from .exceptions import (
    PetroRAGException,
    DocumentNotFoundError,
    CategoryNotFoundError,
    ChatNotFoundError,
    ValidationError,
    ProcessingError
)

__all__ = [
    "save_uploaded_file",
    "generate_unique_filename",
    "PetroRAGException",
    "DocumentNotFoundError",
    "CategoryNotFoundError", 
    "ChatNotFoundError",
    "ValidationError",
    "ProcessingError"
]
