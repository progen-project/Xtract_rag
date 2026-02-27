"""
FastAPI application factory.

Creates and configures the FastAPI application.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from pathlib import Path
import logging

from .lifespan import lifespan
from .logging_config import setup_logging
from .logging_middleware import RequestLoggingMiddleware
from app.utils.exceptions import (
    CategoryNotFoundError,
    DocumentNotFoundError,
    ChatNotFoundError,
    ValidationError
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance.
    """
    # ── Initialize logging first ──
    from app.config.settings import get_settings
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        log_dir=settings.log_dir,
        log_json=settings.log_json,
    )
    
    app = FastAPI(
        title="PetroRAG API",
        description="""
        Multimodal RAG Pipeline with Clean Architecture
        
        Features:
        - Category-based document organization
        - PDF upload and processing (Docling)
        - Table and figure extraction
        - LlamaIndex semantic search with Qdrant
        - Chat with file-based image uploads
        """,
        version="3.0.0",
        lifespan=lifespan
    )
    
    # ── Request logging middleware (must be added before CORS) ──
    app.add_middleware(RequestLoggingMiddleware)
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )
    
    # Register exception handlers
    _register_exception_handlers(app)
    
    # Include routers
    _include_routers(app)
    
    # Root and health endpoints
    _register_root_endpoints(app)
    
    # Mount static file directories for images
    if settings.images_dir.exists():
        app.mount("/extracted_images", StaticFiles(directory=str(settings.images_dir)), name="extracted_images")
    
    if settings.chat_images_dir.exists():
        app.mount("/chat_images", StaticFiles(directory=str(settings.chat_images_dir)), name="chat_images")
    
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers with logging."""
    
    @app.exception_handler(CategoryNotFoundError)
    async def category_not_found_handler(request, exc):
        logger.warning(f"Category not found: {exc.category_id} — {request.method} {request.url.path}")
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    
    @app.exception_handler(DocumentNotFoundError)
    async def document_not_found_handler(request, exc):
        logger.warning(f"Document not found: {exc.document_id} — {request.method} {request.url.path}")
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    
    @app.exception_handler(ChatNotFoundError)
    async def chat_not_found_handler(request, exc):
        logger.warning(f"Chat not found: {exc.chat_id} — {request.method} {request.url.path}")
        return JSONResponse(status_code=404, content={"detail": str(exc)})
    
    @app.exception_handler(ValidationError)
    async def validation_error_handler(request, exc):
        logger.warning(f"Validation error: {exc} — {request.method} {request.url.path}")
        return JSONResponse(status_code=400, content={"detail": str(exc)})


def _include_routers(app: FastAPI) -> None:
    """Include all API routers."""
    from app.routers import (
        category_router,
        document_router,
        query_router,
        chat_router,
        batch_router
    )
    
    app.include_router(category_router.router)
    app.include_router(document_router.router)
    app.include_router(query_router.router)
    app.include_router(chat_router.router)
    app.include_router(batch_router.router)


def _register_root_endpoints(app: FastAPI) -> None:
    """Register root and health endpoints."""
    from .dependencies import container
    
    @app.get("/")
    async def root():
        """Root endpoint with API information."""
        return {
            "name": "PetroRAG API",
            "version": "3.0.0",
            "description": "Multimodal RAG Pipeline with Clean Architecture",
            "endpoints": {
                "categories": "/api/categories",
                "documents": "/api/documents",
                "query": "/api/query",
                "chat": "/api/chat",
                "docs": "/docs"
            }
        }
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "services": {
                "mongodb": "connected" if container.base_repo.is_connected else "disconnected",
                "llm": "configured" if container.settings.llm_api_key else "not configured",
                "indexer": "initialized" if container.indexer._initialized else "not initialized"
            }
        }
