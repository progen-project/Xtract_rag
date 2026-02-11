# Integration Documentation

This folder contains resources for integrating frontend and backend services with the RAG API.

## Structure

- **`dtos/`**: JSON definitions and examples of Data Transfer Objects (Request/Response bodies).
    - `document_dtos.json`: For file upload and management.
    - `chat_dtos.json`: For conversational AI features.
    - `query_dtos.json`: For search and RAG features.

- **`endpoints/`**: Markdown guides for specific workflows.
    - `document_management.md`: Uploading, tracking progress (SSE), and cleanup.
    - `chat_and_query.md`: Chatting and querying knowledge base.

## Key Features

- **Real-time Upload Tracking**: Use Server-Sent Events (SSE) to track file processing status.
- **Batch Management**: Every upload batch has a unique ID used for tracking and termination.
- **Lifecycle Management**: APIs available to terminate batches, cleanup old files, and permanently burn documents.
