# PetroRAG - Main Backend Application API

A comprehensive RAG (Retrieval-Augmented Generation) system for processing PDF documents with tables and figures, using LlamaIndex for indexing, Qdrant for vector search, MongoDB for metadata storage, and GROQ API with Qwen models.

## Features
- **PDF Processing**: Extract text, tables, and images from PDFs.
- **Section-based Chunking**: Intelligent chunking based on document TOC with 20% overlap.
- **Table Extraction**: Structured table extraction using pdfplumber.
- **Image Extraction**: Figure and image extraction with caption detection.
- **Multimodal RAG**: Query both text and image content.
- **Categories & Batches**: Robust file and category management and batch uploading capabilities.
- **Streaming Chat**: Server-Sent Events (SSE) based real-time chat with LLM.

---

## 🚀 API Endpoints Signature Guide

The main application exposes the following RESTful API endpoints under `/api`. This guide serves as a reference for integrating external services with PetroRAG.

### 1. Categories (`/api/categories`)
Manage document categories. Categories help separate and organize embeddings and context for precise querying.

| Method | Endpoint | Description | Content-Type | Payload/Query |
|--------|----------|-------------|--------------|---------------|
| `POST` | `/api/categories` | Create a new category | `application/json` | Body: `{"name": "string", "description": "string"}` |
| `GET` | `/api/categories` | List all categories | - | - |
| `GET` | `/api/categories/{category_id}` | Get specific category metadata | - | - |
| `PUT` | `/api/categories/{category_id}` | Update category | `application/json` | Body: `{"name": "string", "description": "string"}` |
| `DELETE`| `/api/categories/{category_id}` | Delete a category | - | - |
| `GET` | `/api/categories/{category_id}/documents` | List documents in category | - | - |

### 2. Documents (`/api/documents`)
Handle PDF uploads, daily (temporary) documents, deletions, and downloads.

| Method | Endpoint | Description | Content-Type | Payload/Query |
|--------|----------|-------------|--------------|---------------|
| `POST` | `/api/documents/upload/{category_id}` | Upload multiple PDFs | `multipart/form-data` | Form: `files` (Array of files). Max 50 files. Returns `batch_id`. |
| `POST` | `/api/documents/upload/daily/{category_id}` | Upload temp PDFs (24h expiry) | `multipart/form-data` | Form: `files` (Array of files). Max 50 files. Returns `batch_id`. |
| `DELETE`| `/api/documents/cleanup/daily` | Delete all >24h old documents | - | - |
| `GET` | `/api/documents` | List all documents | - | Query: `?category_id=optional_id` |
| `GET` | `/api/documents/{document_id}` | Get document metadata | - | - |
| `DELETE`| `/api/documents/{document_id}` | Delete a document gently | - | - |
| `DELETE`| `/api/documents/{document_id}/burn` | Hard-delete doc & all artifacts | - | - |
| `GET` | `/api/documents/{document_id}/download`| Download PDF | - | Returns `application/pdf` |

### 3. Batches (`/api/batches`)
Track multi-file upload processing in real-time.

| Method | Endpoint | Description | Content-Type | Payload/Query |
|--------|----------|-------------|--------------|---------------|
| `GET` | `/api/batches/{batch_id}` | One-time status of batch | - | Returns JSON dict of files status |
| `GET` | `/api/batches/{batch_id}/progress` | Real-time batch progress stream| - | Returns `text/event-stream` (SSE) |
| `POST` | `/api/batches/{batch_id}/terminate` | Terminate in-progress batch | - | Halts remaining processing |

### 4. Chat (`/api/chat`)
Stateful conversational endpoints supporting Multimodal RAG context, history, and real-time streaming.

| Method | Endpoint | Description | Content-Type | Payload/Query |
|--------|----------|-------------|--------------|---------------|
| `POST` | `/api/chat` | Send a chat message | `multipart/form-data` | Form: `message` (str, req), `username` (str, req), `chat_id` (str, opt), `category_ids` (JSON str, opt), `document_ids` (JSON str, opt), `top_k` (int, opt), `images` (List of files, opt). |
| `POST` | `/api/chat/stream` | Stream chat message (SSE) | `multipart/form-data` | Form: Same as `/api/chat`. Returns `text/event-stream`. |
| `GET` | `/api/chat` | List chat sessions | - | Query: `?username=req&limit=50` |
| `GET` | `/api/chat/{chat_id}` | Get specific chat session | - | Query: `?username=req` |
| `DELETE`| `/api/chat/{chat_id}` | Delete a chat session | - | Query: `?username=req` |

### 5. Query (`/api/query`)
Stateless raw query operations (RAG without persistent chat state) and pure image-search.

| Method | Endpoint | Description | Content-Type | Payload/Query |
|--------|----------|-------------|--------------|---------------|
| `POST` | `/api/query` | RAG query | `application/json` | Body: `QueryRequest` (query, top_k, categories, etc) |
| `POST` | `/api/query/image-search` | Multimodal Image Search | `application/json` | Body: `ImageSearchRequest` (text or image query) |

---

## 🛠 Usage Example

### Uploading a batch of documents and tracking progress:
```bash
# 1. Upload files
curl -X POST "http://localhost:8080/api/documents/upload/<category_id>" \
  -H "Content-Type: multipart/form-data" \
  -F "files=@document1.pdf" -F "files=@document2.pdf"
# Returns: [{"document_id": "...", "batch_id": "abc-123", ...}]

# 2. Track Progress (Server-Sent Events)
curl -N "http://localhost:8080/api/batches/abc-123/progress"
```

### Multimodal Streaming Chat:
```bash
curl -N -X POST "http://localhost:8080/api/chat/stream" \
  -F "username=johndoe" \
  -F "message=Explain the process in this diagram" \
  -F "category_ids=[\"cat_id_a\"]" \
  -F "images=@diagram.png"
```

---

## Architecture & Storage
- **LlamaIndex + Qdrant**: High-performance semantic search with Vector embeddings.
- **MongoDB**: Central metadata for documents, chunks, chat histories, tables, and images.
- **Local File System**: Upload directory (`uploads/`) and extracted artifacts (`extracted_images/`).

## Setup and Running
1. `pip install -r requirements.txt`
2. `cp .env.example .env` (Configure MONGODB_URI, GROQ_API_KEY)
3. `uvicorn app.main:app --host 0.0.0.0 --port 8080`
