"""
Document API router.

Thin router that delegates to DocumentController.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, BackgroundTasks
from typing import List, Optional
import uuid
from pathlib import Path

from app.core.dependencies import get_document_controller, get_category_controller, container
from app.controllers import DocumentController, CategoryController
from app.schemas import DocumentMetadata, DocumentUploadResponse

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post("/upload/{category_id}", response_model=List[DocumentUploadResponse])
async def upload_document(
    background_tasks: BackgroundTasks,
    category_id: str,
    files: List[UploadFile] = File(...),
    controller: DocumentController = Depends(get_document_controller),
    category_controller: CategoryController = Depends(get_category_controller)
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
    
    responses = []
    
    for file in files:
        if not file.filename.lower().endswith('.pdf'):
            # Skip non-PDFs or raise error? 
            # Raising error fails the whole batch. Better to skip or error.
            # User implies PDF workflow. Let's error for safety.
            raise HTTPException(status_code=400, detail=f"File {file.filename} is not a PDF")
        
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
            file_size=len(content)
        )
        
        # Process in background
        background_tasks.add_task(controller.process_document, response.document_id)
        responses.append(response)
    
    return responses


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
