# Document Upload & Processing Flow

## Overview
The document upload process is asynchronous and tracked via Server-Sent Events (SSE).
1.  **Frontend**: Connects to SSE endpoint to listen for progress.
2.  **Frontend**: Uploads files to the `upload` endpoint.
3.  **Backend**: Returns a `batch_id`.
4.  **Backend**: Processes files in background (parsing -> chunking -> indexing).
5.  **Frontend**: Receives real-time updates via SSE using the `batch_id`.

## Endpoints

### 1. Upload Documents
**POST** `/api/documents/upload/{category_id}`

**Request**: `multipart/form-data`
- `files`: List of PDF files.

**Response**:
```json
[
  {
    "document_id": "doc_123",
    "category_id": "cat_1",
    "filename": "file.pdf",
    "message": "Document uploaded. Processing started.",
    "status": "pending",
    "batch_id": "batch_abc"
  }
]
```

### 2. Upload Daily Documents (Temporary)
**POST** `/api/documents/upload/daily/{category_id}`

Same as standard upload, but documents are marked for automatic deletion after 24 hours.

### 3. Stream Progress (SSE)
**GET** `/api/batches/{batch_id}/progress`

**Response (Stream)**:
```
data: {"type": "initial_state", "batch_id": "batch_abc", "files": {...}}

data: {"batch_id": "batch_abc", "filename": "file.pdf", "status": "processing", "detail": "Starting..."}
```

### 4. Get Batch Status (Snapshot)
**GET** `/api/batches/{batch_id}`

Returns the current status of all files in the batch as a standard JSON response (One-time).

**Response**:
```json
{
  "batch_id": "batch_abc",
  "files": {
    "file.pdf": {
      "status": "processing",
      "detail": "Chunking...",
      "timestamp": "2023-10-27T10:00:00"
    }
  },
  "timestamp": "2023-10-27T10:00:05"
}
```

### 5. Terminate Batch
**POST** `/api/batches/{batch_id}/terminate`

Stops processing and deletes incomplete files.

**Response**:
```json
{
  "batch_id": "batch_abc",
  "total_documents": 5,
  "kept_completed": 2,
  "deleted_incomplete": 3
}
```

### 6. Cleanup Operations
- **Delete Daily**: `DELETE /api/documents/cleanup/daily`
- **Burn Document**: `DELETE /api/documents/{document_id}/burn`

## Reference: File Statuses

### High-Level Status (Database & DTOs)
These are the statuses stored in MongoDB and returned in `DocumentUploadResponse`.
- `pending`: Uploaded, waiting for processing.
- `processing`: Generally processing (parsing, embedding, etc).
- `completed`: Successfully processed and indexed.
- `failed`: Encountered a critical error.

### Granular Status (Batch Progress / SSE)
These are detailed steps broadcasted via SSE and returned in Batch Status endpoint.
- `pending`: Waiting to start.
- `processing`: Initializing.
- `parsing`: Converting PDF to structured format.
- `extracting_images`: Extracting images from PDF.
- `chunking`: Splitting text into chunks.
- `indexing`: Indexing text chunks into Vector DB.
- `analyzing_images`: Running Vision LLM on images.
- `indexing_images`: Indexing image embeddings.
- `indexing_tables`: Indexing table embeddings.
- `completed`: Finished successfully.
- `failed`: Error occurred.
