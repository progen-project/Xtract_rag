
from fastapi import APIRouter, UploadFile, File, HTTPException, Body, Form
from fastapi.responses import StreamingResponse
from typing import List, Optional
import json

from python_client_app.services.rag_client import RAGClientService
from python_client_app.schemas.batch import BatchStatusResponse, TerminateBatchResponse
from python_client_app.schemas.category import CategoryResponse, CategoryCreate, CategoryUpdate
from python_client_app.schemas.chat import ChatRequest, ChatResponse, ChatSession
from python_client_app.schemas.document import DocumentResponse, UploadResponse, DocumentStatus
from python_client_app.schemas.query import (
    QueryRequest, QueryResponse,
    ImageSearchRequest, ImageSearchResponse,
)
from python_client_app.core.cache import category_cache, document_cache, chat_cache

router = APIRouter()
rag_service = RAGClientService()

# --- Categories ---
@router.get("/categories", response_model=List[CategoryResponse], tags=["Categories"])
async def list_categories():
    cache_key = "list_categories"
    cached = await category_cache.get(cache_key)
    if cached:
        return cached

    categories = await rag_service.list_categories()
    await category_cache.set(cache_key, categories)
    return categories

@router.post("/categories", response_model=CategoryResponse, tags=["Categories"])
async def create_category(request: CategoryCreate):
    result = await rag_service.create_category(request)
    await category_cache.invalidate_prefix("list_categories")
    return result

@router.put("/categories/{category_id}", response_model=CategoryResponse, tags=["Categories"])
async def update_category(category_id: str, request: CategoryUpdate):
    result = await rag_service.update_category(category_id, request)
    await category_cache.invalidate_prefix("list_categories")
    return result

@router.delete("/categories/{category_id}", tags=["Categories"])
async def delete_category(category_id: str):
    result = await rag_service.delete_category(category_id)
    await category_cache.invalidate_prefix("list_categories")
    await document_cache.invalidate_prefix("list_documents")
    return result

@router.get("/categories/{category_id}/documents", response_model=List[DocumentResponse], tags=["Categories"])
async def list_category_documents(category_id: str):
    """List all documents in a specific category."""
    cache_key = f"list_documents:{category_id}"
    cached = await document_cache.get(cache_key)
    if cached:
        return cached
        
    docs = await rag_service.list_documents(category_id)
    await document_cache.set(cache_key, docs)
    return docs

# --- Documents ---
@router.get("/documents", response_model=List[DocumentResponse], tags=["Documents"])
async def list_documents(category_id: Optional[str] = None):
    cache_key = f"list_documents:{category_id}" if category_id else "list_documents:all"
    cached = await document_cache.get(cache_key)
    if cached:
        return cached

    docs = await rag_service.list_documents(category_id)
    await document_cache.set(cache_key, docs)
    return docs

@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
async def get_document(document_id: str):
    """Get a single document's metadata."""
    cache_key = f"get_document:{document_id}"
    cached = await document_cache.get(cache_key)
    if cached:
        return cached

    doc = await rag_service.get_document(document_id)
    await document_cache.set(cache_key, doc)
    return doc

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
    
    result = await rag_service.upload_documents(category_id, file_list, is_daily)
    await document_cache.invalidate_prefix("list_documents")
    await category_cache.invalidate_prefix("list_categories") # Counts update
    return result

@router.delete("/documents/{document_id}", tags=["Documents"])
async def delete_document(document_id: str):
    result = await rag_service.delete_document(document_id)
    await document_cache.invalidate(f"get_document:{document_id}")
    await document_cache.invalidate_prefix("list_documents")
    await category_cache.invalidate_prefix("list_categories")
    return result

@router.delete("/documents/{document_id}/burn", tags=["Documents"])
async def burn_document(document_id: str):
    result = await rag_service.burn_document(document_id)
    await document_cache.invalidate(f"get_document:{document_id}")
    await document_cache.invalidate_prefix("list_documents")
    await category_cache.invalidate_prefix("list_categories")
    return result

@router.get("/documents/{document_id}/download", tags=["Documents"])
async def download_document(document_id: str):
    """Proxy download with proper filename and content-type headers."""
    stream, filename, content_type = await rag_service.download_document(document_id)
    
    from urllib.parse import quote
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{safe_filename}'
        }
    )

