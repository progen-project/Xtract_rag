"""Generate PetroRAG Postman collection with accurate examples matching actual API schemas."""
import json

def ex(name, method, url_raw, url_host, url_path, status="OK", code=200,
       lang="json", ct="application/json", body="", req_header=None,
       req_body=None, req_body_mode="raw", url_query=None):
    """Helper to build a Postman saved example."""
    orig = {"method": method, "header": req_header or [], "url": {
        "raw": url_raw, "host": [url_host], "path": url_path
    }}
    if url_query:
        orig["url"]["query"] = url_query
    if req_body:
        orig["body"] = {"mode": req_body_mode}
        if req_body_mode == "raw":
            orig["body"]["raw"] = req_body
        elif req_body_mode == "formdata":
            orig["body"]["formdata"] = req_body
    return {
        "name": name, "originalRequest": orig,
        "status": status, "code": code, "_postman_previewlanguage": lang,
        "header": [{"key": "Content-Type", "value": ct}],
        "cookie": [], "body": body
    }

def json_header():
    return [{"key": "Content-Type", "value": "application/json"}]

# ── Validation error body (422) ──
V422 = json.dumps({
    "detail": [{"loc": ["body", "name"], "msg": "field required", "type": "value_error.missing"}]
}, indent=4)

N404 = lambda thing: json.dumps({"detail": f"{thing} not found"}, indent=4)

# ══════════════════════════════════════════════════════════════════
# CATEGORIES
# ══════════════════════════════════════════════════════════════════
cat_response = json.dumps({
    "category_id": "a1b2c3d4e5f6", "name": "Drilling Reports",
    "description": "Technical drilling reports and logs",
    "document_count": 0, "created_at": "2024-06-15T08:30:00"
}, indent=4)

cat_response_with_docs = json.dumps({
    "category_id": "a1b2c3d4e5f6", "name": "Drilling Reports",
    "description": "Technical drilling reports and logs",
    "document_count": 12, "created_at": "2024-06-15T08:30:00"
}, indent=4)

cat_list = json.dumps([
    {"category_id": "a1b2c3d4e5f6", "name": "Drilling Reports",
     "description": "Technical drilling reports", "document_count": 12,
     "created_at": "2024-06-15T08:30:00"},
    {"category_id": "f6e5d4c3b2a1", "name": "Safety Manuals",
     "description": "HSE documentation", "document_count": 5,
     "created_at": "2024-07-01T10:00:00"}
], indent=4)

