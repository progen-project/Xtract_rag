# PetroRAG — Main API Documentation

> **Version:** 3.0.0 | **Base URL:** `http://localhost:8080` | **Docs:** `/docs`

PetroRAG is a Multimodal RAG (Retrieval-Augmented Generation) pipeline for petroleum engineering documents. It supports PDF ingestion, table/image extraction, semantic search, and AI-powered chat with citation support.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Setup & Configuration](#setup--configuration)
3. [Global Response Conventions](#global-response-conventions)
4. [Categories API](#categories-api)
5. [Documents API](#documents-api)
6. [Batches API](#batches-api)
7. [Query API](#query-api)
8. [Chat API](#chat-api)
9. [Health & Root](#health--root)

---

## Architecture Overview

```
Client → NGINX (8002) → Client Proxy (8001) → Main API (8080)
                                                    ├── MongoDB  (documents, chunks, chats)
                                                    ├── Qdrant   (vector search)
                                                    └── Redis    (status streaming)
```

**Core Services:**
- **Docling** — PDF parsing, table extraction, figure detection
- **LlamaIndex + Qdrant** — Hybrid dense+sparse vector search (RRF fusion)
- **GROQ API** — LLM text generation (Qwen) and vision analysis (Llama-4)
- **BGE-VL-base** — Multimodal image embeddings
- **Cross-Encoder** — Re-ranking retrieved results

---

## Setup & Configuration

### Environment Variables (`.env`)

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=petro_rag

# Collections
DOCUMENTS_COLLECTION=rag_documents
CATEGORIES_COLLECTION=rag_categories
CHUNKS_COLLECTION=rag_chunks
IMAGES_COLLECTION=rag_images
TABLES_COLLECTION=rag_tables
CHATS_COLLECTION=rag_chats

# Redis
REDIS_URL=redis://localhost:6379/0

# GROQ
GROQ_API_KEY=gsk_...
QWEN_TEXT_MODEL=qwen/qwen3-32b
GROQ_VISION_MODEL=meta-llama/llama-4-maverick-17b-128e-instruct
LLM_TEMPERATURE=0.0
LLM_MAX_TOKENS=5000

# Qdrant
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=petro_rag_vectors

# Embeddings & Search
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
USE_RERANKER=true
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_TOP_K=10
TOP_K=60
SIMILARITY_THRESHOLD=0.0

# LLM Guard
GUARD_THRESHOLD=0.1

# Storage
UPLOAD_DIR=./uploads
IMAGES_DIR=./extracted_images
MAX_IMAGE_WIDTH=800
CHAT_IMAGES_DIR=./chat_images
CHAT_CONTEXT_WINDOW=10
MAX_CHAT_IMAGES=10

# Chunking
CHUNK_OVERLAP_PERCENTAGE=0.20
MIN_CHUNK_SIZE=100
MAX_CHUNK_SIZE=2000
```

### Running

```bash
# Docker (recommended)
docker-compose up --build

# Local
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

---

## Global Response Conventions

### Content Types
- `application/json` — All JSON endpoints
- `multipart/form-data` — File upload endpoints
- `text/event-stream` — SSE streaming endpoints
- `application/pdf` — File download endpoints

### Common Error Responses

```json
// 400 Bad Request — Validation failure
{
  "detail": "Maximum 10 images allowed"
}

// 404 Not Found — Resource missing
{
  "detail": "Category not found: cat_abc123"
}

// 404 Not Found — Document
{
  "detail": "Document not found: doc_abc123"
}

// 404 Not Found — Chat
{
  "detail": "Chat not found: chat_abc123"
}

// 422 Unprocessable Entity — Schema validation (FastAPI)
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}

// 500 Internal Server Error
{
  "detail": "Internal server error"
}
```

---

## Categories API

**Base path:** `/api/categories`  
Categories are folders that organize documents into logical groups.

---

### `POST /api/categories` — Create Category

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "name": "Well Control Documents",
  "description": "All documents related to well control procedures"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ✅ | Category display name |
| `description` | string | ❌ | Optional description |

**Success Response — `201 Created`:**
```json
{
  "category_id": "cat_3f9a1b2c4d5e",
  "name": "Well Control Documents",
  "description": "All documents related to well control procedures",
  "document_count": 0,
  "created_at": "2024-01-15T10:30:00.000Z"
}
```

**Error Responses:**
```json
// 422 — Missing required field
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

### `GET /api/categories` — List All Categories

**Request:** No body or parameters.

**Success Response — `200 OK`:**
```json
[
  {
    "category_id": "cat_3f9a1b2c4d5e",
    "name": "Well Control Documents",
    "description": "All documents related to well control procedures",
    "document_count": 12,
    "created_at": "2024-01-15T10:30:00.000Z"
  },
  {
    "category_id": "cat_7e8f9a0b1c2d",
    "name": "Drilling Manuals",
    "description": null,
    "document_count": 5,
    "created_at": "2024-01-16T08:00:00.000Z"
  }
]
```

---

### `GET /api/categories/{category_id}` — Get Single Category

**Path Parameter:** `category_id` (string)

**Success Response — `200 OK`:**
```json
{
  "category_id": "cat_3f9a1b2c4d5e",
  "name": "Well Control Documents",
  "description": "All documents related to well control procedures",
  "document_count": 12,
  "created_at": "2024-01-15T10:30:00.000Z"
}
```

**Error Responses:**
```json
// 404 — Category not found
{
  "detail": "Category not found: cat_3f9a1b2c4d5e"
}
```

---

### `PUT /api/categories/{category_id}` — Update Category

**Path Parameter:** `category_id` (string)  
**Content-Type:** `application/json`

**Request Body:**
```json
{
  "name": "Updated Category Name",
  "description": "Updated description text"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ❌ | New category name (omit to keep current) |
| `description` | string | ❌ | New description (omit to keep current) |

**Success Response — `200 OK`:**
```json
{
  "category_id": "cat_3f9a1b2c4d5e",
  "name": "Updated Category Name",
  "description": "Updated description text",
  "document_count": 12,
  "created_at": "2024-01-15T10:30:00.000Z"
}
```

**Error Responses:**
```json
// 404 — Category not found
{
  "detail": "Category not found: cat_3f9a1b2c4d5e"
}
```

---

### `DELETE /api/categories/{category_id}` — Delete Category

**Path Parameter:** `category_id` (string)

**Success Response — `200 OK`:**
```json
{
  "message": "Category cat_3f9a1b2c4d5e deleted"
}
```

**Error Responses:**
```json
// 404 — Category not found
{
  "detail": "Category not found: cat_3f9a1b2c4d5e"
}
```

---

### `GET /api/categories/{category_id}/documents` — List Category Documents

**Path Parameter:** `category_id` (string)

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "well_control_procedures.pdf",
    "file_path": "./uploads/WellControl/abc123_well_control_procedures.pdf",
    "file_size": 2048576,
    "page_count": 45,
    "upload_date": "2024-01-15T11:00:00.000Z",
    "status": "completed",
    "batch_id": "batch_xyz789",
    "is_daily": false,
    "toc": [
      {
        "title": "Introduction",
        "level": 1,
        "page_number": 1,
        "page_end": 5
      }
    ],
    "processing_errors": []
  }
]
```

---

## Documents API

**Base path:** `/api/documents`  
Handles PDF upload, processing (parse → chunk → embed → index), and retrieval.

---

### `POST /api/documents/upload/{category_id}` — Upload Documents (Permanent)

**Path Parameter:** `category_id` (string)  
**Content-Type:** `multipart/form-data`  
**Max files per request:** 50

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | `UploadFile[]` | ✅ | PDF files to upload |

**Example cURL:**
```bash
curl -X POST "http://localhost:8080/api/documents/upload/cat_3f9a1b2c4d5e" \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf"
```

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "document1.pdf",
    "message": "Document uploaded. Processing started.",
    "status": "pending",
    "batch_id": "a3f8e9d2c1b047f6"
  },
  {
    "document_id": "doc_2b3c4d5e6f7a",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "document2.pdf",
    "message": "Document uploaded. Processing started.",
    "status": "pending",
    "batch_id": "a3f8e9d2c1b047f6"
  }
]
```

> **Note:** Processing is asynchronous. Use the `batch_id` to track progress via `/api/batches/{batch_id}/progress`.

**Error Responses:**
```json
// 400 — Too many files
{
  "detail": "Maximum 50 files allowed per batch"
}

// 400 — No valid PDFs
{
  "detail": "No valid PDF files found in batch"
}

// 404 — Category not found
{
  "detail": "Category not found: cat_3f9a1b2c4d5e"
}
```

---

### `POST /api/documents/upload/daily/{category_id}` — Upload Temporary Documents

Same as permanent upload but documents are **automatically deleted after 24 hours**.

**Path Parameter:** `category_id` (string)  
**Content-Type:** `multipart/form-data`

**Form Fields:** Same as permanent upload (`files`)

**Success Response — `200 OK`:** Same structure as permanent upload, with `"status": "pending"`.

**Error Responses:** Same as permanent upload.

---

### `GET /api/documents` — List All Documents

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category_id` | string | ❌ | Filter documents by category |

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "well_control_procedures.pdf",
    "file_path": "./uploads/WellControl/abc123_well_control_procedures.pdf",
    "file_size": 2048576,
    "page_count": 45,
    "upload_date": "2024-01-15T11:00:00.000Z",
    "status": "completed",
    "batch_id": "a3f8e9d2c1b047f6",
    "is_daily": false,
    "toc": [
      {
        "title": "Chapter 1: Introduction",
        "level": 1,
        "page_number": 1,
        "page_end": 8
      },
      {
        "title": "1.1 Scope",
        "level": 2,
        "page_number": 2,
        "page_end": 3
      }
    ],
    "processing_errors": []
  }
]
```

**Document Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Uploaded, waiting to process |
| `processing` | Currently being processed |
| `completed` | Fully indexed and searchable |
| `failed` | Processing failed (see `processing_errors`) |

---

### `GET /api/documents/{document_id}` — Get Single Document

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:** Full `DocumentMetadata` object (same as above).

**Error Responses:**
```json
// 404 — Document not found
{
  "detail": "Document not found: doc_1a2b3c4d5e6f"
}
```

---

### `DELETE /api/documents/{document_id}` — Delete Document

Removes document from MongoDB, Qdrant (all collections), and deletes source PDF from disk.

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
```json
{
  "message": "Document doc_1a2b3c4d5e6f deleted"
}
```

**Error Responses:**
```json
// 404 — Document not found
{
  "detail": "Document not found: doc_1a2b3c4d5e6f"
}
```

---

### `DELETE /api/documents/{document_id}/burn` — Burn Document

Complete removal of a document and all its artifacts (vectors, chunks, images, tables, source file).

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
```json
{
  "message": "Document doc_1a2b3c4d5e6f burned successfully"
}
```

**Error Responses:**
```json
// 404 — Document not found
{
  "detail": "Document not found: doc_1a2b3c4d5e6f"
}
```

---

### `GET /api/documents/{document_id}/download` — Download PDF

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="original_filename.pdf"`
- Body: Raw PDF binary stream

**Error Responses:**
```json
// 404 — Document not found
{
  "detail": "Document not found"
}

// 404 — File missing from disk
{
  "detail": "File not found on server"
}
```

---

### `DELETE /api/documents/cleanup/daily` — Cleanup Daily Documents

Deletes all documents where `is_daily=true` and `upload_date < now - 24h`.

**Request:** No body.

**Success Response — `200 OK`:**
```json
{
  "deleted_documents": 7,
  "failed_deletions": 0,
  "cutoff_time": "2024-01-14T11:00:00.000Z"
}
```

---

## Batches API

**Base path:** `/api/batches`  
A batch is created for each multi-file upload. Use it to track processing progress.

---

### `GET /api/batches/{batch_id}` — Get Batch Status Snapshot

**Path Parameter:** `batch_id` (string)

**Success Response — `200 OK`:**
```json
{
  "batch_id": "a3f8e9d2c1b047f6",
  "files": {
    "document1.pdf": {
      "status": "completed",
      "detail": "Processing completed successfully.",
      "timestamp": "2024-01-15T11:05:00.000Z"
    },
    "document2.pdf": {
      "status": "indexing",
      "detail": "Indexing 42 chunks...",
      "timestamp": "2024-01-15T11:04:45.000Z"
    }
  },
  "timestamp": "2024-01-15T11:05:01.000Z"
}
```

**Processing Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Waiting to start |
| `processing` | General processing started |
| `parsing` | Parsing PDF with Docling |
| `extracting_images` | Extracting figures from PDF |
| `chunking` | Splitting sections into chunks |
| `indexing` | Indexing text chunks in Qdrant |
| `analyzing_images` | Running vision model on images |
| `indexing_images` | Indexing image embeddings |
| `indexing_tables` | Indexing tables in Qdrant |
| `completed` | Successfully finished |
| `failed` | Processing failed |

**Error Responses:**
```json
// 404 — Batch not found
{
  "detail": "Batch not found"
}
```

---

### `GET /api/batches/{batch_id}/progress` — Stream Batch Progress (SSE)

Real-time Server-Sent Events stream for processing progress.

**Path Parameter:** `batch_id` (string)  
**Response Content-Type:** `text/event-stream`

**SSE Event Format:**

```
data: {"type": "initial_state", "batch_id": "a3f8e9...", "files": {...}}

data: {"batch_id": "a3f8e9...", "filename": "doc1.pdf", "status": "parsing", "detail": "Parsing PDF document...", "timestamp": "2024-01-15T11:04:30.000Z"}

data: {"batch_id": "a3f8e9...", "filename": "doc1.pdf", "status": "completed", "detail": "Processing completed successfully.", "timestamp": "2024-01-15T11:05:00.000Z"}

data: {"type": "heartbeat", "batch_id": "a3f8e9...", "timestamp": "2024-01-15T11:05:15.000Z"}
```

**Event Types:**

| Type | Description |
|------|-------------|
| `initial_state` | Full snapshot of all files on connection |
| File update (no type field) | Progress update for a specific file |
| `heartbeat` | Keep-alive ping every 15 seconds |

---

### `POST /api/batches/{batch_id}/terminate` — Terminate Batch

Stops processing and deletes all non-completed documents in the batch. Completed documents are preserved.

**Path Parameter:** `batch_id` (string)

**Success Response — `200 OK`:**
```json
{
  "batch_id": "a3f8e9d2c1b047f6",
  "total_documents": 5,
  "kept_completed": 2,
  "deleted_incomplete": 3
}
```

---

## Query API

**Base path:** `/api/query`  
Stateless RAG query endpoint — no conversation history.

---

### `POST /api/query` — RAG Query

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query": "What are the procedures for well control during a kick?",
  "category_ids": ["cat_3f9a1b2c4d5e"],
  "document_ids": null,
  "top_k": 60,
  "include_images": true,
  "include_tables": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | — | Natural language question |
| `category_ids` | string[] | ❌ | `null` | Restrict search to specific categories |
| `document_ids` | string[] | ❌ | `null` | Restrict search to specific documents |
| `top_k` | integer | ❌ | `60` | Initial candidates to retrieve (1–100) |
| `include_images` | boolean | ❌ | `true` | Enrich results with images |
| `include_tables` | boolean | ❌ | `true` | Enrich results with tables |

**Success Response — `200 OK`:**
```json
{
  "query": "What are the procedures for well control during a kick?",
  "answer": "During a kick event, the driller should immediately shut in the well using the BOP [Source 1, Page 12–13]. The wellbore pressure must be monitored continuously to prevent blowout [Source 2, Page 7].\n\n## Immediate Actions\n- Shut in the well\n- Record shut-in drill pipe pressure (SIDPP) and shut-in casing pressure (SICP) [Source 1, Page 14]\n\n## Kill Methods\nThe **Driller's Method** is preferred for live well control [Source 3, Page 21–22].",
  "retrieved_chunks": [
    {
      "chunk_id": "doc_1a2b3c4d5e6f_chunk_3",
      "content": "Section 3.2: Well Control Procedures. Upon detecting a kick indicator...",
      "score": 0.912,
      "section_title": "Well Control Procedures",
      "page_start": 12,
      "page_end": 14,
      "image_ids": ["doc_1a2b3c4d5e6f_p13_img0"],
      "images": [],
      "tables": []
    }
  ],
  "sources": ["doc_1a2b3c4d5e6f", "doc_2b3c4d5e6f7a"],
  "inline_citations": [
    {
      "source_number": 1,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "Well Control Procedures",
      "pages": [12, 13]
    }
  ]
}
```

> **LLM Guard:** If the query is unrelated to petroleum engineering (score below `GUARD_THRESHOLD`), the system bypasses RAG and uses general LLM knowledge directly, returning an empty `retrieved_chunks` and `sources`.

---

### `POST /api/query/image-search` — Image Semantic Search

Search document images by text description or by providing a reference image.

**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query_text": "P&ID diagram showing separator",
  "query_image_base64": null,
  "category_ids": ["cat_3f9a1b2c4d5e"],
  "document_ids": null,
  "top_k": 60
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query_text` | string | ❌* | Text description to search images by |
| `query_image_base64` | string | ❌* | Base64-encoded image to search by similarity |
| `category_ids` | string[] | ❌ | Filter by categories |
| `document_ids` | string[] | ❌ | Filter by documents |
| `top_k` | integer | ❌ | Max results (default from config) |

> ⚠️ At least one of `query_text` or `query_image_base64` is required.

**Success Response — `200 OK`:**
```json
{
  "query_text": "P&ID diagram showing separator",
  "has_query_image": false,
  "results": [
    {
      "image_id": "doc_1a2b3c4d5e6f_p8_img0",
      "document_id": "doc_1a2b3c4d5e6f",
      "page_number": 8,
      "section_title": "Process Flow Diagrams",
      "caption": "Figure 3: Three-phase separator P&ID",
      "image_path": "./extracted_images/cat_3f9a1b2c4d5e/doc_1a2b3c4d5e6f/p8_img0.png",
      "score": 0.876
    }
  ],
  "count": 1
}
```

**Error Responses:**
```json
// 400 — Neither query_text nor query_image_base64 provided
{
  "detail": "At least one of 'query_text' or 'query_image_base64' must be provided"
}
```

---

## Chat API

**Base path:** `/api/chat`  
Stateful conversational RAG with context window, inline citations, and multimodal support.

**Key behaviors:**
- Chat sessions persist in MongoDB
- Last `CHAT_CONTEXT_WINDOW` (default: 10) messages used as history context
- LLM Guard filters off-topic messages
- Sources filtered to only cited documents
- Images embedded using vision model when available

---

### `POST /api/chat` — Send Message (Synchronous)

**Content-Type:** `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `message` | string | ✅ | — | User's text message |
| `username` | string | ✅ | — | User identifier |
| `chat_id` | string | ❌ | `null` | Existing session ID (creates new if omitted) |
| `category_ids` | string (JSON) | ❌ | `null` | JSON array e.g. `'["cat_abc"]'` or CSV |
| `document_ids` | string (JSON) | ❌ | `null` | JSON array e.g. `'["doc_abc"]'` or CSV |
| `top_k` | integer | ❌ | `60` | Initial retrieval candidates |
| `images` | `UploadFile[]` | ❌ | `[]` | Up to 10 images (sent to vision model) |

**Example cURL:**
```bash
curl -X POST "http://localhost:8080/api/chat" \
  -F "message=What causes a blowout?" \
  -F "username=engineer01" \
  -F 'category_ids=["cat_3f9a1b2c4d5e"]'
```

**Success Response — `200 OK`:**
```json
{
  "chat_id": "chat_a1b2c3d4e5f6",
  "username": "engineer01",
  "message_id": "msg_1f2e3d4c5b6a",
  "answer": "A blowout occurs when formation pressure exceeds wellbore pressure [well_control_manual.pdf, Page 5–6]. The primary causes include:\n\n- Insufficient mud weight [well_control_manual.pdf, Page 7]\n- Failure of BOP equipment [drilling_handbook.pdf, Page 23]\n- Improper well control procedures [well_control_manual.pdf, Page 12–13]",
  "sources": {
    "doc_1a2b3c4d5e6f": {
      "filename": "well_control_manual.pdf",
      "category_id": "cat_3f9a1b2c4d5e",
      "category_name": "Well Control Documents",
      "pages": [5, 6, 7, 12, 13],
      "score": 0.923,
      "contains": ["text", "table"]
    },
    "doc_2b3c4d5e6f7a": {
      "filename": "drilling_handbook.pdf",
      "category_id": "cat_3f9a1b2c4d5e",
      "category_name": "Well Control Documents",
      "pages": [23],
      "score": 0.845,
      "contains": ["text"]
    }
  },
  "inline_citations": [
    {
      "source_number": 1,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "Causes of Blowout",
      "pages": [5, 6]
    },
    {
      "source_number": 2,
      "document_id": "doc_2b3c4d5e6f7a",
      "filename": "drilling_handbook.pdf",
      "section_title": "BOP Equipment",
      "pages": [23]
    }
  ],
  "image_results": [
    {
      "image_id": "doc_1a2b3c4d5e6f_p6_img0",
      "document_id": "doc_1a2b3c4d5e6f",
      "page_number": 6,
      "section_title": "Pressure Control",
      "caption": "Figure 2: Wellbore pressure diagram",
      "image_path": "./extracted_images/cat_3f9a1b2c4d5e/doc_1a2b3c4d5e6f/p6_img0.png",
      "score": 0.0
    }
  ]
}
```

**Response Field Descriptions:**

| Field | Description |
|-------|-------------|
| `chat_id` | Session ID (save for follow-up messages) |
| `answer` | AI-generated answer with inline citations replaced as `[filename.pdf, Page X–Y]` |
| `sources` | Map of `document_id → metadata`, filtered to only cited documents |
| `inline_citations` | Structured citation objects extracted from the answer |
| `image_results` | Images retrieved during search (paths for frontend display) |

**Error Responses:**
```json
// 400 — Too many images
{
  "detail": "Maximum 10 images allowed"
}

// 404 — Chat session not found (when chat_id provided but doesn't exist)
{
  "detail": "Chat not found: chat_a1b2c3d4e5f6"
}
```

---

### `POST /api/chat/stream` — Send Message (Server-Sent Events)

Same parameters as synchronous chat but streams the response token-by-token.

**Content-Type:** `multipart/form-data`  
**Response Content-Type:** `text/event-stream`

**Form Fields:** Same as `POST /api/chat`

**SSE Stream Events:**

```
// Token events (one per word/token):
data: {"token": "A "}
data: {"token": "blowout "}
data: {"token": "occurs "}

// Final event with complete metadata:
data: {
  "done": true,
  "chat_id": "chat_a1b2c3d4e5f6",
  "username": "engineer01",
  "message_id": "msg_1f2e3d4c5b6a",
  "answer": "A blowout occurs when formation pressure...",
  "sources": { ... },
  "inline_citations": [ ... ],
  "image_results": [ ... ]
}
```

**Error Event:**
```
data: {"error": "LLM generation failed: rate limit exceeded"}
```

> **Important:** The full `answer` in the final `done` event has citations enriched (replaced with filenames). Accumulate tokens for real-time display, use the `done` event's `answer` as the canonical final text.

---

### `GET /api/chat` — List Chat Sessions

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `username` | string | ✅ | — | User identifier |
| `limit` | integer | ❌ | `50` | Max sessions to return |

**Success Response — `200 OK`:**
```json
[
  {
    "chat_id": "chat_a1b2c3d4e5f6",
    "username": "engineer01",
    "category_ids": ["cat_3f9a1b2c4d5e"],
    "document_ids": null,
    "messages": [
      {
        "message_id": "msg_aabbccddee11",
        "role": "user",
        "content": "What causes a blowout?",
        "image_paths": [],
        "sources": null,
        "timestamp": "2024-01-15T12:00:00.000Z"
      },
      {
        "message_id": "msg_1f2e3d4c5b6a",
        "role": "assistant",
        "content": "A blowout occurs when...",
        "image_paths": ["./extracted_images/.../p6_img0.png"],
        "sources": { "doc_1a2b3c4d5e6f": { ... } },
        "timestamp": "2024-01-15T12:00:05.000Z"
      }
    ],
    "created_at": "2024-01-15T12:00:00.000Z",
    "updated_at": "2024-01-15T12:00:05.000Z"
  }
]
```

---

### `GET /api/chat/{chat_id}` — Get Chat Session

**Path Parameter:** `chat_id` (string)  
**Query Parameter:** `username` (string, required)

**Success Response — `200 OK`:** Same as single item in list above.

**Error Responses:**
```json
// 404 — Chat not found or username mismatch
{
  "detail": "Chat not found: chat_a1b2c3d4e5f6"
}
```

---

### `DELETE /api/chat/{chat_id}` — Delete Chat Session

Deletes the session, messages, and all associated uploaded images from disk.

**Path Parameter:** `chat_id` (string)  
**Query Parameter:** `username` (string, required)

**Success Response — `200 OK`:**
```json
{
  "message": "Chat chat_a1b2c3d4e5f6 deleted"
}
```

**Error Responses:**
```json
// 404 — Chat not found
{
  "detail": "Chat not found: chat_a1b2c3d4e5f6"
}
```

---

## Health & Root

### `GET /` — Root

**Success Response — `200 OK`:**
```json
{
  "name": "PetroRAG API",
  "version": "3.0.0",
  "description": "Multimodal RAG Pipeline with Clean Architecture",
  "endpoints": {
    "categories": "/api/categories",
    "documents": "/api/documents",
    "query": "/api/query",
    "chat": "/api/chat",
    "docs": "/docs"
  }
}
```

---

### `GET /health` — Health Check

**Success Response — `200 OK`:**
```json
{
  "status": "healthy",
  "services": {
    "mongodb": "connected",
    "llm": "configured",
    "indexer": "initialized"
  }
}
```

**Degraded Response (partial services):**
```json
{
  "status": "healthy",
  "services": {
    "mongodb": "disconnected",
    "llm": "not configured",
    "indexer": "not initialized"
  }
}
```

---

## Static File Access

Extracted images and chat images are served as static files:

```
GET /extracted_images/{category_id}/{document_id}/{filename}
GET /chat_images/{chat_id}/{filename}
```

Example:
```
GET /extracted_images/cat_3f9a1b2c4d5e/doc_1a2b3c4d5e6f/p8_img0.png
```

---

## Data Models Reference

### DocumentMetadata
```json
{
  "document_id": "string",
  "category_id": "string",
  "filename": "string",
  "file_path": "string",
  "file_size": "integer (bytes)",
  "page_count": "integer",
  "upload_date": "datetime (ISO 8601)",
  "status": "pending | processing | completed | failed",
  "batch_id": "string | null",
  "is_daily": "boolean",
  "toc": [
    {
      "title": "string",
      "level": "integer",
      "page_number": "integer",
      "page_end": "integer | null"
    }
  ],
  "processing_errors": ["string"]
}
```

### RetrievedChunk
```json
{
  "chunk_id": "string",
  "content": "string",
  "score": "float (0.0–1.0)",
  "section_title": "string",
  "page_start": "integer",
  "page_end": "integer",
  "image_ids": ["string"],
  "images": ["ExtractedImage"],
  "tables": ["ExtractedTable"]
}
```

### InlineCitation
```json
{
  "source_number": "integer",
  "document_id": "string",
  "filename": "string",
  "section_title": "string",
  "pages": ["integer"]
}
```

### ChatMessage
```json
{
  "message_id": "string",
  "role": "user | assistant",
  "content": "string",
  "image_paths": ["string"],
  "sources": "dict | null",
  "timestamp": "datetime (ISO 8601)"
}
```
