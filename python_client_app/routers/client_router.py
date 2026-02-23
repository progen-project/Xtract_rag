"""
Client API router.
Caching is now handled entirely by Nginx proxy_cache (nginx.conf).
All Redis cache get/set/invalidate calls have been removed.
"""

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

router = APIRouter()
rag_service = RAGClientService()


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------

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


@router.get("/categories/{category_id}/documents", response_model=List[DocumentResponse], tags=["Categories"])
async def list_category_documents(category_id: str):
    return await rag_service.list_documents(category_id)


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/documents", response_model=List[DocumentResponse], tags=["Documents"])
async def list_documents(category_id: Optional[str] = None):
    return await rag_service.list_documents(category_id)


@router.get("/documents/{document_id}", response_model=DocumentResponse, tags=["Documents"])
async def get_document(document_id: str):
    return await rag_service.get_document(document_id)


@router.post("/documents/upload/{category_id}", response_model=List[UploadResponse], tags=["Documents"])
async def upload_documents(
    category_id: str,
    files: List[UploadFile] = File(...),
    is_daily: bool = Form(False),
):
    file_list = []
    for file in files:
        content = await file.read()
        file_list.append(("files", (file.filename, content, file.content_type)))

    return await rag_service.upload_documents(category_id, file_list, is_daily)


@router.delete("/documents/{document_id}", tags=["Documents"])
async def delete_document(document_id: str):
    return await rag_service.delete_document(document_id)


@router.delete("/documents/{document_id}/burn", tags=["Documents"])
async def burn_document(document_id: str):
    return await rag_service.burn_document(document_id)


@router.get("/documents/{document_id}/download", tags=["Documents"])
async def download_document(document_id: str):
    stream, filename, content_type = await rag_service.download_document(document_id)

    from urllib.parse import quote
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{safe_filename}"
            )
        },
    )


@router.get("/documents/{document_id}/view", tags=["Documents"])
async def view_document(document_id: str):
    stream, filename, content_type = await rag_service.download_document(document_id)

    from urllib.parse import quote
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{filename}"; '
                f"filename*=UTF-8''{safe_filename}"
            )
        },
    )


@router.delete("/documents/cleanup/daily", tags=["Documents"])
async def cleanup_daily():
    return await rag_service.cleanup_daily()


# ---------------------------------------------------------------------------
# Batches
# ---------------------------------------------------------------------------

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
    """Proxy SSE stream from main API."""

    async def generator():
        async for data in rag_service.stream_batch_progress(batch_id):
            yield f"data: {json.dumps(data)}\n\n"

    return StreamingResponse(generator(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.get("/chat", response_model=List[ChatSession], tags=["Chat"])
async def list_chats(username: str, limit: int = 50):
    return await rag_service.list_chats(username, limit)


@router.get("/chat/{chat_id}", response_model=ChatSession, tags=["Chat"])
async def get_chat(chat_id: str, username: str):
    return await rag_service.get_chat(chat_id, username)


@router.delete("/chat/{chat_id}", tags=["Chat"])
async def delete_chat(chat_id: str, username: str):
    return await rag_service.delete_chat(chat_id, username)


@router.post("/chat", response_model=ChatResponse, tags=["Chat"])
async def send_message(
    message: str = Form(...),
    username: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[]),
) -> ChatResponse:
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
        username=username,
        chat_id=chat_id,
        category_ids=parsed_category_ids,
        document_ids=parsed_document_ids,
    )

    image_files = []
    for img in images:
        content = await img.read()
        if img.filename:
            image_files.append(("images", (img.filename, content, img.content_type)))

    return await rag_service.send_message(request, image_files)


@router.post("/chat/stream", tags=["Chat"])
async def stream_message(
    message: str = Form(...),
    username: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    images: List[UploadFile] = File(default=[]),
):
    """Proxy streaming chat to main API — returns SSE."""
    data = {"message": message, "username": username}
    if chat_id:
        data["chat_id"] = chat_id
    if category_ids:
        data["category_ids"] = category_ids
    if document_ids:
        data["document_ids"] = document_ids

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
                timeout=None,
            ) as response:
                async for line in response.aiter_lines():
                    if line.strip():
                        yield line + "\n\n"

    return StreamingResponse(
        proxy_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@router.post("/query", response_model=QueryResponse, tags=["Query"])
async def query(request: QueryRequest):
    return await rag_service.query(request)


@router.post("/query/image-search", response_model=ImageSearchResponse, tags=["Query"])
async def image_search(request: ImageSearchRequest):
    return await rag_service.search_images(request)