"""
FIXED Dependency injection - adds document_repo to ChatController.
"""
from typing import Optional
import logging

from app.config.settings import get_settings
from app.repositories import (
    BaseRepository,
    CategoryRepository,
    DocumentRepository,
    ChunkRepository,
    ChatRepository
)
from app.controllers import (
    CategoryController,
    DocumentController,
    QueryController,
    ChatController
)
from app.services.indexer import indexer as indexer_service
from app.services.llm_service import llm_service
from app.services.pdf_parser import DoclingParser
from app.services.chunker import SectionChunker
from app.services.image_embedder import image_embedder
from app.services.rerank_service import rerank_service


from app.services.status import ProcessingStatusManager  # Added


logger = logging.getLogger(__name__)


class Container:
    """Dependency injection container with document_repo for ChatController."""
    
    def __init__(self):
        self.settings = get_settings()
        self.base_repo = BaseRepository()
        
        # Repositories
        self.category_repo: Optional[CategoryRepository] = None
        self.document_repo: Optional[DocumentRepository] = None
        self.chunk_repo: Optional[ChunkRepository] = None
        self.chat_repo: Optional[ChatRepository] = None
        
        # Controllers
        self.category_controller: Optional[CategoryController] = None
        self.document_controller: Optional[DocumentController] = None
        self.query_controller: Optional[QueryController] = None
        self.chat_controller: Optional[ChatController] = None
        
        # Services
        self.indexer = indexer_service
        self.llm = llm_service
        self.pdf_parser = DoclingParser()
        self.chunker = SectionChunker()
        self.image_embedder = image_embedder
        self.rerank_service = rerank_service
        self.status_manager = ProcessingStatusManager()  # Added status manager
    
    async def initialize(self) -> None:
        """Initialize all components (called at startup)."""
        logger.info("Initializing dependency container...")
        self.settings.ensure_directories()
        
        # Connect to database
        await self.base_repo.connect()
        
        # Initialize repositories
        self.category_repo = CategoryRepository(self.base_repo.db)
        self.category_repo.set_settings(self.settings)
        
        self.document_repo = DocumentRepository(self.base_repo.db)
        self.document_repo.set_settings(self.settings)
        
        self.chunk_repo = ChunkRepository(self.base_repo.db)
        self.chunk_repo.set_settings(self.settings)
        
        self.chat_repo = ChatRepository(self.base_repo.db)
        self.chat_repo.set_settings(self.settings)
        
        # Initialize services
        self.indexer.initialize()
        self.llm.initialize()
        self.rerank_service.initialize()
        
        # Initialize controllers
        self.category_controller = CategoryController(self.category_repo)
        
        self.document_controller = DocumentController(
            document_repo=self.document_repo,
            category_repo=self.category_repo,
            chunk_repo=self.chunk_repo,
            indexer=self.indexer,
            pdf_parser=self.pdf_parser,
            chunker=self.chunker,
            image_embedder=self.image_embedder,
            settings=self.settings,
            llm_service=self.llm,  # Added LLM service
            status_manager=self.status_manager  # Added status manager
        )
        
        self.query_controller = QueryController(
            indexer=self.indexer,
            llm_service=self.llm,
            document_repo=self.document_repo
        )
        
        # FIXED: ChatController now gets document_repo to fetch images by ID
        self.chat_controller = ChatController(
            chat_repo=self.chat_repo,
            indexer=self.indexer,
            llm_service=self.llm,
            settings=self.settings,
            document_repo=self.document_repo  # ADDED
        )
        
        logger.info("Dependency container initialized")
    
    async def shutdown(self) -> None:
        """Cleanup on shutdown."""
        logger.info("Shutting down dependency container...")
        await self.base_repo.disconnect()
        logger.info("Dependency container shutdown complete")


# Global container instance
container = Container()


# Dependency functions for FastAPI
def get_container() -> Container:
    """Get the DI container."""
    return container


def get_category_controller() -> CategoryController:
    """Dependency for category controller."""
    return container.category_controller


def get_document_controller() -> DocumentController:
    """Dependency for document controller."""
    return container.document_controller


def get_query_controller() -> QueryController:
    """Dependency for query controller."""
    return container.query_controller


def get_chat_controller() -> ChatController:
    """Dependency for chat controller."""
    return container.chat_controller


def get_status_manager() -> ProcessingStatusManager:  # Added dependency
    """Dependency for status manager."""
    return container.status_manager