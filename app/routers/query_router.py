"""
Query API router.

Thin router that delegates to QueryController.
"""
from fastapi import APIRouter, Depends

from app.core.dependencies import get_query_controller
from app.controllers import QueryController
from app.schemas import (
    QueryRequest,
    QueryResponse,
    ImageSearchRequest,
    ImageSearchResponse
)

router = APIRouter(prefix="/api/query", tags=["Query"])


@router.post("", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    controller: QueryController = Depends(get_query_controller)
):
    """Perform a RAG query."""
    return await controller.query(request)


@router.post("/image-search", response_model=ImageSearchResponse)
async def image_search(
    request: ImageSearchRequest,
    controller: QueryController = Depends(get_query_controller)
):
    """Search for images using text or image."""
    return await controller.search_images(request)
