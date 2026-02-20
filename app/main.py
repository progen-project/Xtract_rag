"""
PetroRAG - Multimodal RAG Pipeline API

Entry point for the FastAPI application.
Logging is configured automatically by create_app() via logging_config.
"""
from app.core import create_app

# Create FastAPI application
app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True
    )
