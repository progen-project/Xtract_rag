
from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json

from python_client_app.services.rag_client import RAGClientService
from python_client_app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from python_client_app.schemas.document import DocumentResponse, UploadResponse, DocumentStatus
from python_client_app.schemas.batch import BatchStatusResponse, TerminateBatchResponse
from python_client_app.schemas.chat import ChatRequest, ChatResponse, ChatSession
from python_client_app.schemas.query import (
    QueryRequest, QueryResponse,
    ImageSearchRequest, ImageSearchResponse,
)

router = APIRouter()
rag_service = RAGClientService()

# --- Categories ---
@router.get("/categories", response_model=List[CategoryResponse], tags=["Categories"])
async def list_categories():
    return await rag_service.list_categories()

@router.post("/categories", response_model=CategoryResponse, tags=["Categories"])
async def create_category(request: CategoryCreate):
    return await rag_service.create_category(request)

@router.put("/categories/{category_id}", response_model=CategoryResponse, tags=["Categories"])
async def update_category(category_id: str, request: CategoryUpdate):
    return await rag_service.update_category(category_id, request)

@router.delete("/categories/{category_id}", tags=["Categories"])
async def delete_category(category_id: str):
    return await rag_service.delete_category(category_id)

# --- Documents ---
@router.get("/documents", response_model=List[DocumentResponse], tags=["Documents"])
async def list_documents(category_id: Optional[str] = None):
    return await rag_service.list_documents(category_id)

@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
async def get_document(document_id: str):
    """Get a single document's metadata."""
    return await rag_service.get_document(document_id)

@router.post("/documents/upload/{category_id}", response_model=List[UploadResponse], tags=["Documents"])
async def upload_documents(
    category_id: str,
    files: List[UploadFile] = File(...),
    is_daily: bool = Form(False)
):
    """
    Proxy upload to main API. 
    Note: We read file content into memory to forward it. 
    For large files, streaming would be better, but keeping it simple for now.
    """
    file_list = []
    for file in files:
        content = await file.read()
        file_list.append(('files', (file.filename, content, file.content_type)))
    
    return await rag_service.upload_documents(category_id, file_list, is_daily)

@router.delete("/documents/{document_id}", tags=["Documents"])
async def delete_document(document_id: str):
    return await rag_service.delete_document(document_id)

@router.delete("/documents/{document_id}/burn", tags=["Documents"])
async def burn_document(document_id: str):
    return await rag_service.burn_document(document_id)

@router.get("/documents/{document_id}/download", tags=["Documents"])
async def download_document(document_id: str):
    """Proxy download with proper filename and content-type headers."""
    stream, filename, content_type = await rag_service.download_document(document_id)
    
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )

@router.delete("/documents/cleanup/daily", tags=["Documents"])
async def cleanup_daily():
    return await rag_service.cleanup_daily()

# --- Batches ---
@router.get("/batches/{batch_id}", response_model=Optional[BatchStatusResponse], tags=["Batches"])
async def get_batch_status(batch_id: str):
    status = await rag_service.get_batch_status(batch_id)
    if not status:
        raise HTTPException(status_code=404, detail="Batch not found")
    return status

@router.post("/batches/{batch_id}/terminate", response_model=TerminateBatchResponse, tags=["Batches"])
async def terminate_batch(batch_id: str):
    return await rag_service.terminate_batch(batch_id)

@router.get("/batches/{batch_id}/progress", tags=["Batches"])
async def stream_batch_progress(batch_id: str):
    """Proxy SSE stream."""
    async def generator():
        async for data in rag_service.stream_batch_progress(batch_id):
            yield f"data: {json.dumps(data)}\n\n"
            
    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
    )

# --- Chat ---
@router.get("/chat", response_model=List[ChatSession], tags=["Chat"])
async def list_chats(limit: int = 50):
    return await rag_service.list_chats(limit)

@router.get("/chat/{chat_id}", response_model=ChatSession, tags=["Chat"])
async def get_chat(chat_id: str):
    return await rag_service.get_chat(chat_id)

@router.delete("/chat/{chat_id}", tags=["Chat"])
async def delete_chat(chat_id: str):
    return await rag_service.delete_chat(chat_id)

@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def send_message(
    message: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    top_k: int = Form(5),
    images: List[UploadFile] = File(default=[])
):
    """
    Proxy chat request. 
    Accepts Form data to match main API and allow efficient forwarding.
    """
    parsed_category_ids = None
    if category_ids:
        try:
            parsed_category_ids = json.loads(category_ids)
            if isinstance(parsed_category_ids, str):
                parsed_category_ids = [parsed_category_ids]
        except json.JSONDecodeError:
            parsed_category_ids = [cid.strip() for cid in category_ids.split(",") if cid.strip()]
            
    request = ChatRequest(
        message=message,
        chat_id=chat_id,
        category_ids=parsed_category_ids,
        top_k=top_k
    )
    
    # Process images for service
    image_files = []
    for img in images:
        content = await img.read()
        if img.filename:  # Skip empty file inputs
            image_files.append(('images', (img.filename, content, img.content_type)))
        
    return await rag_service.send_message(request, image_files)

# --- Query ---
@router.post("/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    """Proxy RAG query to main API."""
    return await rag_service.query(request)

@router.post("/query/image-search", response_model=ImageSearchResponse, tags=["Query"])
async def image_search(request: ImageSearchRequest):
    """Proxy image search to main API."""
    return await rag_service.search_images(request)
