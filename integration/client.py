import requests
import json
from enum import Enum
from typing import List, Optional, Dict, Any, Generator
from datetime import datetime
from pydantic import BaseModel, Field

# --- configuration ---
BASE_URL = "http://localhost:8080/api"

# --- Schemas ---

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class CategoryCreate(BaseModel):
    name: str
    description: Optional[str] = None

class CategoryResponse(BaseModel):
    category_id: str
    name: str
    description: Optional[str]
    document_count: int
    created_at: datetime

class DocumentUploadResponse(BaseModel):
    document_id: str
    category_id: str
    filename: str
    status: DocumentStatus
    batch_id: Optional[str] = None
    message: Optional[str] = None

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    category_ids: Optional[List[str]] = None

class QueryRequest(BaseModel):
    query: str
    category_ids: Optional[List[str]] = None

# --- Client ---

class RAGClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")

    # --- Categories ---
    
    def create_category(self, name: str, description: str = None) -> CategoryResponse:
        """Create a new category."""
        payload = CategoryCreate(name=name, description=description).model_dump()
        response = requests.post(f"{self.base_url}/categories", json=payload)
        response.raise_for_status()
        return CategoryResponse(**response.json())

    def list_categories(self) -> List[CategoryResponse]:
        """List all categories."""
        response = requests.get(f"{self.base_url}/categories")
        response.raise_for_status()
        return [CategoryResponse(**item) for item in response.json()]

    def delete_category(self, category_id: str) -> None:
        """Delete a category."""
        requests.delete(f"{self.base_url}/categories/{category_id}").raise_for_status()

    # --- Documents ---

    def upload_documents(self, category_id: str, file_paths: List[str]) -> List[DocumentUploadResponse]:
        """Upload PDF documents to a category (Permanent)."""
        url = f"{self.base_url}/documents/upload/{category_id}"
        files = [('files', open(path, 'rb')) for path in file_paths]
        
        try:
            response = requests.post(url, files=files)
            response.raise_for_status()
            return [DocumentUploadResponse(**item) for item in response.json()]
        finally:
            for _, f in files:
                f.close()

    def upload_daily_documents(self, category_id: str, file_paths: List[str]) -> List[DocumentUploadResponse]:
        """
        Upload 'daily' documents to a category.
        These documents are automatically deleted after 24 hours.
        """
        url = f"{self.base_url}/documents/upload/daily/{category_id}"
        files = [('files', open(path, 'rb')) for path in file_paths]
        
        try:
            response = requests.post(url, files=files)
            response.raise_for_status()
            return [DocumentUploadResponse(**item) for item in response.json()]
        finally:
            for _, f in files:
                f.close()

    def listen_to_progress(self, batch_id: str) -> Generator[Dict[str, Any], None, None]:
        """Generator that yields progress events for a batch."""
        url = f"{self.base_url}/batches/{batch_id}/progress"
        with requests.get(url, stream=True) as response:
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        yield json.loads(decoded[6:])

    def get_batch_status(self, batch_id: str) -> Dict[str, Any]:
        """Get current status of a batch (One-time snapshot)."""
        response = requests.get(f"{self.base_url}/batches/{batch_id}")
        response.raise_for_status()
        return response.json()


    def terminate_batch(self, batch_id: str) -> Dict[str, Any]:
        """Terminate a batch upload and clean up incomplete files."""
        response = requests.post(f"{self.base_url}/batches/{batch_id}/terminate")
        response.raise_for_status()
        return response.json()

    def cleanup_daily(self) -> Dict[str, Any]:
        """Trigger daily cleanup of old files."""
        response = requests.delete(f"{self.base_url}/documents/cleanup/daily")
        response.raise_for_status()
        return response.json()

    def burn_document(self, document_id: str) -> None:
        """Completely remove a document and its artifacts."""
        requests.delete(f"{self.base_url}/documents/{document_id}/burn").raise_for_status()

    # --- Chat & Query ---

    def chat(self, message: str, chat_id: str = None, category_ids: List[str] = None) -> Dict[str, Any]:
        """Send a message to the chat endpoint."""
        # Note: The API usually expects form-data for chat if images are involved, 
        # but for text-only, we can send form fields.
        data = {
            "message": message,
        }
        if chat_id:
            data["chat_id"] = chat_id
        if category_ids:
            data["category_ids"] = json.dumps(category_ids) # API expects JSON string in form field

        response = requests.post(f"{self.base_url}/chat", data=data)
        response.raise_for_status()
        return response.json()

    def query(self, query_text: str, category_ids: List[str] = None) -> Dict[str, Any]:
        """Perform a standard RAG query."""
        payload = QueryRequest(query=query_text, category_ids=category_ids).model_dump()
        response = requests.post(f"{self.base_url}/query", json=payload)
        response.raise_for_status()
        return response.json()

# --- Example Usage ---
if __name__ == "__main__":
    client = RAGClient()
    
    # 1. Create Category
    try:
        cat = client.create_category("finance_2024", "Financial Reports 2024")
        print(f"Created category: {cat.category_id}")
        
        # 2. Upload (Mocking file path - ensure valid path exists)
        # docs = client.upload_documents(cat.category_id, ["report.pdf"])
        # print(f"Uploaded: {docs[0].filename} Batch: {docs[0].batch_id}")
        
        # 3. Chat
        # resp = client.chat("What is the net profit?")
        # print(f"Answer: {resp['answer']}")
        
    except Exception as e:
        print(f"Error: {e}")