@router.get("/documents/{document_id}/view", tags=["Documents"])
async def view_document(document_id: str):
    """Serve PDF inline for in-browser viewing (supports #page=N)."""
    stream, filename, content_type = await rag_service.download_document(document_id)
    
    from urllib.parse import quote
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": f'inline; filename="{filename}"; filename*=UTF-8\'\'{safe_filename}'
        }
    )

@router.delete("/documents/cleanup/daily", tags=["Documents"])
async def cleanup_daily():
    result = await rag_service.cleanup_daily()
    await document_cache.invalidate_prefix("list_documents")
    await document_cache.invalidate_prefix("get_document")
    await category_cache.invalidate_prefix("list_categories")
    return result

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
            
    return StreamingResponse(generator(), media_type="text/event-stream")

# --- Chat ---
@router.get("/chat", response_model=List[ChatSession], tags=["Chat"])
async def list_chats(limit: int = 50):
    cache_key = f"list_chats:{limit}"
    cached = await chat_cache.get(cache_key)
    if cached:
        return cached

    chats = await rag_service.list_chats(limit)
    await chat_cache.set(cache_key, chats)
    return chats

@router.get("/chat/{chat_id}", response_model=ChatSession, tags=["Chat"])
async def get_chat(chat_id: str):
    cache_key = f"get_chat:{chat_id}"
    cached = await chat_cache.get(cache_key)
    if cached:
        return cached

    chat = await rag_service.get_chat(chat_id)
    await chat_cache.set(cache_key, chat)
    return chat

@router.delete("/chat/{chat_id}", tags=["Chat"])
async def delete_chat(chat_id: str):
    result = await rag_service.delete_chat(chat_id)
    await chat_cache.invalidate(f"get_chat:{chat_id}")
    await chat_cache.invalidate_prefix("list_chats")
    return result

@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def send_message(
    message: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[])
) -> ChatResponse:
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
    
    parsed_document_ids = None
    if document_ids:
        try:
            parsed_document_ids = json.loads(document_ids)
            if isinstance(parsed_document_ids, str):
                parsed_document_ids = [parsed_document_ids]
        except json.JSONDecodeError:
            parsed_document_ids = [did.strip() for did in document_ids.split(",") if did.strip()]

    request = ChatRequest(
        message=message,
        chat_id=chat_id,
        category_ids=parsed_category_ids,
        document_ids=parsed_document_ids,
    )
    
    # Process images for service
    image_files = []
    for img in images:
        content = await img.read()
        if img.filename:  # Skip empty file inputs
            image_files.append(('images', (img.filename, content, img.content_type)))
        
    result = await rag_service.send_message(request, image_files)
    
    await chat_cache.invalidate_prefix("list_chats")
    if result.chat_id:
        await chat_cache.invalidate(f"get_chat:{result.chat_id}")
        
    return result

@router.post("/chat/stream", tags=["Chat"])
async def stream_message(
    message: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[])
):
    """
    Proxy streaming chat to main API.
    Returns Server-Sent Events with word-by-word response tokens.
    """
    # Build form data for backend
    data = {"message": message}
    if chat_id:
        data["chat_id"] = chat_id
    if category_ids:
        data["category_ids"] = category_ids
    if document_ids:
        data["document_ids"] = document_ids

    # Read image files
    files = []
    for img in images:
        content = await img.read()
        if img.filename:
            files.append(("images", (img.filename, content, img.content_type)))

    async def proxy_stream():
        async with await rag_service._get_client() as client:
            async with client.stream(
                "POST",
                "/chat/stream",
                data=data,
                files=files if files else None,
                timeout=None
            ) as response:
                # Invalidate cache on stream start
                await chat_cache.invalidate_prefix("list_chats")
                if chat_id:
                    await chat_cache.invalidate(f"get_chat:{chat_id}")
                    
                async for line in response.aiter_lines():
                    if line.strip():
                        yield line + "\n\n"

    return StreamingResponse(
        proxy_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# --- Query ---
@router.post("/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    """Proxy RAG query to main API."""
    return await rag_service.query(request)

@router.post("/query/image-search", response_model=ImageSearchResponse, tags=["Query"])
async def image_search(request: ImageSearchRequest):
    """Proxy image search to main API."""
    return await rag_service.search_images(request)
