"""
Document API router.

Thin router that delegates to DocumentController.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Optional
import uuid
import asyncio
import logging
from pathlib import Path

from app.core.dependencies import (
    get_document_controller, 
    get_category_controller, 
    get_status_manager,
    container
)
from app.controllers import DocumentController, CategoryController
from app.services.status import ProcessingStatusManager
from app.schemas import DocumentMetadata, DocumentUploadResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# Per-document processing timeout in seconds (10 minutes)
DOCUMENT_PROCESSING_TIMEOUT = 1800


async def _safe_process_document(
    controller: DocumentController,
    document_id: str,
    batch_id: str,
    filename: str,
    status_manager: ProcessingStatusManager,
    timeout: int = DOCUMENT_PROCESSING_TIMEOUT,
):
    """
    Process a single document with timeout and error isolation.
    
    Each document runs as an independent asyncio task so that:
    - One file hanging does NOT block other files in the batch
    - A timeout prevents infinite hangs
    - Errors are caught and status updated without affecting others
    """
    try:
        await asyncio.wait_for(
            controller.process_document(document_id, batch_id),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.error(
            f"Document {document_id} ({filename}) timed out after {timeout}s"
        )
        try:
            from app.schemas import DocumentStatus
            await controller.document_repo.update_status(
                document_id, DocumentStatus.FAILED, 
                f"Processing timed out after {timeout} seconds"
            )
            await status_manager.update_file_status(
                batch_id, filename, "failed",
                f"Processing timed out after {timeout} seconds"
            )
        except Exception:
            pass
    except Exception as e:
        logger.error(
            f"Document {document_id} ({filename}) failed: {e}"
        )
        # process_document already handles its own error status updates,
        # but we log here for visibility


@router.post("/upload/{category_id}", response_model=List[DocumentUploadResponse])
async def upload_document(
    category_id: str,
    files: List[UploadFile] = File(...),
    controller: DocumentController = Depends(get_document_controller),
    category_controller: CategoryController = Depends(get_category_controller),
    status_manager: ProcessingStatusManager = Depends(get_status_manager)
):
    """Upload multiple PDF documents for processing (Max 50)."""
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files allowed per batch")
        
    settings = container.settings
    
    # Get category for folder organization
    category = await category_controller.get_category(category_id)
    
    # Sanitize category name
    safe_name = "".join([c for c in category.name if c.isalnum() or c in (' ', '_', '-')]).strip()
    if not safe_name:
        safe_name = category_id
        
    # Create category directory
    category_dir = settings.upload_dir / safe_name
    category_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize batch tracking
    batch_id = uuid.uuid4().hex
    status_manager.init_batch(batch_id, files)
    
    responses = []
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            # Update status to failed for non-PDF
            await status_manager.update_file_status(
                batch_id, file.filename, "failed", "File is not a PDF"
            )
            continue
        
        # Save file
        file_path = category_dir / f"{uuid.uuid4().hex}_{file.filename}"
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Upload and schedule processing
        response = await controller.upload_document(
            category_id=category_id,
            filename=file.filename,
            file_path=file_path,
            file_size=len(content),
            batch_id=batch_id
        )
        
        # Process as independent concurrent task (NOT BackgroundTasks queue)
        asyncio.create_task(
            _safe_process_document(
                controller, response.document_id, batch_id,
                file.filename, status_manager
            )
        )
        responses.append(response)
    
    if not responses and files:
         raise HTTPException(status_code=400, detail="No valid PDF files found in batch")
    
    return responses


@router.post("/upload/daily/{category_id}", response_model=List[DocumentUploadResponse])
async def upload_daily_documents(
    category_id: str,
    files: List[UploadFile] = File(...),
    controller: DocumentController = Depends(get_document_controller),
    category_controller: CategoryController = Depends(get_category_controller),
    status_manager: ProcessingStatusManager = Depends(get_status_manager)
):
    """
    Upload temporary documents (Max 50).
    These documents will be automatically deleted after 24 hours.
    """
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 files allowed per batch")
        
    settings = container.settings
    
    # Get category for folder organization
    category = await category_controller.get_category(category_id)
    
    # Sanitize category name
    safe_name = "".join([c for c in category.name if c.isalnum() or c in (' ', '_', '-')]).strip()
    if not safe_name:
        safe_name = category_id
        
    # Create category directory
    category_dir = settings.upload_dir / safe_name
    category_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize batch tracking
    batch_id = uuid.uuid4().hex
    status_manager.init_batch(batch_id, files)
    
    responses = []
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            await status_manager.update_file_status(
                batch_id, file.filename, "failed", "File is not a PDF"
            )
            continue
        
        # Save file
        file_path = category_dir / f"{uuid.uuid4().hex}_{file.filename}"
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Upload and schedule processing (is_daily=True)
        response = await controller.upload_document(
            category_id=category_id,
            filename=file.filename,
            file_path=file_path,
            file_size=len(content),
            batch_id=batch_id,
            is_daily=True
        )
        
        # Process as independent concurrent task (NOT BackgroundTasks queue)
        asyncio.create_task(
            _safe_process_document(
                controller, response.document_id, batch_id,
                file.filename, status_manager
            )
        )
        responses.append(response)
    
    if not responses and files:
         raise HTTPException(status_code=400, detail="No valid PDF files found in batch")

    return responses


@router.delete("/cleanup/daily")
async def cleanup_daily_uploads(
    controller: DocumentController = Depends(get_document_controller)
):
    """
    Delete all documents older than 24 hours.
    Removes traces from MongoDB, Qdrant, and disk.
    """
    result = await controller.cleanup_daily_uploads()
    return result


@router.delete("/{document_id}/burn")
async def burn_document(
    document_id: str,
    controller: DocumentController = Depends(get_document_controller)
):
    """
    Burn a document: Completely remove it and all related data/artifacts.
    """
    await controller.burn_document(document_id)
    return {"message": f"Document {document_id} burned successfully"}


@router.get("", response_model=List[DocumentMetadata])
async def list_documents(
    category_id: Optional[str] = None,
    controller: DocumentController = Depends(get_document_controller)
):
    """List all documents."""
    return await controller.list_documents(category_id)


@router.get("/{document_id}", response_model=DocumentMetadata)
async def get_document(
    document_id: str,
    controller: DocumentController = Depends(get_document_controller)
):
    """Get document metadata."""
    return await controller.get_document(document_id)


@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    controller: DocumentController = Depends(get_document_controller)
):
    """Delete a document."""
    await controller.delete_document(document_id)
    return {"message": f"Document {document_id} deleted"}


@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    controller: DocumentController = Depends(get_document_controller)
):
    """Download a document file."""
    # Get metadata
    doc = await controller.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")
        
    return FileResponse(
        path=file_path,
        filename=doc.filename,
        media_type="application/pdf"
    )
