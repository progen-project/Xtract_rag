# PetroRAG - Multimodal RAG Pipeline

A comprehensive RAG (Retrieval-Augmented Generation) system for processing PDF documents with tables and figures, using LlamaIndex for indexing, Qdrant for vector search, MongoDB for metadata storage, and GROQ API with Qwen models.

## Features

- **PDF Processing**: Extract text, tables, and images from PDFs
- **Section-based Chunking**: Intelligent chunking based on document TOC with 20% overlap
- **Table Extraction**: Structured table extraction using pdfplumber
- **Image Extraction**: Figure and image extraction with caption detection
- **LlamaIndex + Qdrant**: High-performance semantic search with Qdrant vector database
- **Multimodal RAG**: Query both text and image content
- **GROQ/Qwen Integration**: Fast LLM inference with Qwen models

## Project Structure

```
new_rag/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration settings
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py          # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── pdf_parser.py       # PDF parsing logic
│   │   ├── chunker.py          # Section chunking
│   │   ├── image_extractor.py  # Image extraction
│   │   ├── indexer.py          # LlamaIndex integration
│   │   └── llm_service.py      # GROQ/Qwen integration
│   ├── database/
│   │   ├── __init__.py
│   │   └── mongodb.py          # MongoDB operations
│   └── routers/
│       ├── __init__.py
│       ├── documents.py        # Document endpoints
│       └── query.py            # Query endpoints
├── uploads/                    # PDF storage
├── extracted_images/           # Extracted images
├── requirements.txt
├── .env.example
└── README.md
```

## Setup

### 1. Install Dependencies

```bash
cd new_rag
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=petro_rag
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Start MongoDB

Ensure MongoDB is running locally or configure MongoDB Atlas URI.

### 4. Run the Application

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`

## API Endpoints

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/documents/upload` | Upload PDF for processing |
| GET | `/api/documents/` | List all documents |
| GET | `/api/documents/{id}` | Get document metadata |
| GET | `/api/documents/{id}/chunks` | Get document chunks |
| GET | `/api/documents/{id}/images` | Get document images |
| GET | `/api/documents/{id}/tables` | Get document tables |
| DELETE | `/api/documents/{id}` | Delete document |

### Query

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/query/` | RAG query |
| POST | `/api/query/multimodal` | Multimodal query |
| POST | `/api/query/similar` | Find similar chunks |
| GET | `/api/query/embedding` | Get text embedding |

## Usage Example

### Upload a Document

```bash
curl -X POST "http://localhost:8000/api/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

### Query the System

```bash
curl -X POST "http://localhost:8000/api/query/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the main findings?",
    "top_k": 5,
    "include_images": true,
    "include_tables": true
  }'
```

## Architecture

```
PDF Upload → Parser → Chunks → Index → Qdrant (vectors)
                ↓        ↓           ↘
           Images    Tables      MongoDB (metadata)
                ↓        ↓
Query → Retrieval → LLM → Response
```

## Storage

| Storage | Purpose |
|---------|---------|
| **Qdrant** | Vector embeddings for semantic search |
| **MongoDB** | Document metadata, chunks, images, tables |

## License

MIT
