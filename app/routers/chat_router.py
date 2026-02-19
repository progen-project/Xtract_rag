"""
Chat API router.

Thin router that delegates to ChatController.
"""
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from typing import List, Optional
import json

from app.core.dependencies import get_chat_controller
from app.controllers import ChatController
from app.schemas import ChatSession, ChatResponse

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    message: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    top_k: int = Form(5),
    images: List[UploadFile] = File(default=[]),
    controller: ChatController = Depends(get_chat_controller)
):
    """
    Chat with file-based image uploads.
    
    - **message**: User's text message
    - **chat_id**: Optional existing chat ID
    - **category_ids**: Optional JSON array of category IDs
    - **document_ids**: Optional JSON array of document IDs
    - **images**: Optional image files (max 10)
    """
    # Parse category_ids
    parsed_category_ids = None
    if category_ids:
        try:
            parsed_category_ids = json.loads(category_ids)
            if isinstance(parsed_category_ids, str):
                parsed_category_ids = [parsed_category_ids]
        except json.JSONDecodeError:
            parsed_category_ids = [cid.strip() for cid in category_ids.split(",") if cid.strip()]
    
    # Parse document_ids
    parsed_document_ids = None
    if document_ids:
        try:
            parsed_document_ids = json.loads(document_ids)
            if isinstance(parsed_document_ids, str):
                parsed_document_ids = [parsed_document_ids]
        except json.JSONDecodeError:
            parsed_document_ids = [did.strip() for did in document_ids.split(",") if did.strip()]
    
    # Save images
    image_paths = []
    if images and images[0].filename:
        temp_chat_id = chat_id or f"temp_{__import__('uuid').uuid4().hex[:12]}"
        image_paths = await controller.save_uploaded_images(images, temp_chat_id)
    
    response = await controller.send_message(
        message=message,
        chat_id=chat_id,
        category_ids=parsed_category_ids,
        document_ids=parsed_document_ids,
        image_paths=image_paths,
        top_k=top_k
    )
    
    return response


@router.post("/stream")
async def chat_stream(
    message: str = Form(...),
    chat_id: Optional[str] = Form(None),
    category_ids: Optional[str] = Form(None),
    document_ids: Optional[str] = Form(None),
    top_k: int = Form(5),
    images: List[UploadFile] = File(default=[]),
    controller: ChatController = Depends(get_chat_controller)
):
    """
    Streaming chat endpoint.
    Returns Server-Sent Events with word-by-word response tokens.
    
    Events:
    - data: {"token": "word"} — each content token
    - data: {"done": true, "chat_id": "...", "answer": "...", "sources": {...}, ...} — final metadata
    """
    from fastapi.responses import StreamingResponse

    # Parse category_ids
    parsed_category_ids = None
    if category_ids:
        try:
            parsed_category_ids = json.loads(category_ids)
            if isinstance(parsed_category_ids, str):
                parsed_category_ids = [parsed_category_ids]
        except json.JSONDecodeError:
            parsed_category_ids = [cid.strip() for cid in category_ids.split(",") if cid.strip()]

    # Parse document_ids
    parsed_document_ids = None
    if document_ids:
        try:
            parsed_document_ids = json.loads(document_ids)
            if isinstance(parsed_document_ids, str):
                parsed_document_ids = [parsed_document_ids]
        except json.JSONDecodeError:
            parsed_document_ids = [did.strip() for did in document_ids.split(",") if did.strip()]

    # Save images
    image_paths = []
    if images and images[0].filename:
        temp_chat_id = chat_id or f"temp_{__import__('uuid').uuid4().hex[:12]}"
        image_paths = await controller.save_uploaded_images(images, temp_chat_id)

    return StreamingResponse(
        controller.send_message_stream(
            message=message,
            chat_id=chat_id,
            category_ids=parsed_category_ids,
            document_ids=parsed_document_ids,
            image_paths=image_paths,
            top_k=top_k
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("", response_model=List[ChatSession])
async def list_chats(
    limit: int = 50,
    controller: ChatController = Depends(get_chat_controller)
):
    """List all chat sessions."""
    return await controller.list_chats(limit)


@router.get("/{chat_id}", response_model=ChatSession)
async def get_chat(
    chat_id: str,
    controller: ChatController = Depends(get_chat_controller)
):
    """Get a chat session."""
    return await controller.get_chat(chat_id)


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    controller: ChatController = Depends(get_chat_controller)
):
    """Delete a chat session."""
    await controller.delete_chat(chat_id)
    return {"message": f"Chat {chat_id} deleted"}
