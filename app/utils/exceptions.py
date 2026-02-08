"""
Custom exceptions for PetroRAG application.
"""


class PetroRAGException(Exception):
    """Base exception for PetroRAG."""
    pass


class DocumentNotFoundError(PetroRAGException):
    """Raised when a document is not found."""
    def __init__(self, document_id: str):
        self.document_id = document_id
        super().__init__(f"Document not found: {document_id}")


class CategoryNotFoundError(PetroRAGException):
    """Raised when a category is not found."""
    def __init__(self, category_id: str):
        self.category_id = category_id
        super().__init__(f"Category not found: {category_id}")


class ChatNotFoundError(PetroRAGException):
    """Raised when a chat is not found."""
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        super().__init__(f"Chat not found: {chat_id}")


class ValidationError(PetroRAGException):
    """Raised for validation errors."""
    pass


class ProcessingError(PetroRAGException):
    """Raised when document processing fails."""
    pass
