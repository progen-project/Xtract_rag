# PetroRAG - Python Client Proxy

The **Python Client App** is a fast, robust proxy acting as a gateway and abstraction layer for the core PetroRAG API.
It utilizes FastAPI under the hood to expose strongly-typed, frontend-ready endpoints under the `/client-api` prefix.

This layer introduces intelligent request forwarding, transparent file handling, Caching strategies with `category_cache`, `document_cache`, and `chat_cache`, and handles appropriate HTTP headers mapping for correct cross-domain interactions.

## 🚀 Client Proxy Endpoints Signature Guide

The client application exposes the following RESTful API endpoints running on port `8001` by default. They generally mirror the backend application but introduce caching logic or simplified proxy mechanisms. 

### 1. Categories (`/client-api/categories`)
Cached operations for faster retrieval.
| Method | Endpoint | Description | Payloads / Content-Type |
|--------|----------|-------------|-------------------------|
| `GET` | `/client-api/categories` | List categories (Cached) | - |
| `POST` | `/client-api/categories` | Create category & Invalidate cache | Body: `CategoryCreate` |
| `PUT` | `/client-api/categories/{id}`| Update category & Invalidate | Body: `CategoryUpdate` |
| `DELETE`| `/client-api/categories/{id}`| Delete category & Invalidate | - |
| `GET` | `/client-api/categories/{id}/documents` | List docs in category (Cached) | - |

### 2. Documents (`/client-api/documents`)
Includes proxies for downloads and specialized `inline` viewing.
| Method | Endpoint | Description | Payloads / Query |
|--------|----------|-------------|------------------|
| `GET` | `/client-api/documents` | List all documents (Cached) | Query: `?category_id=opt` |
| `GET` | `/client-api/documents/{id}` | Get single document metadata | - |
| `POST` | `/client-api/documents/upload/{id}` | Form proxy file upload | Form: `files` (Array), `is_daily` (bool) |
| `DELETE` | `/client-api/documents/{id}` | Delete document | - |
| `DELETE` | `/client-api/documents/{id}/burn` | Burn document | - |
| `GET` | `/client-api/documents/{id}/download` | Download PDF file | Returns `attachment` content-disposition |
| `GET` | `/client-api/documents/{id}/view` | Inline view PDF | Returns `inline` content-disposition |
| `DELETE`| `/client-api/documents/cleanup/daily`| Trigger daily cleanup | - |

### 3. Batches (`/client-api/batches`)
Proxy endpoints for processing state.
| Method | Endpoint | Description | Format |
|--------|----------|-------------|--------|
| `GET` | `/client-api/batches/{batch_id}` | Get status | Returns dict |
| `POST` | `/client-api/batches/{batch_id}/terminate` | Terminate | Returns response |
| `GET` | `/client-api/batches/{batch_id}/progress` | Proxy SSE progress | `text/event-stream` SSE |

### 4. Chat (`/client-api/chat`)
Manages stateful chats through proxying multipart requests and JSON mapping.
| Method | Endpoint | Description | Content-Type & Payloads |
|--------|----------|-------------|-------------------------|
| `GET` | `/client-api/chat` | List user sessions (Cached) | Query: `?username=req&limit=req` |
| `GET` | `/client-api/chat/{chat_id}`| Get session (Cached) | Query: `?username=req` |
| `DELETE`| `/client-api/chat/{chat_id}`| Delete session | Query: `?username=req` |
| `POST` | `/client-api/chat` | Sync chat proxy | Form: `message`, `username`, `chat_id`, `category_ids`, `document_ids`, `images` |
| `POST` | `/client-api/chat/stream` | Async chat streaming SSE proxy | Form: Same as sync chat. Returns SSE stream. |

### 5. Query (`/client-api/query`)
| Method | Endpoint | Description | Content-Type & Payloads |
|--------|----------|-------------|-------------------------|
| `POST` | `/client-api/query` | Stateless query | Body: `QueryRequest` |
| `POST` | `/client-api/query/image-search` | Image semantic search | Body: `ImageSearchRequest` |


## 🧠 Core Features & Behaviors
- **Memory Caching**: Implements prefixed caching mechanisms to avoid straining the main API with redundant `GET` requests for categories, documents, and chat history lists.
- **Multipart Form Proxy**: Reads incoming `UploadFile` content, packs it perfectly to forward directly downstream to the main API without persisting data locally.
- **SSE Generative Forwarding**: Fully supports forwarding Server-Sent Events natively by wrapping downstream iterators (e.g. streaming LLM responses, file upload batches status!).
- **CORS Handling**: Properly manages cross-domain requests, explicitly exposing `Content-Disposition` heavily used by frontend file viewers.

## 🔧 Running Guidelines
The Proxy component typically relies on the main API. Ensure the backend API is operating before utilizing the CLI app routes.

1. Ensure the `python_client_app/core/config.py` points to the main core API endpoint. 
2. Install pip dependencies and run:
```bash
uvicorn python_client_app.main:app --host 0.0.0.0 --port 8001 --reload
```
API docs will be available at `http://localhost:8001/docs`.