categories = {
    "name": "Categories", "description": "CRUD operations for document categories.",
    "item": [
        {
            "name": "Create Category",
            "event": [{"listen": "test", "script": {"exec": [
                "if (pm.response.code === 200) {",
                "    const json = pm.response.json();",
                "    pm.environment.set('category_id', json.category_id);",
                "    pm.test('Category created', () => {",
                "        pm.expect(json).to.have.property('category_id');",
                "    });",
                "}"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "POST", "header": json_header(),
                "body": {"mode": "raw", "raw": json.dumps({"name": "Drilling Reports", "description": "Technical drilling reports and logs"}, indent=4)},
                "url": {"raw": "{{base_url}}/categories", "host": ["{{base_url}}"], "path": ["categories"]},
                "description": "Create a new document category.\n\n**Request Body (JSON):**\n| Field | Type | Required | Description |\n|-------|------|----------|-------------|\n| `name` | string | ✅ | Category name |\n| `description` | string | ❌ | Optional description |\n\n**Response:** `CategoryResponse`"
            },
            "response": [
                ex("200 — Created", "POST", "{{base_url}}/categories", "{{base_url}}", ["categories"],
                   body=cat_response, req_header=json_header(),
                   req_body=json.dumps({"name": "Drilling Reports", "description": "Technical drilling reports and logs"})),
                ex("422 — Validation Error", "POST", "{{base_url}}/categories", "{{base_url}}", ["categories"],
                   status="Unprocessable Entity", code=422, body=V422, req_header=json_header(),
                   req_body=json.dumps({"description": "Missing name field"}))
            ]
        },
        {
            "name": "List Categories",
            "event": [{"listen": "test", "script": {"exec": [
                "pm.test('Returns array', () => pm.expect(pm.response.json()).to.be.an('array'));",
                "const cats = pm.response.json();",
                "if (cats.length > 0) pm.environment.set('category_id', cats[0].category_id);"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/categories", "host": ["{{base_url}}"], "path": ["categories"]},
                "description": "List all categories.\n\n**Response:** `CategoryResponse[]`"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/categories", "{{base_url}}", ["categories"], body=cat_list)
            ]
        },
        {
            "name": "Get Category",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/categories/{{category_id}}", "host": ["{{base_url}}"], "path": ["categories", "{{category_id}}"]},
                "description": "Get a single category by ID.\n\n**Path:** `category_id`\n\n**Response:** `CategoryResponse`"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/categories/{{category_id}}", "{{base_url}}", ["categories", "{{category_id}}"], body=cat_response_with_docs),
                ex("404 — Not Found", "GET", "{{base_url}}/categories/bad_id", "{{base_url}}", ["categories", "bad_id"],
                   status="Not Found", code=404, body=N404("Category"))
            ]
        },
        {
            "name": "Update Category",
            "request": {
                "method": "PUT", "header": json_header(),
                "body": {"mode": "raw", "raw": json.dumps({"name": "Updated Name", "description": "Updated description"}, indent=4)},
                "url": {"raw": "{{base_url}}/categories/{{category_id}}", "host": ["{{base_url}}"], "path": ["categories", "{{category_id}}"]},
                "description": "Update a category name and/or description.\n\n**Request Body (JSON):**\n| Field | Type | Required |\n|-------|------|----------|\n| `name` | string | ❌ |\n| `description` | string | ❌ |\n\n**Response:** `CategoryResponse`"
            },
            "response": [
                ex("200 — Updated", "PUT", "{{base_url}}/categories/{{category_id}}", "{{base_url}}", ["categories", "{{category_id}}"],
                   body=json.dumps({"category_id": "a1b2c3d4e5f6", "name": "Updated Name", "description": "Updated description", "document_count": 12, "created_at": "2024-06-15T08:30:00"}, indent=4),
                   req_header=json_header(), req_body=json.dumps({"name": "Updated Name"})),
                ex("404 — Not Found", "PUT", "{{base_url}}/categories/bad_id", "{{base_url}}", ["categories", "bad_id"],
                   status="Not Found", code=404, body=N404("Category"), req_header=json_header())
            ]
        },
        {
            "name": "Delete Category",
            "request": {
                "method": "DELETE",
                "url": {"raw": "{{base_url}}/categories/{{category_id}}", "host": ["{{base_url}}"], "path": ["categories", "{{category_id}}"]},
                "description": "Delete a category. Documents remain but lose their category grouping.\n\n**Response:** `{message}`"
            },
            "response": [
                ex("200 — Deleted", "DELETE", "{{base_url}}/categories/{{category_id}}", "{{base_url}}", ["categories", "{{category_id}}"],
                   body=json.dumps({"message": "Category a1b2c3d4e5f6 deleted"}, indent=4)),
                ex("404 — Not Found", "DELETE", "{{base_url}}/categories/bad_id", "{{base_url}}", ["categories", "bad_id"],
                   status="Not Found", code=404, body=N404("Category"))
            ]
        }
    ]
}

# ══════════════════════════════════════════════════════════════════
# DOCUMENTS
# ══════════════════════════════════════════════════════════════════
doc_upload_resp = json.dumps([{
    "document_id": "d0c1a2b3e4f5", "category_id": "a1b2c3d4e5f6",
    "filename": "Well_Report_2024.pdf", "message": "Document uploaded successfully",
    "status": "pending", "batch_id": "b1a2t3c4h5"
}], indent=4)

doc_meta = json.dumps({
    "document_id": "d0c1a2b3e4f5", "category_id": "a1b2c3d4e5f6",
    "filename": "Well_Report_2024.pdf",
    "file_path": "/data/uploads/Drilling Reports/abc_Well_Report_2024.pdf",
    "file_size": 2048576, "page_count": 45,
    "upload_date": "2024-06-15T09:00:00", "status": "completed",
    "batch_id": "b1a2t3c4h5", "is_daily": False,
    "toc": [{"title": "Executive Summary", "level": 1, "page_number": 1, "page_end": 3},
            {"title": "Drilling Operations", "level": 1, "page_number": 4, "page_end": 20}],
    "processing_errors": []
}, indent=4)

doc_list = json.dumps([json.loads(doc_meta)], indent=4)

ff = [{"key": "files", "type": "file", "description": "PDF file(s) to upload", "src": []}]

documents = {
    "name": "Documents", "description": "Upload, manage, and download PDF documents.",
    "item": [
        {
            "name": "Upload Documents (Permanent)",
            "event": [{"listen": "test", "script": {"exec": [
                "if (pm.response.code === 200) {",
                "    const json = pm.response.json();",
                "    if (json.length > 0) {",
                "        pm.environment.set('document_id', json[0].document_id);",
                "        pm.environment.set('batch_id', json[0].batch_id);",
                "    }",
                "}"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "POST",
                "body": {"mode": "formdata", "formdata": ff},
                "url": {"raw": "{{base_url}}/documents/upload/{{category_id}}", "host": ["{{base_url}}"], "path": ["documents", "upload", "{{category_id}}"]},
                "description": "Upload PDF documents to a category for processing.\n\n**Path:** `category_id`\n**Form Data:** `files` — one or more PDF files (max 50)\n\n**Response:** `DocumentUploadResponse[]`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `document_id` | string | Unique document ID |\n| `category_id` | string | Target category |\n| `filename` | string | Original filename |\n| `message` | string | Status message |\n| `status` | enum | `pending` \\| `processing` \\| `completed` \\| `failed` |\n| `batch_id` | string | Batch tracking ID |"
            },
            "response": [
                ex("200 — Uploaded", "POST", "{{base_url}}/documents/upload/{{category_id}}", "{{base_url}}", ["documents", "upload", "{{category_id}}"],
                   body=doc_upload_resp, req_body=ff, req_body_mode="formdata"),
                ex("400 — Too Many Files", "POST", "{{base_url}}/documents/upload/{{category_id}}", "{{base_url}}", ["documents", "upload", "{{category_id}}"],
                   status="Bad Request", code=400, body=json.dumps({"detail": "Maximum 50 files allowed per batch"}, indent=4)),
                ex("400 — No Valid PDFs", "POST", "{{base_url}}/documents/upload/{{category_id}}", "{{base_url}}", ["documents", "upload", "{{category_id}}"],
                   status="Bad Request", code=400, body=json.dumps({"detail": "No valid PDF files found in batch"}, indent=4)),
                ex("404 — Category Not Found", "POST", "{{base_url}}/documents/upload/bad_id", "{{base_url}}", ["documents", "upload", "bad_id"],
                   status="Not Found", code=404, body=N404("Category"))
            ]
        },
        {
            "name": "Upload Documents (Daily / Temporary)",
            "request": {
                "method": "POST",
                "body": {"mode": "formdata", "formdata": ff},
                "url": {"raw": "{{base_url}}/documents/upload/daily/{{category_id}}", "host": ["{{base_url}}"], "path": ["documents", "upload", "daily", "{{category_id}}"]},
                "description": "Upload temporary documents that auto-delete after 24 hours.\n\nSame interface as permanent upload but documents are marked `is_daily=true`."
            },
            "response": [
                ex("200 — Uploaded", "POST", "{{base_url}}/documents/upload/daily/{{category_id}}", "{{base_url}}", ["documents", "upload", "daily", "{{category_id}}"],
                   body=json.dumps([{"document_id": "d_daily_001", "category_id": "a1b2c3d4e5f6", "filename": "temp_notes.pdf", "message": "Document uploaded successfully", "status": "pending", "batch_id": "b_daily_01"}], indent=4))
            ]
        },
        {
            "name": "List Documents",
            "event": [{"listen": "test", "script": {"exec": [
                "pm.test('Returns array', () => pm.expect(pm.response.json()).to.be.an('array'));",
                "const docs = pm.response.json();",
                "if (docs.length > 0) pm.environment.set('document_id', docs[0].document_id);"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/documents?category_id={{category_id}}", "host": ["{{base_url}}"], "path": ["documents"],
                        "query": [{"key": "category_id", "value": "{{category_id}}", "description": "Optional. Filter by category."}]},
                "description": "List all documents, optionally filtered by category.\n\n**Query:** `category_id` (optional)\n\n**Response:** `DocumentMetadata[]`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `document_id` | string | Unique ID |\n| `category_id` | string | Category |\n| `filename` | string | Original filename |\n| `file_path` | string | Server path |\n| `file_size` | int | Bytes |\n| `page_count` | int | Number of pages |\n| `upload_date` | datetime | Upload timestamp |\n| `status` | enum | `pending`\\|`processing`\\|`completed`\\|`failed` |\n| `batch_id` | string? | Batch ID |\n| `is_daily` | bool | Auto-deletes after 24h |\n| `toc` | TOCEntry[] | Table of contents |\n| `processing_errors` | string[] | Error messages |"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/documents", "{{base_url}}", ["documents"], body=doc_list)
            ]
        },
        {
            "name": "Get Document",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/documents/{{document_id}}", "host": ["{{base_url}}"], "path": ["documents", "{{document_id}}"]},
                "description": "Get metadata for a single document.\n\n**Response:** `DocumentMetadata`"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/documents/{{document_id}}", "{{base_url}}", ["documents", "{{document_id}}"], body=doc_meta),
                ex("404 — Not Found", "GET", "{{base_url}}/documents/bad_id", "{{base_url}}", ["documents", "bad_id"],
                   status="Not Found", code=404, body=N404("Document"))
            ]
        },
        {
            "name": "Download Document",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/documents/{{document_id}}/download", "host": ["{{base_url}}"], "path": ["documents", "{{document_id}}", "download"]},
                "description": "Download the original PDF file.\n\n**Response:** Binary PDF with `Content-Disposition: attachment`"
            },
            "response": [
                ex("200 — File", "GET", "{{base_url}}/documents/{{document_id}}/download", "{{base_url}}", ["documents", "{{document_id}}", "download"],
                   lang="html", ct="application/pdf", body="[Binary PDF Data]"),
                ex("404 — Not Found", "GET", "{{base_url}}/documents/bad_id/download", "{{base_url}}", ["documents", "bad_id", "download"],
                   status="Not Found", code=404, body=N404("Document"))
            ]
        },
        {
            "name": "Delete Document (Soft)",
            "request": {
                "method": "DELETE",
                "url": {"raw": "{{base_url}}/documents/{{document_id}}", "host": ["{{base_url}}"], "path": ["documents", "{{document_id}}"]},
                "description": "Soft-delete a document.\n\n**Response:** `{message}`"
            },
            "response": [
                ex("200 — Deleted", "DELETE", "{{base_url}}/documents/{{document_id}}", "{{base_url}}", ["documents", "{{document_id}}"],
                   body=json.dumps({"message": "Document d0c1a2b3e4f5 deleted"}, indent=4)),
                ex("404 — Not Found", "DELETE", "{{base_url}}/documents/bad_id", "{{base_url}}", ["documents", "bad_id"],
                   status="Not Found", code=404, body=N404("Document"))
            ]
        },
        {
            "name": "Burn Document (Full Purge)",
            "request": {
                "method": "DELETE",
                "url": {"raw": "{{base_url}}/documents/{{document_id}}/burn", "host": ["{{base_url}}"], "path": ["documents", "{{document_id}}", "burn"]},
                "description": "**Permanently** remove a document and ALL related data (MongoDB, Qdrant vectors, disk files).\n\n⚠️ Irreversible.\n\n**Response:** `{message}`"
            },
            "response": [
                ex("200 — Burned", "DELETE", "{{base_url}}/documents/{{document_id}}/burn", "{{base_url}}", ["documents", "{{document_id}}", "burn"],
                   body=json.dumps({"message": "Document d0c1a2b3e4f5 burned successfully"}, indent=4)),
                ex("404 — Not Found", "DELETE", "{{base_url}}/documents/bad_id/burn", "{{base_url}}", ["documents", "bad_id", "burn"],
                   status="Not Found", code=404, body=N404("Document"))
            ]
        },
        {
            "name": "Cleanup Daily Documents",
            "request": {
                "method": "DELETE",
                "url": {"raw": "{{base_url}}/documents/cleanup/daily", "host": ["{{base_url}}"], "path": ["documents", "cleanup", "daily"]},
                "description": "Remove all daily documents older than 24 hours.\n\n**Response:** Cleanup result"
            },
            "response": [
                ex("200 — Cleaned", "DELETE", "{{base_url}}/documents/cleanup/daily", "{{base_url}}", ["documents", "cleanup", "daily"],
                   body=json.dumps({"deleted_count": 3, "message": "Daily cleanup completed"}, indent=4))
            ]
        }
    ]
}

# ══════════════════════════════════════════════════════════════════
# BATCHES
# ══════════════════════════════════════════════════════════════════
batch_status = json.dumps({
    "batch_id": "b1a2t3c4h5",
    "files": {
        "Well_Report_2024.pdf": {"status": "embedding", "detail": "Generating vectors for page 12/45"},
        "Safety_Manual.pdf": {"status": "completed", "detail": "Done"}
    },
    "timestamp": "2024-06-15T09:05:00"
}, indent=4)

batches = {
    "name": "Batches", "description": "Track and manage document processing batches.",
    "item": [
        {
            "name": "Get Batch Status (Snapshot)",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/batches/{{batch_id}}", "host": ["{{base_url}}"], "path": ["batches", "{{batch_id}}"]},
                "description": "One-time snapshot of batch processing status.\n\n**Response:**\n| Field | Type | Description |\n|-------|------|-------------|\n| `batch_id` | string | Batch ID |\n| `files` | object | Map of filename → {status, detail} |\n| `timestamp` | datetime | Current time |"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/batches/{{batch_id}}", "{{base_url}}", ["batches", "{{batch_id}}"], body=batch_status),
                ex("404 — Not Found", "GET", "{{base_url}}/batches/bad_id", "{{base_url}}", ["batches", "bad_id"],
                   status="Not Found", code=404, body=N404("Batch"))
            ]
        },
        {
            "name": "Stream Batch Progress (SSE)",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/batches/{{batch_id}}/progress", "host": ["{{base_url}}"], "path": ["batches", "{{batch_id}}", "progress"]},
                "description": "**Server-Sent Events** stream for real-time progress.\n\n**Event format:**\n```\ndata: {\"filename\": \"report.pdf\", \"status\": \"embedding\", \"detail\": \"Page 5/20\"}\n```\n\n**Frontend:**\n```javascript\nconst evtSource = new EventSource('/api/batches/{batch_id}/progress');\nevtSource.onmessage = (e) => console.log(JSON.parse(e.data));\n```"
            },
            "response": [
                ex("200 — SSE Stream", "GET", "{{base_url}}/batches/{{batch_id}}/progress", "{{base_url}}", ["batches", "{{batch_id}}", "progress"],
                   lang="text", ct="text/event-stream",
                   body='data: {"filename": "report.pdf", "status": "chunking", "detail": "Processing page 5/20"}\n\ndata: {"filename": "report.pdf", "status": "embedding", "detail": "Generating vectors"}\n\ndata: {"filename": "report.pdf", "status": "completed", "detail": "Done"}\n\n')
            ]
        },
        {
            "name": "Terminate Batch",
            "request": {
                "method": "POST",
                "url": {"raw": "{{base_url}}/batches/{{batch_id}}/terminate", "host": ["{{base_url}}"], "path": ["batches", "{{batch_id}}", "terminate"]},
                "description": "Terminate a batch. Completed docs are kept, incomplete ones deleted.\n\n**Response:**\n| Field | Type | Description |\n|-------|------|-------------|\n| `batch_id` | string | Batch ID |\n| `total_documents` | int | Total in batch |\n| `kept_completed` | int | Completed & kept |\n| `deleted_incomplete` | int | Removed |"
            },
            "response": [
                ex("200 — Terminated", "POST", "{{base_url}}/batches/{{batch_id}}/terminate", "{{base_url}}", ["batches", "{{batch_id}}", "terminate"],
                   body=json.dumps({"batch_id": "b1a2t3c4h5", "total_documents": 5, "kept_completed": 3, "deleted_incomplete": 2}, indent=4)),
                ex("404 — Not Found", "POST", "{{base_url}}/batches/bad_id/terminate", "{{base_url}}", ["batches", "bad_id", "terminate"],
                   status="Not Found", code=404, body=N404("Batch"))
            ]
        }
    ]
}

# ══════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════
chat_resp = json.dumps({
    "chat_id": "c1h2a3t4-abcd-efgh-ijkl-567890",
    "message_id": "msg_a1b2c3d4",
    "answer": "Based on the drilling report [Source 1, Page 12], the well reached a total depth of 15,000 ft. The formation analysis [Source 2, Page 8] indicates high porosity in the target zone.",
    "sources": {
        "d0c1a2b3e4f5": {"filename": "Well_Report_2024.pdf", "pages": [12, 13]},
        "d0c1a2b3e4f6": {"filename": "Formation_Analysis.pdf", "pages": [8]}
    },
    "inline_citations": [
        {"source_number": 1, "document_id": "d0c1a2b3e4f5", "filename": "Well_Report_2024.pdf", "section_title": "Drilling Summary", "pages": [12]},
        {"source_number": 2, "document_id": "d0c1a2b3e4f6", "filename": "Formation_Analysis.pdf", "section_title": "Porosity Analysis", "pages": [8]}
    ],
    "image_results": [
        {"image_id": "img_001", "document_id": "d0c1a2b3e4f5", "page_number": 13, "section_title": "Well Diagram", "caption": "Figure 4.1: Well Profile", "image_path": "/static/images/d0c1a2b3e4f5/img_001.png", "score": 0.88}
    ]
}, indent=4)

chat_form = [
    {"key": "message", "value": "What is the total depth of the well?", "type": "text", "description": "Required. User's question."},
    {"key": "chat_id", "value": "", "type": "text", "description": "Optional. Existing chat session ID.", "disabled": True},
    {"key": "category_ids", "value": '[\"{{category_id}}\"]', "type": "text", "description": "Optional. JSON array of category IDs."},
    {"key": "top_k", "value": "5", "type": "text", "description": "Chunks to retrieve (1-20, default 5)."},
    {"key": "images", "type": "file", "description": "Optional. Image files (max 10).", "src": [], "disabled": True}
]

chat_session = json.dumps({
    "chat_id": "c1h2a3t4-abcd-efgh-ijkl-567890",
    "category_ids": ["a1b2c3d4e5f6"],
    "messages": [
        {"message_id": "msg_u001", "role": "user", "content": "What is the total depth?", "image_paths": [], "sources": None, "timestamp": "2024-06-15T10:00:00"},
        {"message_id": "msg_a001", "role": "assistant", "content": "Based on the report, the total depth is 15,000 ft.",
         "image_paths": [], "sources": {"d0c1a2b3e4f5": {"filename": "Well_Report_2024.pdf", "pages": [12]}}, "timestamp": "2024-06-15T10:00:05"}
    ],
    "created_at": "2024-06-15T10:00:00", "updated_at": "2024-06-15T10:00:05"
}, indent=4)

chat_sessions_list = json.dumps([json.loads(chat_session)], indent=4)

chat_section = {
    "name": "Chat", "description": "Conversational AI with document-grounded responses.",
    "item": [
        {
            "name": "Send Message",
            "event": [{"listen": "test", "script": {"exec": [
                "if (pm.response.code === 200) {",
                "    const json = pm.response.json();",
                "    pm.environment.set('chat_id', json.chat_id);",
                "}"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "POST",
                "body": {"mode": "formdata", "formdata": chat_form},
                "url": {"raw": "{{base_url}}/chat", "host": ["{{base_url}}"], "path": ["chat"]},
                "description": "Send a message (multipart/form-data for image support).\n\n**Form Fields:**\n| Field | Type | Required | Description |\n|-------|------|----------|-------------|\n| `message` | string | ✅ | User's question |\n| `chat_id` | string | ❌ | Continue existing chat |\n| `category_ids` | JSON string | ❌ | `'[\"id1\",\"id2\"]'` |\n| `top_k` | int | ❌ | Chunks (default 5) |\n| `images` | file[] | ❌ | Image attachments |\n\n**Response:** `ChatResponse`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `chat_id` | string | Session ID (save this!) |\n| `message_id` | string | Message ID |\n| `answer` | string | AI response with inline citations |\n| `sources` | dict | `{doc_id: {filename, pages[]}}` |\n| `inline_citations` | InlineCitation[] | `[{source_number, document_id, filename, section_title, pages[]}]` |\n| `image_results` | ImageSearchResult[] | Retrieved images |"
            },
            "response": [
                ex("200 — Success", "POST", "{{base_url}}/chat", "{{base_url}}", ["chat"],
                   body=chat_resp, req_body=chat_form, req_body_mode="formdata"),
                ex("422 — Missing Message", "POST", "{{base_url}}/chat", "{{base_url}}", ["chat"],
                   status="Unprocessable Entity", code=422,
                   body=json.dumps({"detail": [{"loc": ["body", "message"], "msg": "field required", "type": "value_error.missing"}]}, indent=4))
            ]
        },
        {
            "name": "Send Message (Streaming)",
            "request": {
                "method": "POST",
                "body": {"mode": "formdata", "formdata": [
                    {"key": "message", "value": "Summarize the uploaded documents", "type": "text"},
                    {"key": "category_ids", "value": '[\"{{category_id}}\"]', "type": "text"},
                    {"key": "top_k", "value": "5", "type": "text"}
                ]},
                "url": {"raw": "{{base_url}}/chat/stream", "host": ["{{base_url}}"], "path": ["chat", "stream"]},
                "description": "**SSE streaming** chat. Returns word-by-word tokens then final metadata.\n\n**Same form fields as Send Message.**\n\n**Event format:**\n```\ndata: {\"token\": \"Based\"}\ndata: {\"token\": \" on\"}\n...\ndata: {\"done\": true, \"chat_id\": \"...\", \"message_id\": \"...\", \"answer\": \"...\", \"sources\": {...}, \"inline_citations\": [...], \"image_results\": [...]}\n```\n\n**Frontend:**\n```javascript\nconst response = await fetch('/api/chat/stream', {method: 'POST', body: formData});\nconst reader = response.body.getReader();\n// Read and parse each SSE line\n```"
            },
            "response": [
                ex("200 — SSE Stream", "POST", "{{base_url}}/chat/stream", "{{base_url}}", ["chat", "stream"],
                   lang="text", ct="text/event-stream",
                   body='data: {"token": "Based"}\n\ndata: {"token": " on"}\n\ndata: {"token": " the"}\n\ndata: {"token": " drilling"}\n\ndata: {"token": " report"}\n\ndata: {"done": true, "chat_id": "c1h2a3t4-abcd", "message_id": "msg_a1b2", "answer": "Based on the drilling report...", "sources": {"d0c1": {"filename": "report.pdf", "pages": [12]}}, "inline_citations": [{"source_number": 1, "document_id": "d0c1", "filename": "report.pdf", "section_title": "Summary", "pages": [12]}], "image_results": []}\n\n')
            ]
        },
        {
            "name": "List Chat Sessions",
            "event": [{"listen": "test", "script": {"exec": [
                "pm.test('Returns array', () => pm.expect(pm.response.json()).to.be.an('array'));",
                "const chats = pm.response.json();",
                "if (chats.length > 0) pm.environment.set('chat_id', chats[0].chat_id);"
            ], "type": "text/javascript"}}],
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/chat?limit=50", "host": ["{{base_url}}"], "path": ["chat"],
                        "query": [{"key": "limit", "value": "50", "description": "Max sessions (default 50)"}]},
                "description": "List all chat sessions.\n\n**Response:** `ChatSession[]`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `chat_id` | string | Session ID |\n| `category_ids` | string[]? | Linked categories |\n| `messages` | ChatMessage[] | All messages |\n| `created_at` | datetime | Created |\n| `updated_at` | datetime | Last activity |"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/chat?limit=50", "{{base_url}}", ["chat"], body=chat_sessions_list)
            ]
        },
        {
            "name": "Get Chat Session",
            "request": {
                "method": "GET",
                "url": {"raw": "{{base_url}}/chat/{{chat_id}}", "host": ["{{base_url}}"], "path": ["chat", "{{chat_id}}"]},
                "description": "Get full chat session with all messages.\n\n**Response:** `ChatSession`"
            },
            "response": [
                ex("200 — Success", "GET", "{{base_url}}/chat/{{chat_id}}", "{{base_url}}", ["chat", "{{chat_id}}"], body=chat_session),
                ex("404 — Not Found", "GET", "{{base_url}}/chat/bad_id", "{{base_url}}", ["chat", "bad_id"],
                   status="Not Found", code=404, body=N404("Chat"))
            ]
        },
        {
            "name": "Delete Chat Session",
            "request": {
                "method": "DELETE",
                "url": {"raw": "{{base_url}}/chat/{{chat_id}}", "host": ["{{base_url}}"], "path": ["chat", "{{chat_id}}"]},
                "description": "Delete a chat session and all messages.\n\n**Response:** `{message}`"
            },
            "response": [
                ex("200 — Deleted", "DELETE", "{{base_url}}/chat/{{chat_id}}", "{{base_url}}", ["chat", "{{chat_id}}"],
                   body=json.dumps({"message": "Chat c1h2a3t4-abcd-efgh-ijkl-567890 deleted"}, indent=4)),
                ex("404 — Not Found", "DELETE", "{{base_url}}/chat/bad_id", "{{base_url}}", ["chat", "bad_id"],
                   status="Not Found", code=404, body=N404("Chat"))
            ]
        }
    ]
}

# ══════════════════════════════════════════════════════════════════
# QUERY
# ══════════════════════════════════════════════════════════════════
query_resp = json.dumps({
    "query": "What are the production statistics for Q3?",
    "answer": "According to the quarterly report [Source 1, Page 5], production increased by 15% in Q3 2024.",
    "retrieved_chunks": [{
        "chunk_id": "d0c1_chunk_04", "content": "Q3 production output reached 45,000 barrels per day...",
        "score": 0.95, "section_title": "Q3 Production Summary",
        "page_start": 5, "page_end": 6,
        "image_ids": ["img_001"], "images": [], "tables": []
    }],
    "sources": ["d0c1a2b3e4f5"],
    "inline_citations": [
        {"source_number": 1, "document_id": "d0c1a2b3e4f5", "filename": "Quarterly_Report_Q3.pdf", "section_title": "Q3 Production Summary", "pages": [5]}
    ]
}, indent=4)

img_search_resp = json.dumps({
    "query_text": "production flowchart diagram",
    "has_query_image": False,
    "results": [{
        "image_id": "img_001", "document_id": "d0c1a2b3e4f5",
        "page_number": 13, "section_title": "Process Flow",
        "caption": "Figure 4.1: Production Flowchart",
        "image_path": "/static/images/d0c1a2b3e4f5/img_001.png", "score": 0.92
    }],
    "count": 1
}, indent=4)

query_section = {
    "name": "Query", "description": "Direct RAG query and image search (no chat history).",
    "item": [
        {
            "name": "RAG Query",
            "request": {
                "method": "POST", "header": json_header(),
                "body": {"mode": "raw", "raw": json.dumps({"query": "What are the production statistics for Q3?", "category_ids": ["{{category_id}}"], "top_k": 5, "include_images": True, "include_tables": True}, indent=4)},
                "url": {"raw": "{{base_url}}/query", "host": ["{{base_url}}"], "path": ["query"]},
                "description": "One-shot RAG query.\n\n**Request Body (JSON):**\n| Field | Type | Required | Default |\n|-------|------|----------|---------|\n| `query` | string | ✅ | — |\n| `category_ids` | string[] | ❌ | all |\n| `document_ids` | string[] | ❌ | all |\n| `top_k` | int (1-20) | ❌ | 5 |\n| `include_images` | bool | ❌ | true |\n| `include_tables` | bool | ❌ | true |\n\n**Response:** `QueryResponse`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `query` | string | Original query |\n| `answer` | string | AI answer |\n| `retrieved_chunks` | RetrievedChunk[] | Context chunks |\n| `sources` | string[] | Document IDs used |\n| `inline_citations` | dict[] | Structured citations |"
            },
            "response": [
                ex("200 — Success", "POST", "{{base_url}}/query", "{{base_url}}", ["query"],
                   body=query_resp, req_header=json_header(),
                   req_body=json.dumps({"query": "What are the production statistics for Q3?", "top_k": 5})),
                ex("422 — Missing Query", "POST", "{{base_url}}/query", "{{base_url}}", ["query"],
                   status="Unprocessable Entity", code=422,
                   body=json.dumps({"detail": [{"loc": ["body", "query"], "msg": "field required", "type": "value_error.missing"}]}, indent=4),
                   req_header=json_header(), req_body=json.dumps({"top_k": 5}))
            ]
        },
        {
            "name": "Image Search",
            "request": {
                "method": "POST", "header": json_header(),
                "body": {"mode": "raw", "raw": json.dumps({"query_text": "production flowchart diagram", "category_ids": ["{{category_id}}"], "top_k": 5}, indent=4)},
                "url": {"raw": "{{base_url}}/query/image-search", "host": ["{{base_url}}"], "path": ["query", "image-search"]},
                "description": "Search for images by text or image similarity.\n\n**Request Body (JSON):**\n| Field | Type | Required |\n|-------|------|----------|\n| `query_text` | string | ❌ (one of text/image required) |\n| `query_image_base64` | string | ❌ |\n| `category_ids` | string[] | ❌ |\n| `document_ids` | string[] | ❌ |\n| `top_k` | int (1-20) | ❌ (default 5) |\n\n**Response:** `ImageSearchResponse`\n\n| Field | Type | Description |\n|-------|------|-------------|\n| `query_text` | string? | Echo of input |\n| `has_query_image` | bool | Whether image was provided |\n| `results` | ImageSearchResult[] | Matched images |\n| `count` | int | Number of results |"
            },
            "response": [
                ex("200 — Success", "POST", "{{base_url}}/query/image-search", "{{base_url}}", ["query", "image-search"],
                   body=img_search_resp, req_header=json_header(),
                   req_body=json.dumps({"query_text": "production flowchart", "top_k": 5})),
                ex("422 — Empty Request", "POST", "{{base_url}}/query/image-search", "{{base_url}}", ["query", "image-search"],
                   status="Unprocessable Entity", code=422,
                   body=json.dumps({"detail": "Either query_text or query_image_base64 must be provided"}, indent=4),
                   req_header=json_header(), req_body=json.dumps({}))
            ]
        }
    ]
}

# ══════════════════════════════════════════════════════════════════
# CLIENT PROXY (mirrors all main API endpoints via port 8001)
# ══════════════════════════════════════════════════════════════════
def proxy_item(name, method, path_parts, desc, main_responses, header=None, body_obj=None, body_mode="raw", query=None):
    """Build a client proxy item that mirrors a main API endpoint."""
    url_raw = "{{client_url}}/" + "/".join(p.replace("{{category_id}}", "{{category_id}}").replace("{{document_id}}", "{{document_id}}").replace("{{batch_id}}", "{{batch_id}}").replace("{{chat_id}}", "{{chat_id}}") for p in path_parts)
    req = {"method": method, "url": {"raw": url_raw, "host": ["{{client_url}}"], "path": path_parts}, "description": f"(Proxy) {desc}"}
    if header:
        req["header"] = header
    if body_obj:
        req["body"] = {"mode": body_mode}
        if body_mode == "raw":
            req["body"]["raw"] = body_obj if isinstance(body_obj, str) else json.dumps(body_obj, indent=4)
        else:
            req["body"][body_mode] = body_obj
    if query:
        req["url"]["query"] = query
    # Build proxy responses mirroring main ones
    proxy_resps = []
    for r in main_responses:
        pr = dict(r)
        pr["originalRequest"] = dict(r["originalRequest"])
        pr["originalRequest"]["url"] = dict(r["originalRequest"]["url"])
        pr["originalRequest"]["url"]["raw"] = pr["originalRequest"]["url"]["raw"].replace("{{base_url}}", "{{client_url}}")
        pr["originalRequest"]["url"]["host"] = ["{{client_url}}"]
        proxy_resps.append(pr)
    return {"name": f"{name} (via Proxy)", "request": req, "response": proxy_resps}

client_proxy = {
    "name": "Client Proxy",
    "description": "Same endpoints via the Python Client Proxy (port 8001). Uses `{{client_url}}` base URL.\n\nThe proxy validates DTOs and forwards requests to the main API.",
    "item": [
        # Categories
        proxy_item("List Categories", "GET", ["categories"], "List all categories.", categories["item"][1]["response"]),
        proxy_item("Create Category", "POST", ["categories"], "Create a category.",
                   categories["item"][0]["response"], header=json_header(),
                   body_obj=json.dumps({"name": "New Category", "description": "Desc"})),
        proxy_item("Update Category", "PUT", ["categories", "{{category_id}}"], "Update a category.",
                   categories["item"][3]["response"], header=json_header(),
                   body_obj=json.dumps({"name": "Updated"})),
        proxy_item("Delete Category", "DELETE", ["categories", "{{category_id}}"], "Delete a category.",
                   categories["item"][4]["response"]),
        # Documents
        proxy_item("List Documents", "GET", ["documents"], "List documents.",
                   documents["item"][2]["response"],
                   query=[{"key": "category_id", "value": "{{category_id}}"}]),
        proxy_item("Get Document", "GET", ["documents", "{{document_id}}"], "Get document metadata.",
                   documents["item"][3]["response"]),
        proxy_item("Upload Documents", "POST", ["documents", "upload", "{{category_id}}"], "Upload PDFs.",
                   [documents["item"][0]["response"][0]], body_obj=ff, body_mode="formdata"),
        proxy_item("Delete Document", "DELETE", ["documents", "{{document_id}}"], "Soft delete.",
                   documents["item"][5]["response"]),
        proxy_item("Burn Document", "DELETE", ["documents", "{{document_id}}", "burn"], "Full purge.",
                   documents["item"][6]["response"]),
        proxy_item("Download Document", "GET", ["documents", "{{document_id}}", "download"], "Download PDF.",
                   documents["item"][4]["response"]),
        proxy_item("Cleanup Daily", "DELETE", ["documents", "cleanup", "daily"], "Cleanup expired.",
                   documents["item"][7]["response"]),
        # Batches
        proxy_item("Get Batch Status", "GET", ["batches", "{{batch_id}}"], "Batch snapshot.",
                   batches["item"][0]["response"]),
        proxy_item("Stream Batch Progress", "GET", ["batches", "{{batch_id}}", "progress"], "SSE progress.",
                   batches["item"][1]["response"]),
        proxy_item("Terminate Batch", "POST", ["batches", "{{batch_id}}", "terminate"], "Terminate batch.",
                   batches["item"][2]["response"]),
        # Chat
        proxy_item("Send Chat Message", "POST", ["chat"], "Send chat message.",
                   [chat_section["item"][0]["response"][0]], body_obj=chat_form, body_mode="formdata"),
        proxy_item("List Chat Sessions", "GET", ["chat"], "List sessions.",
                   chat_section["item"][2]["response"],
                   query=[{"key": "limit", "value": "50"}]),
        proxy_item("Get Chat Session", "GET", ["chat", "{{chat_id}}"], "Get session.",
                   chat_section["item"][3]["response"]),
        proxy_item("Delete Chat Session", "DELETE", ["chat", "{{chat_id}}"], "Delete session.",
                   chat_section["item"][4]["response"]),
        # Query
        proxy_item("RAG Query", "POST", ["query"], "RAG query.",
                   [query_section["item"][0]["response"][0]], header=json_header(),
                   body_obj=json.dumps({"query": "What are the key metrics?", "top_k": 5})),
        proxy_item("Image Search", "POST", ["query", "image-search"], "Image search.",
                   [query_section["item"][1]["response"][0]], header=json_header(),
                   body_obj=json.dumps({"query_text": "flowchart", "top_k": 5})),
    ]
}

# ══════════════════════════════════════════════════════════════════
# ASSEMBLE
# ══════════════════════════════════════════════════════════════════
collection = {
    "info": {
        "_postman_id": "petrorag-api-collection-v2",
        "name": "PetroRAG API",
        "description": "Complete API collection for PetroRAG — a multimodal RAG pipeline for document management, chat, and query.\n\n## Architecture\n- **Main API** (port 8000): Core backend — `{{base_url}}`\n- **Client Proxy** (port 8001): Typed proxy layer — `{{client_url}}`\n\n## Quick Start\n1. Import this collection and the environment file\n2. Start the backend: `uvicorn app.main:app --port 8000`\n3. Run requests in order: Create Category → Upload → Chat/Query\n\n## Response Schema Notes\n- All timestamps are ISO 8601 format\n- Document status: `pending` | `processing` | `completed` | `failed`\n- Errors return `{\"detail\": \"...\"}`\n- Streaming endpoints use Server-Sent Events (SSE)",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "variable": [],
    "item": [categories, documents, batches, chat_section, query_section, client_proxy]
}

output_path = r"e:\Private\Ali_Nasser\new_rag\integration\PetroRAG_API.postman_collection.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(collection, f, indent="\t", ensure_ascii=False)

print(f"Written to {output_path}")
print(f"File size: {__import__('os').path.getsize(output_path):,} bytes")

# Count endpoints and examples
total_endpoints = 0
total_examples = 0
for section in collection["item"]:
    for item in section["item"]:
        total_endpoints += 1
        total_examples += len(item.get("response", []))
print(f"Total endpoints: {total_endpoints}")
print(f"Total examples: {total_examples}")
