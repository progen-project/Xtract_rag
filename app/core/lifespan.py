"""
Application lifespan management.

Handles startup and shutdown events.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

from .dependencies import container

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Initializes all components at startup and cleans up at shutdown.
    """
    # Startup
    logger.info("Starting PetroRAG API...")
    await container.initialize()
    logger.info("PetroRAG API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down PetroRAG API...")
    await container.shutdown()
    logger.info("PetroRAG API shutdown complete")
