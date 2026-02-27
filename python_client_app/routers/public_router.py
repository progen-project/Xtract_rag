"""
Public router — root-level endpoints for external integration.
Serves document view/download without the /client-api prefix.
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from urllib.parse import quote

from python_client_app.services.rag_client import RAGClientService

router = APIRouter()
rag_service = RAGClientService()


@router.get("/documents/{document_id}/view", tags=["Public Documents"])
async def view_document(document_id: str):
    stream, filename, content_type = await rag_service.download_document(document_id)
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'inline; filename="{filename}"; filename*=UTF-8\'\'{safe_filename}'
            )
        },
    )


@router.get("/documents/{document_id}/download", tags=["Public Documents"])
async def download_document(document_id: str):
    stream, filename, content_type = await rag_service.download_document(document_id)
    safe_filename = quote(filename)
    return StreamingResponse(
        stream,
        media_type=content_type,
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; filename*=UTF-8\'\'{safe_filename}'
            )
        },
    )
