# PetroRAG — Python Client Proxy Documentation

> **Version:** 1.0.0 | **Base URL:** `http://localhost:8001` | **Docs:** `/docs`  
> **Prefix:** All endpoints are under `/client-api`

The Python Client Proxy is a FastAPI gateway that sits between the frontend and the Main API. It adds Nginx-Caching caching, simplified type-safe DTOs, multipart forwarding, SSE proxying, and clean cache invalidation on mutations.

---

## Table of Contents

1. [Architecture & Purpose](#architecture--purpose)
2. [Setup & Configuration](#setup--configuration)
3. [Caching Strategy](#caching-strategy)
4. [Global Response Conventions](#global-response-conventions)
5. [Categories API](#categories-api)
6. [Documents API](#documents-api)
7. [Batches API](#batches-api)
8. [Chat API](#chat-api)
9. [Query API](#query-api)
10. [Data Models Reference](#data-models-reference)

---

## Architecture & Purpose

```
Frontend ──→ NGINX (Caching) (8002) ──→ Client Proxy (8001) ──→ Main API (8080)
                                    
                                 
```

**What the proxy adds:**
- **Cache invalidation** — mutations automatically clear related cache keys
- **DTO enforcement** — strict Pydantic schemas; invalid main API responses raise errors here
- **Multipart forwarding** — reads uploaded file bytes and re-streams them to the main API without saving locally
- **SSE proxying** — transparently forwards Server-Sent Events for batch progress and streaming chat
- **File streaming** — proxies PDF downloads with correct `Content-Disposition` headers

---

## Setup & Configuration

### Environment Variables

```env
RAG_API_URL=http://localhost:8080/api   # Main API base URL
```

### Running

```bash
# Install dependencies
pip install -r python_client_app/requirements.txt

# Start proxy
uvicorn python_client_app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Dependencies (`python_client_app/requirements.txt`)
```
fastapi>=0.111.0
uvicorn>=0.30.1
pydantic>=2.7.4
httpx>=0.27.0
python-multipart>=0.0.9
```

---

## Caching Strategy

| Cache Store | TTL | Scope |
|-------------|-----|-------|
| `category_cache` | 60s | Category lists |
| `document_cache` | 60s | Document lists and metadata |
| `chat_cache` | 60s | Chat session lists and details |

### Cache Key Patterns

| Key | Endpoint cached |
|-----|-----------------|
| `list_categories` | GET /client-api/categories |
| `list_documents:{category_id}` | GET /client-api/categories/{id}/documents |
| `list_documents:all` | GET /client-api/documents (no filter) |
| `list_documents:{category_id}` | GET /client-api/documents?category_id=... |
| `get_document:{document_id}` | GET /client-api/documents/{id} |
| `list_chats:{username}:{limit}` | GET /client-api/chat?username=...&limit=... |
| `get_chat:{username}:{chat_id}` | GET /client-api/chat/{chat_id} |

### Cache Invalidation

| Mutation | Invalidated Keys |
|----------|-----------------|
| Create / Update / Delete category | `list_categories*` |
| Delete category | `list_categories*`, `list_documents*` |
| Upload / Delete / Burn document | `list_documents*`, `get_document:{id}`, `list_categories*` |
| Delete / Burn document | `get_document:{id}`, `list_documents*`, `list_categories*` |
| Send chat message | `list_chats:{username}*`, `get_chat:{username}:{chat_id}` |
| Delete chat | `get_chat:{username}:{chat_id}`, `list_chats:{username}*` |

---

## Global Response Conventions

All endpoints forward HTTP status codes from the main API. Additional proxy-level errors:

```json
// 404 — Resource not found (forwarded from main API)
{
  "detail": "Category not found: cat_abc123"
}

// 422 — Schema validation failure (Pydantic DTO mismatch)
{
  "detail": [
    {
      "loc": ["body", "name"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}

// 500 — Main API unreachable or unexpected error
{
  "detail": "Internal server error"
}
```


---

## Categories API

**Base path:** `/client-api/categories`

---

### `GET /client-api/categories` — List All Categories

**Cache:** `list_categories` (60s TTL)  
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

### `POST /client-api/categories` — Create Category

**Invalidates:** `list_categories*`  
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
| `description` | string | ❌ | Optional description (null if omitted) |

**Success Response — `200 OK`:**
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
// 422 — Missing name field
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

### `PUT /client-api/categories/{category_id}` — Update Category

**Invalidates:** `list_categories*`  
**Path Parameter:** `category_id` (string)  
**Content-Type:** `application/json`

**Request Body:**
```json
{
  "name": "Updated Category Name",
  "description": "Updated description"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | ❌ | New name (omit to keep current) |
| `description` | string | ❌ | New description (omit to keep current) |

**Success Response — `200 OK`:**
```json
{
  "category_id": "cat_3f9a1b2c4d5e",
  "name": "Updated Category Name",
  "description": "Updated description",
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

### `DELETE /client-api/categories/{category_id}` — Delete Category

**Invalidates:** `list_categories*`, `list_documents*`  
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

### `GET /client-api/categories/{category_id}/documents` — List Category Documents

**Cache:** `list_documents:{category_id}` (60s TTL)  
**Path Parameter:** `category_id` (string)

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "well_control_procedures.pdf",
    "status": "completed",
    "upload_date": "2024-01-15T11:00:00.000Z",
    "batch_id": "a3f8e9d2c1b047f6",
    "is_daily": false,
    "error_message": null
  }
]
```

**Error Responses:**
```json
// 404 — Category not found
{
  "detail": "Category not found: cat_3f9a1b2c4d5e"
}
```

---

## Documents API

**Base path:** `/client-api/documents`

---

### `GET /client-api/documents` — List All Documents

**Cache:** `list_documents:all` or `list_documents:{category_id}` (60s TTL)

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `category_id` | string | ❌ | Filter by category |

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "well_control_procedures.pdf",
    "status": "completed",
    "upload_date": "2024-01-15T11:00:00.000Z",
    "batch_id": "a3f8e9d2c1b047f6",
    "is_daily": false,
    "error_message": null
  },
  {
    "document_id": "doc_2b3c4d5e6f7a",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "drilling_manual.pdf",
    "status": "failed",
    "upload_date": "2024-01-15T14:00:00.000Z",
    "batch_id": "b4e9f0a3d2c1",
    "is_daily": false,
    "error_message": "PDF parsing failed: corrupted file"
  }
]
```

**Document Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Uploaded, waiting to process |
| `processing` | Currently being processed |
| `completed` | Fully indexed and searchable |
| `failed` | Processing failed |

---

### `GET /client-api/documents/{document_id}` — Get Single Document

**Cache:** `get_document:{document_id}` (60s TTL)  
**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
```json
{
  "document_id": "doc_1a2b3c4d5e6f",
  "category_id": "cat_3f9a1b2c4d5e",
  "filename": "well_control_procedures.pdf",
  "status": "completed",
  "upload_date": "2024-01-15T11:00:00.000Z",
  "batch_id": "a3f8e9d2c1b047f6",
  "is_daily": false,
  "error_message": null
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

### `POST /client-api/documents/upload/{category_id}` — Upload Documents

**Invalidates:** `list_documents*`, `list_categories*`  
**Path Parameter:** `category_id` (string)  
**Content-Type:** `multipart/form-data`  
**Max files per request:** 50

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `files` | `UploadFile[]` | ✅ | — | PDF files to upload |
| `is_daily` | boolean | ❌ | `false` | If `true`, documents auto-delete after 24h |

**Example cURL:**
```bash
curl -X POST "http://localhost:8001/client-api/documents/upload/cat_3f9a1b2c4d5e" \
  -F "files=@document1.pdf" \
  -F "files=@document2.pdf" \
  -F "is_daily=false"
```

**Success Response — `200 OK`:**
```json
[
  {
    "document_id": "doc_1a2b3c4d5e6f",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "document1.pdf",
    "status": "pending",
    "batch_id": "a3f8e9d2c1b047f6",
    "message": "Document uploaded. Processing started."
  },
  {
    "document_id": "doc_2b3c4d5e6f7a",
    "category_id": "cat_3f9a1b2c4d5e",
    "filename": "document2.pdf",
    "status": "pending",
    "batch_id": "a3f8e9d2c1b047f6",
    "message": "Document uploaded. Processing started."
  }
]
```

> **Note:** Processing is asynchronous. Use `batch_id` to poll `/client-api/batches/{batch_id}` or stream `/client-api/batches/{batch_id}/progress`.

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

### `DELETE /client-api/documents/{document_id}` — Delete Document

**Invalidates:** `get_document:{id}`, `list_documents*`, `list_categories*`  
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

### `DELETE /client-api/documents/{document_id}/burn` — Burn Document

Complete removal including vectors, chunks, images, tables, and source PDF. Extended timeout (300s).

**Invalidates:** `get_document:{id}`, `list_documents*`, `list_categories*`  
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

### `GET /client-api/documents/{document_id}/download` — Download PDF

Streams the PDF to the client with `attachment` content disposition.

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
- `Content-Type: application/pdf`
- `Content-Disposition: attachment; filename="original_filename.pdf"; filename*=UTF-8''original_filename.pdf`
- Body: Streamed PDF bytes

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

### `GET /client-api/documents/{document_id}/view` — View PDF Inline

Same as download but uses `inline` content disposition, allowing browsers to render the PDF directly (supports `#page=N` fragments).

**Path Parameter:** `document_id` (string)

**Success Response — `200 OK`:**
- `Content-Type: application/pdf`
- `Content-Disposition: inline; filename="original_filename.pdf"; filename*=UTF-8''original_filename.pdf`
- Body: Streamed PDF bytes

**Error Responses:** Same as download.

---

### `DELETE /client-api/documents/cleanup/daily` — Cleanup Temporary Documents

**Invalidates:** `list_documents*`, `get_document*`, `list_categories*`  
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

**Base path:** `/client-api/batches`

---

### `GET /client-api/batches/{batch_id}` — Get Batch Status Snapshot

**No caching** (always fresh for status).  
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
      "status": "indexing_images",
      "detail": "Indexing 8 images...",
      "timestamp": "2024-01-15T11:04:45.000Z"
    },
    "document3.pdf": {
      "status": "failed",
      "detail": "Processing failed: corrupted PDF header",
      "timestamp": "2024-01-15T11:03:00.000Z"
    }
  },
  "timestamp": "2024-01-15T11:05:01.000Z"
}
```

**File Status Values:**

| Status | Description |
|--------|-------------|
| `pending` | Waiting to start |
| `processing` | General processing started |
| `parsing` | PDF parsing via Docling |
| `extracting_images` | Extracting figures |
| `chunking` | Text chunking |
| `indexing` | Indexing text chunks |
| `analyzing_images` | Vision model analysis |
| `indexing_images` | Image embedding + indexing |
| `indexing_tables` | Table indexing |
| `completed` | Done |
| `failed` | Error (see `detail`) |

**Error Responses:**
```json
// 404 — Batch ID not found
{
  "detail": "Batch not found"
}
```

---

### `POST /client-api/batches/{batch_id}/terminate` — Terminate Batch

Stops processing for all non-completed documents in the batch. Completed documents are preserved.

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

### `GET /client-api/batches/{batch_id}/progress` — Stream Batch Progress (SSE)

Proxies the main API SSE stream. Stays open until the client disconnects.

**Path Parameter:** `batch_id` (string)  
**Response Content-Type:** `text/event-stream`

**SSE Events Format:**

```
// Initial snapshot (sent immediately on connection):
data: {"type": "initial_state", "batch_id": "a3f8e9d2c1b047f6", "files": {"document1.pdf": {"status": "pending", "detail": "Waiting to start...", "timestamp": "..."}}}

// Progress update for a file:
data: {"batch_id": "a3f8e9d2c1b047f6", "filename": "document1.pdf", "status": "parsing", "detail": "Parsing PDF document...", "timestamp": "2024-01-15T11:04:30.000Z"}

// File completed:
data: {"batch_id": "a3f8e9d2c1b047f6", "filename": "document1.pdf", "status": "completed", "detail": "Processing completed successfully.", "timestamp": "2024-01-15T11:05:00.000Z"}

// File failed:
data: {"batch_id": "a3f8e9d2c1b047f6", "filename": "document3.pdf", "status": "failed", "detail": "Processing failed: corrupted PDF header", "timestamp": "2024-01-15T11:03:00.000Z"}

// Heartbeat (every 15 seconds to keep connection alive):
data: {"type": "heartbeat", "batch_id": "a3f8e9d2c1b047f6", "timestamp": "2024-01-15T11:05:15.000Z"}
```

**JavaScript Example:**
```javascript
const evtSource = new EventSource('/client-api/batches/a3f8e9d2c1b047f6/progress');

evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'initial_state') {
    // Initialize UI with all file statuses
    renderFileList(data.files);
  } else if (data.type === 'heartbeat') {
    // Keep-alive, no UI update needed
  } else {
    // Update specific file status
    updateFileStatus(data.filename, data.status, data.detail);
    
    // Check if all done to close stream
    if (data.status === 'completed' || data.status === 'failed') {
      checkAllComplete();
    }
  }
};
```

---

## Chat API

**Base path:** `/client-api/chat`

---

### `GET /client-api/chat` — List Chat Sessions

**Cache:** `list_chats:{username}:{limit}` (60s TTL)

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | ✅ | User identifier |
| `limit` | integer | ❌ | Max results (default: 50) |

**Success Response — `200 OK`:**
```json
[
  {
    "chat_id": "chat_a1b2c3d4e5f6",
    "username": "engineer01",
    "title": null,
    "category_ids": ["cat_3f9a1b2c4d5e"],
    "document_ids": null,
    "created_at": "2024-01-15T12:00:00.000Z",
    "messages": [
      {
        "role": "user",
        "content": "What causes a blowout?",
        "timestamp": "2024-01-15T12:00:00.000Z",
        "sources": null,
        "image_paths": []
      },
      {
        "role": "assistant",
        "content": "A blowout occurs when...",
        "timestamp": "2024-01-15T12:00:05.000Z",
        "sources": {
          "doc_1a2b3c4d5e6f": {
            "filename": "well_control_manual.pdf",
            "pages": [5, 6, 7]
          }
        },
        "image_paths": ["./extracted_images/.../p6_img0.png"]
      }
    ]
  }
]
```

---

### `GET /client-api/chat/{chat_id}` — Get Chat Session

**Cache:** `get_chat:{username}:{chat_id}` (60s TTL)

**Path Parameter:** `chat_id` (string)  
**Query Parameter:** `username` (string, required)

**Success Response — `200 OK`:** Single `ChatSession` object (same structure as list item above).

**Error Responses:**
```json
// 404 — Chat not found or username mismatch
{
  "detail": "Chat not found: chat_a1b2c3d4e5f6"
}
```

---

### `DELETE /client-api/chat/{chat_id}` — Delete Chat Session

**Invalidates:** `get_chat:{username}:{chat_id}`, `list_chats:{username}*`

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

### `POST /client-api/chat` — Send Message (Synchronous)

**Invalidates:** `list_chats:{username}*`, `get_chat:{username}:{chat_id}` (if chat_id provided)  
**Content-Type:** `multipart/form-data`

**Form Fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `message` | string | ✅ | — | User's text message |
| `username` | string | ✅ | — | User identifier |
| `chat_id` | string | ❌ | `null` | Existing session ID; omit to create new |
| `category_ids` | string (JSON) | ❌ | `null` | JSON array: `'["cat_abc123"]'` or CSV: `"cat_abc123,cat_def456"` |
| `document_ids` | string (JSON) | ❌ | `null` | JSON array: `'["doc_abc123"]'` or CSV |
| `images` | `UploadFile[]` | ❌ | `[]` | Up to 10 image files sent to vision model |

> **Context Selection Logic:**  
> - If **no categories or documents** are explicitly selected, the frontend automatically defaults to fetching and including **all documents across all categories**. 
> - If a **category is selected without specifying individual documents**, the frontend automatically fetches and includes **all documents** within that category.  
> - The backend receives explicit `category_ids` and `document_ids` lists based on these resolutions.

**Example cURL:**
```bash
curl -X POST "http://localhost:8001/client-api/chat" \
  -F "message=Explain the driller's method for well control" \
  -F "username=engineer01" \
  -F 'category_ids=["cat_3f9a1b2c4d5e"]'
```

**Example with image:**
```bash
curl -X POST "http://localhost:8001/client-api/chat" \
  -F "message=What does this P&ID diagram show?" \
  -F "username=engineer01" \
  -F "images=@pid_diagram.png"
```

**Success Response — `200 OK`:**
```json
{
  "chat_id": "chat_a1b2c3d4e5f6",
  "username": "engineer01",
  "message_id": "msg_1f2e3d4c5b6a",
  "answer": "The Driller's Method is a two-circulation kill technique [well_control_manual.pdf, Page 18–19]. In the first circulation, influx is circulated out while maintaining constant drill pipe pressure [well_control_manual.pdf, Page 20]. The second circulation uses kill mud to bring the wellbore to static conditions [drilling_handbook.pdf, Page 45].",
  "sources": {
    "doc_1a2b3c4d5e6f": {
      "filename": "well_control_manual.pdf",
      "category_id": "cat_3f9a1b2c4d5e",
      "category_name": "Well Control Documents",
      "pages": [18, 19, 20],
      "score": 0.934,
      "contains": ["text", "table"]
    },
    "doc_2b3c4d5e6f7a": {
      "filename": "drilling_handbook.pdf",
      "category_id": "cat_3f9a1b2c4d5e",
      "category_name": "Well Control Documents",
      "pages": [45],
      "score": 0.811,
      "contains": ["text"]
    }
  },
  "inline_citations": [
    {
      "source_number": 1,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "Kill Methods",
      "pages": [18, 19]
    },
    {
      "source_number": 2,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "First Circulation",
      "pages": [20]
    },
    {
      "source_number": 3,
      "document_id": "doc_2b3c4d5e6f7a",
      "filename": "drilling_handbook.pdf",
      "section_title": "Kill Mud Procedures",
      "pages": [45]
    }
  ],
  "image_results": [
    {
      "image_id": "doc_1a2b3c4d5e6f_p19_img0",
      "document_id": "doc_1a2b3c4d5e6f",
      "page_number": 19,
      "section_title": "Kill Methods",
      "caption": "Figure 7: Driller's method pressure schedule",
      "image_path": "./extracted_images/cat_3f9a1b2c4d5e/doc_1a2b3c4d5e6f/p19_img0.png",
      "score": 0.0
    }
  ]
}
```

**Response Field Descriptions:**

| Field | Description |
|-------|-------------|
| `chat_id` | Session ID — **save and include** in next message for conversation continuity |
| `answer` | Answer with citations as `[filename.pdf, Page X–Y]` |
| `sources` | Only sources actually cited in the answer (auto-filtered) |
| `inline_citations` | Structured citation objects for building reference UI |
| `image_results` | Retrieved document images relevant to the query |

**Sources Object Schema:**
```json
{
  "doc_1a2b3c4d5e6f": {
    "filename": "well_control_manual.pdf",
    "category_id": "cat_3f9a1b2c4d5e",
    "category_name": "Well Control Documents",
    "pages": [5, 6, 12, 13],
    "score": 0.923,
    "contains": ["text", "table", "image"]
  }
}
```

**`contains` values:** `text`, `table`, `image`

**Off-topic query response** (LLM Guard triggered):
```json
{
  "chat_id": "chat_a1b2c3d4e5f6",
  "username": "engineer01",
  "message_id": "msg_9g8h7i6j5k4l",
  "answer": "I specialize in petroleum engineering topics. For cooking recipes, I'd recommend a culinary resource. Is there something related to drilling or well control I can help you with?",
  "sources": {},
  "inline_citations": [],
  "image_results": []
}
```

**Error Responses:**
```json
// 400 — Too many images
{
  "detail": "Maximum 10 images allowed"
}

// 404 — chat_id provided but not found
{
  "detail": "Chat not found: chat_a1b2c3d4e5f6"
}
```

---

### `POST /client-api/chat/stream` — Send Message (Server-Sent Events)

Proxies the streaming chat endpoint. Response tokens stream word-by-word, followed by a final metadata event.

**Invalidates:** `list_chats:{username}*`, `get_chat:{username}:{chat_id}` (if chat_id provided)  
**Content-Type:** `multipart/form-data`  
**Response Content-Type:** `text/event-stream`

**Form Fields:** Same as synchronous chat (`message`, `username`, `chat_id`, `category_ids`, `document_ids`, `images`)

**SSE Stream Events:**

```
// Streaming tokens (real-time display):
data: {"token": "The "}
data: {"token": "Driller's "}
data: {"token": "Method "}
data: {"token": "is "}
...

// Final event (complete metadata):
data: {
  "done": true,
  "chat_id": "chat_a1b2c3d4e5f6",
  "username": "engineer01",
  "message_id": "msg_1f2e3d4c5b6a",
  "answer": "The Driller's Method is a two-circulation kill technique [well_control_manual.pdf, Page 18–19]...",
  "sources": {
    "doc_1a2b3c4d5e6f": {
      "filename": "well_control_manual.pdf",
      "category_id": "cat_3f9a1b2c4d5e",
      "category_name": "Well Control Documents",
      "pages": [18, 19, 20],
      "score": 0.934,
      "contains": ["text"]
    }
  },
  "inline_citations": [
    {
      "source_number": 1,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "Kill Methods",
      "pages": [18, 19]
    }
  ],
  "image_results": [
    {
      "image_id": "doc_1a2b3c4d5e6f_p19_img0",
      "document_id": "doc_1a2b3c4d5e6f",
      "page_number": 19,
      "section_title": "Kill Methods",
      "caption": "Figure 7",
      "image_path": "./extracted_images/.../p19_img0.png",
      "score": 0.0
    }
  ]
}
```

**Error Event:**
```
data: {"error": "Streaming failed: connection timeout"}
```

**JavaScript Integration Example:**
```javascript
const formData = new FormData();
formData.append('message', 'Explain driller method');
formData.append('username', 'engineer01');
formData.append('category_ids', JSON.stringify(['cat_3f9a1b2c4d5e']));

const response = await fetch('/client-api/chat/stream', {
  method: 'POST',
  body: formData
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
let fullAnswer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  
  buffer += decoder.decode(value, { stream: true });
  const lines = buffer.split('\n\n');
  buffer = lines.pop(); // Keep incomplete line
  
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      
      if (data.token) {
        // Append token to streaming display
        fullAnswer += data.token;
        updateStreamingUI(fullAnswer);
      } else if (data.done) {
        // Use final answer (has enriched citations)
        renderFinalAnswer(data.answer, data.sources, data.inline_citations, data.image_results);
        saveChatId(data.chat_id);
      } else if (data.error) {
        handleError(data.error);
      }
    }
  }
}
```

> **Important:** Accumulate `token` events for live display. The `done` event's `answer` field has citations fully enriched (replaced with filenames). Always use the `done.answer` as the canonical stored text.

---

## Query API

**Base path:** `/client-api/query`  
Stateless RAG queries (no session history).

---

### `POST /client-api/query` — RAG Query

**No caching.**  
**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query": "What is the maximum allowable surface pressure during a well control operation?",
  "category_ids": ["cat_3f9a1b2c4d5e"],
  "document_ids": null,
  "include_images": true,
  "include_tables": true
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | string | ✅ | — | Natural language question |
| `category_ids` | string[] | ❌ | `null` | Filter by categories |
| `document_ids` | string[] | ❌ | `null` | Filter by specific documents |
| `include_images` | boolean | ❌ | `true` | Enrich chunks with related images |
| `include_tables` | boolean | ❌ | `true` | Enrich chunks with related tables |

**Success Response — `200 OK`:**
```json
{
  "query": "What is the maximum allowable surface pressure during a well control operation?",
  "answer": "The Maximum Allowable Annular Surface Pressure (MAASP) is determined by the weakest formation exposed to the wellbore [well_control_manual.pdf, Page 31–32]. It is calculated as:\n\n**MAASP = (LOT pressure - hydrostatic mud pressure at shoe) × 0.052 × TVD** [well_control_manual.pdf, Page 32]\n\nExceeding MAASP risks formation fracture and lost circulation [drilling_handbook.pdf, Page 67].",
  "retrieved_chunks": [
    {
      "chunk_id": "doc_1a2b3c4d5e6f_chunk_15",
      "content": "Section 6.1: MAASP Calculation. The maximum allowable annular surface pressure...",
      "score": 0.941,
      "section_title": "Pressure Calculations",
      "page_start": 31,
      "page_end": 33,
      "image_ids": ["doc_1a2b3c4d5e6f_p32_img1"]
    }
  ],
  "sources": ["doc_1a2b3c4d5e6f", "doc_2b3c4d5e6f7a"],
  "inline_citations": [
    {
      "source_number": 1,
      "document_id": "doc_1a2b3c4d5e6f",
      "filename": "well_control_manual.pdf",
      "section_title": "Pressure Calculations",
      "pages": [31, 32]
    }
  ]
}
```

**Error Responses:**
```json
// 422 — Missing query field
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

### `POST /client-api/query/image-search` — Image Semantic Search

**No caching.**  
**Content-Type:** `application/json`

**Request Body:**
```json
{
  "query_text": "wellbore pressure diagram during kick",
  "query_image_base64": null,
  "category_ids": ["cat_3f9a1b2c4d5e"],
  "document_ids": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query_text` | string | ❌* | Text description to find matching images |
| `query_image_base64` | string | ❌* | Base64-encoded image for similarity search |
| `category_ids` | string[] | ❌ | Filter by categories |
| `document_ids` | string[] | ❌ | Filter by documents |

> ⚠️ At least one of `query_text` or `query_image_base64` is required.

**Success Response — `200 OK`:**
```json
{
  "query_text": "wellbore pressure diagram during kick",
  "has_query_image": false,
  "results": [
    {
      "image_id": "doc_1a2b3c4d5e6f_p13_img0",
      "document_id": "doc_1a2b3c4d5e6f",
      "page_number": 13,
      "section_title": "Kick Detection",
      "caption": "Figure 4: Wellbore pressure profile during kick",
      "image_path": "./extracted_images/cat_3f9a1b2c4d5e/doc_1a2b3c4d5e6f/p13_img0.png",
      "score": 0.887
    },
    {
      "image_id": "doc_2b3c4d5e6f7a_p28_img2",
      "document_id": "doc_2b3c4d5e6f7a",
      "page_number": 28,
      "section_title": "Pressure Control",
      "caption": null,
      "image_path": "./extracted_images/cat_3f9a1b2c4d5e/doc_2b3c4d5e6f7a/p28_img2.png",
      "score": 0.821
    }
  ],
  "count": 2
}
```

**Error Responses:**
```json
// 400 — Neither text nor image provided
{
  "detail": "At least one of 'query_text' or 'query_image_base64' must be provided"
}
```

---

## Data Models Reference

### CategoryResponse
```json
{
  "category_id": "string — e.g. cat_3f9a1b2c4d5e",
  "name": "string",
  "description": "string | null",
  "document_count": "integer",
  "created_at": "datetime ISO 8601"
}
```

### DocumentResponse
```json
{
  "document_id": "string — e.g. doc_1a2b3c4d5e6f",
  "category_id": "string",
  "filename": "string — original filename",
  "status": "pending | processing | completed | failed",
  "upload_date": "datetime ISO 8601",
  "batch_id": "string | null",
  "is_daily": "boolean",
  "error_message": "string | null — populated only on failure"
}
```

### UploadResponse
```json
{
  "document_id": "string",
  "category_id": "string",
  "filename": "string",
  "status": "string — always 'pending' on upload",
  "batch_id": "string — use to track progress",
  "message": "string"
}
```

### BatchStatusResponse
```json
{
  "batch_id": "string",
  "files": {
    "{filename}": {
      "status": "string",
      "detail": "string | null",
      "timestamp": "datetime ISO 8601"
    }
  },
  "timestamp": "datetime ISO 8601"
}
```

### ChatSession
```json
{
  "chat_id": "string",
  "username": "string",
  "title": "string | null",
  "category_ids": ["string"] | null,
  "document_ids": ["string"] | null,
  "created_at": "datetime ISO 8601",
  "messages": [
    {
      "role": "user | assistant",
      "content": "string",
      "timestamp": "datetime ISO 8601",
      "sources": "dict | null",
      "image_paths": ["string"]
    }
  ]
}
```

### ChatResponse
```json
{
  "chat_id": "string",
  "username": "string",
  "message_id": "string",
  "answer": "string — with [filename.pdf, Page X] citation syntax",
  "sources": {
    "{document_id}": {
      "filename": "string",
      "category_id": "string",
      "category_name": "string | null",
      "pages": ["integer"],
      "score": "float",
      "contains": ["text | table | image"]
    }
  },
  "inline_citations": [
    {
      "source_number": "integer",
      "document_id": "string",
      "filename": "string",
      "section_title": "string",
      "pages": ["integer"]
    }
  ],
  "image_results": [
    {
      "image_id": "string",
      "document_id": "string",
      "page_number": "integer",
      "section_title": "string | null",
      "caption": "string | null",
      "image_path": "string",
      "score": "float"
    }
  ]
}
```

### QueryResponse
```json
{
  "query": "string",
  "answer": "string",
  "retrieved_chunks": [
    {
      "chunk_id": "string",
      "content": "string",
      "score": "float",
      "section_title": "string",
      "page_start": "integer",
      "page_end": "integer",
      "image_ids": ["string"]
    }
  ],
  "sources": ["string — document_id list"],
  "inline_citations": [
    {
      "source_number": "integer",
      "document_id": "string",
      "filename": "string",
      "section_title": "string",
      "pages": ["integer"]
    }
  ]
}
```

### ImageSearchResponse
```json
{
  "query_text": "string | null",
  "has_query_image": "boolean",
  "results": [
    {
      "image_id": "string",
      "document_id": "string",
      "page_number": "integer",
      "section_title": "string | null",
      "caption": "string | null",
      "image_path": "string",
      "score": "float"
    }
  ],
  "count": "integer"
}
```

---

## Endpoint Summary Table

| Method | Path | Cache | Description |
|--------|------|-------|-------------|
| `GET` | `/client-api/categories` | ✅ 60s | List all categories |
| `POST` | `/client-api/categories` | ❌ (invalidates) | Create category |
| `PUT` | `/client-api/categories/{id}` | ❌ (invalidates) | Update category |
| `DELETE` | `/client-api/categories/{id}` | ❌ (invalidates) | Delete category |
| `GET` | `/client-api/categories/{id}/documents` | ✅ 60s | List category docs |
| `GET` | `/client-api/documents` | ✅ 60s | List all documents |
| `GET` | `/client-api/documents/{id}` | ✅ 60s | Get document metadata |
| `POST` | `/client-api/documents/upload/{cat_id}` | ❌ (invalidates) | Upload PDFs |
| `DELETE` | `/client-api/documents/{id}` | ❌ (invalidates) | Delete document |
| `DELETE` | `/client-api/documents/{id}/burn` | ❌ (invalidates) | Burn document |
| `GET` | `/client-api/documents/{id}/download` | ❌ | Download PDF |
| `GET` | `/client-api/documents/{id}/view` | ❌ | View PDF inline |
| `DELETE` | `/client-api/documents/cleanup/daily` | ❌ (invalidates) | Cleanup temp docs |
| `GET` | `/client-api/batches/{id}` | ❌ | Get batch snapshot |
| `POST` | `/client-api/batches/{id}/terminate` | ❌ | Terminate batch |
| `GET` | `/client-api/batches/{id}/progress` | ❌ SSE | Stream progress |
| `GET` | `/client-api/chat` | ✅ 60s | List chat sessions |
| `GET` | `/client-api/chat/{id}` | ✅ 60s | Get chat session |
| `DELETE` | `/client-api/chat/{id}` | ❌ (invalidates) | Delete chat |
| `POST` | `/client-api/chat` | ❌ (invalidates) | Send message (sync) |
| `POST` | `/client-api/chat/stream` | ❌ SSE | Send message (stream) |
| `POST` | `/client-api/query` | ❌ | RAG query |
| `POST` | `/client-api/query/image-search` | ❌ | Image search |
