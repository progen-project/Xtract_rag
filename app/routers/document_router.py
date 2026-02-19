"""
Document API router.

Thin router that delegates to DocumentController.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from typing import List, Optional
import uuid
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

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post("/upload/{category_id}", response_model=List[DocumentUploadResponse])
async def upload_document(
    background_tasks: BackgroundTasks,
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
        
        # Process in background
        background_tasks.add_task(
            controller.process_document, 
            response.document_id,
            batch_id
        )
        responses.append(response)
    
    if not responses and files:
         raise HTTPException(status_code=400, detail="No valid PDF files found in batch")
    
    return responses


@router.post("/upload/daily/{category_id}", response_model=List[DocumentUploadResponse])
async def upload_daily_documents(
    background_tasks: BackgroundTasks,
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
    try:
        category = await category_controller.get_category(category_id)
    except Exception:
         # Optionally handle if category doesn't exist? 
         # The controller checks it too, but we use name here.
         # Let's rely on controller check or fetch it.
         # We need category name for folder.
         # So we must fetch it.
         pass

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
        
        background_tasks.add_task(
            controller.process_document, 
            response.document_id,
            batch_id
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
