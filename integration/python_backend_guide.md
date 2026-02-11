# Backend Integration Guide (Python)

This guide provides Python schemas and usage examples for the main backend endpoints.
It is intended for backend developers integrating with the RAG system.

## 1. Category Management

### Schemas
```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class CategoryCreate(BaseModel):
    """Request to create a category."""
    name: str = Field(..., description="Unique name for the category")
    description: Optional[str] = Field(None, description="Optional description")

class CategoryResponse(BaseModel):
    """Response validation schema."""
    category_id: str
    name: str
    description: Optional[str]
    document_count: int
    created_at: datetime
```

### Usage (requests)
```python
import requests

BASE_URL = "http://localhost:8000/api/categories"

def create_category(name: str, desc: str = None):
    payload = {"name": name, "description": desc}
    response = requests.post(BASE_URL, json=payload)
    response.raise_for_status()
    return response.json()

def delete_category(category_id: str):
    response = requests.delete(f"{BASE_URL}/{category_id}")
    response.raise_for_status()
    print(f"Category {category_id} deleted")
```

---

## 2. Document Management

### Schemas
```python
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentUploadResponse(BaseModel):
    document_id: str
    category_id: str
    filename: str
    status: DocumentStatus
    batch_id: Optional[str]
```

### Usage (requests)
```python
import requests

DOCS_URL = "http://localhost:8000/api/documents"

def upload_documents(category_id: str, file_paths: List[str]):
    url = f"{DOCS_URL}/upload/{category_id}"
    files = [('files', open(path, 'rb')) for path in file_paths]
    
    # Upload
    response = requests.post(url, files=files)
    response.raise_for_status()
    result = response.json()
    
    # Get Batch ID for tracking
    if result:
        batch_id = result[0].get('batch_id')
        print(f"Upload started. Batch ID: {batch_id}")
    
    return result

def delete_document(document_id: str):
    response = requests.delete(f"{DOCS_URL}/{document_id}")
    response.raise_for_status()

def listen_to_progress(batch_id: str):
    """Listen to SSE progress stream."""
    url = f"{DOCS_URL}/upload/progress/{batch_id}"
    with requests.get(url, stream=True) as response:
        for line in response.iter_lines():
            if line:
                print(line.decode('utf-8'))
```

---

## 3. Chat & Query Usage

### Schemas
```python
from pydantic import BaseModel, Field
from typing import List, Optional

class ChatRequest(BaseModel):
    message: str
    chat_id: Optional[str] = None
    category_ids: Optional[List[str]] = None
    top_k: int = 5

class QueryRequest(BaseModel):
    query: str
    category_ids: Optional[List[str]] = None
    top_k: int = 5
```

### Usage (requests)
```python
import requests

CHAT_URL = "http://localhost:8000/api/chat"
QUERY_URL = "http://localhost:8000/api/query"

def chat_with_docs(message: str, chat_id: str = None):
    # If sending images, use multipart/form-data. 
    # For text only, form-data is still expected by the endpoint signature.
    data = {
        "message": message,
        "chat_id": chat_id,
        "top_k": 5
    }
    response = requests.post(CHAT_URL, data=data)
    response.raise_for_status()
    return response.json()

def query_rag(question: str):
    payload = {
        "query": question,
        "top_k": 5
    }
    response = requests.post(QUERY_URL, json=payload)
    response.raise_for_status()
    return response.json()
```
