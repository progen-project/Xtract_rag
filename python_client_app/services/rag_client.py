"""
RAG Client Service.
Encapsulates all HTTP communication with the main API.
"""
import httpx
import json
from typing import List, AsyncGenerator, Dict, Any, Optional
from datetime import datetime

from python_client_app.config import ClientConfig
from python_client_app.schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from python_client_app.schemas.document import DocumentResponse, UploadResponse, DocumentStatus
from python_client_app.schemas.batch import BatchStatusResponse, TerminateBatchResponse
from python_client_app.schemas.chat import ChatRequest, ChatResponse, ChatSession


class RAGClientService:
    def __init__(self):
        self.base_url = ClientConfig.BASE_URL
        self.timeout = ClientConfig.TIMEOUT
    
    async def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    # --- Categories ---
    async def list_categories(self) -> List[CategoryResponse]:
        async with await self._get_client() as client:
            resp = await client.get("/categories")
            resp.raise_for_status()
            return [CategoryResponse(**item) for item in resp.json()]

    async def create_category(self, request: CategoryCreate) -> CategoryResponse:
        async with await self._get_client() as client:
            resp = await client.post("/categories", json=request.model_dump())
            resp.raise_for_status()
            return CategoryResponse(**resp.json())

    async def update_category(self, category_id: str, request: CategoryUpdate) -> CategoryResponse:
        async with await self._get_client() as client:
            resp = await client.put(f"/categories/{category_id}", json=request.model_dump(exclude_unset=True))
            resp.raise_for_status()
            return CategoryResponse(**resp.json())

    async def delete_category(self, category_id: str) -> Dict[str, str]:
        async with await self._get_client() as client:
            resp = await client.delete(f"/categories/{category_id}")
            resp.raise_for_status()
            return resp.json()

    # --- Documents ---
    async def list_documents(self, category_id: Optional[str] = None) -> List[DocumentResponse]:
        params = {"category_id": category_id} if category_id else {}
        async with await self._get_client() as client:
            resp = await client.get("/documents", params=params)
            resp.raise_for_status()
            return [DocumentResponse(**item) for item in resp.json()]

    async def upload_documents(self, category_id: str, files: List[tuple], is_daily: bool = False) -> List[UploadResponse]:
        endpoint = f"/documents/upload/daily/{category_id}" if is_daily else f"/documents/upload/{category_id}"
        
        # Files structure for httpx: {'files': (filename, content, type)}
        # The API expects a list of files with key 'files'
        # The input 'files' here is expected to be list of (filename, content_bytes, content_type)
        
        async with await self._get_client() as client:
            # We need to construct multipart/form-data manually or let httpx handle it
            # httpx format: files=[('files', (filename, content, content_type)), ...]
            resp = await client.post(endpoint, files=files)
            resp.raise_for_status()
            return [UploadResponse(**item) for item in resp.json()]

    async def delete_document(self, document_id: str) -> Dict[str, str]:
        async with await self._get_client() as client:
            resp = await client.delete(f"/documents/{document_id}")
            resp.raise_for_status()
            return resp.json()

    async def burn_document(self, document_id: str) -> Dict[str, str]:
        async with await self._get_client() as client:
            # Heavy operation, increase timeout
            resp = await client.delete(f"/documents/{document_id}/burn", timeout=300.0)
            resp.raise_for_status()
            return resp.json()

    async def download_document(self, document_id: str) -> AsyncGenerator[bytes, None]:
        """Stream file download."""
        async with await self._get_client() as client:
            async with client.stream("GET", f"/documents/{document_id}/download", timeout=None) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def cleanup_daily(self) -> Dict[str, Any]:
        async with await self._get_client() as client:
            resp = await client.delete("/documents/cleanup/daily", timeout=300.0)
            resp.raise_for_status()
            return resp.json()

    # --- Batches ---
    async def get_batch_status(self, batch_id: str) -> Optional[BatchStatusResponse]:
        async with await self._get_client() as client:
            resp = await client.get(f"/batches/{batch_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return BatchStatusResponse(**resp.json())

    async def terminate_batch(self, batch_id: str) -> TerminateBatchResponse:
        async with await self._get_client() as client:
            resp = await client.post(f"/batches/{batch_id}/terminate")
            resp.raise_for_status()
            return TerminateBatchResponse(**resp.json())

    async def stream_batch_progress(self, batch_id: str) -> AsyncGenerator[Dict, None]:
        """Yields SSE events."""
        async with await self._get_client() as client:
            async with client.stream("GET", f"/batches/{batch_id}/progress", timeout=None) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield json.loads(line[6:])

    # --- Chat ---
    async def list_chats(self, limit: int = 50) -> List[ChatSession]:
        async with await self._get_client() as client:
            resp = await client.get("/chat", params={"limit": limit})
            resp.raise_for_status()
            return [ChatSession(**item) for item in resp.json()]
            
    async def get_chat(self, chat_id: str) -> ChatSession:
        async with await self._get_client() as client:
            resp = await client.get(f"/chat/{chat_id}")
            resp.raise_for_status()
            return ChatSession(**resp.json())

    async def delete_chat(self, chat_id: str) -> Dict[str, str]:
        async with await self._get_client() as client:
            resp = await client.delete(f"/chat/{chat_id}")
            resp.raise_for_status()
            return resp.json()

    async def send_message(self, request: ChatRequest, images: List[tuple] = None) -> ChatResponse:
        # Note: Main API uses Form data for chat if images included.
        
        data = {
            "message": request.message,
            "top_k": str(request.top_k)
        }
        if request.chat_id:
            data["chat_id"] = request.chat_id
            
        if request.category_ids:
            # Backend expects a list of strings, or a JSON string representation of it?
            # Router code: category_ids: Optional[str] = Form(None) -> loads json
            data["category_ids"] = json.dumps(request.category_ids)

        # Prepare files
        # files argument in httpx: {'images': (filename, content, type), ...} 
        # But we pass list of tuples directly: [('images', (...)), ...]
        files = images if images else []

        async with await self._get_client() as client:
            # If files are present, data must be sent as form (httpx handles this when files is passed)
            # If no files, we can still use files=[] or just data.
            # Using 'data' + 'files' forces multipart/form-data
            resp = await client.post("/chat", data=data, files=files)
            resp.raise_for_status()
            return ChatResponse(**resp.json())
