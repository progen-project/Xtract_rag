"""
Batch API router.

Handles batch-level operations: status, progress, termination.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.dependencies import (
    get_document_controller, 
    get_status_manager
)
from app.controllers import DocumentController
from app.services.status import ProcessingStatusManager

router = APIRouter(prefix="/api/batches", tags=["Batches"])


@router.get("/{batch_id}", response_model=dict)
async def get_batch_status(
    batch_id: str,
    status_manager: ProcessingStatusManager = Depends(get_status_manager)
):
    """
    Get current status of a batch (One-time snapshot, NOT SSE).
    Returns the status of all files in the batch.
    """
    status = status_manager.get_batch_status(batch_id)
    if not status:
        raise HTTPException(status_code=404, detail="Batch not found")
    return status


@router.get("/{batch_id}/progress")
async def get_batch_progress(
    batch_id: str,
    status_manager: ProcessingStatusManager = Depends(get_status_manager)
):
    """Stream upload progress using Server-Sent Events (SSE)."""
    return StreamingResponse(
        status_manager.stream_status(batch_id),
        media_type="text/event-stream",
        headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        }
    )


@router.post("/{batch_id}/terminate")
async def terminate_batch(
    batch_id: str,
    controller: DocumentController = Depends(get_document_controller)
):
    """
    Terminate a batch upload.
    Keeps completed documents, deletes incomplete ones.
    """
    return await controller.terminate_batch(batch_id)
