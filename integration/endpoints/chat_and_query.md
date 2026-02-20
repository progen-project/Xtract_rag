# Chat & Query Integration

## Overview
- **Chat**: Conversational interface with memory. Supports image uploads for multimodal context.
- **Query**: Single-turn RAG (Retrieval-Augmented Generation).
- **Image Search**: Retrieve images using text or image queries.

## Endpoints

### 1. Chat Completion
**POST** `/api/chat`

**Request**: `multipart/form-data`
- `message`: (text) "Explain this chart."
- `chat_id`: (optional) Existing chat session ID.
- `images`: (optional) Image files.
- `category_ids`: (optional) Comma-separated list or JSON array.

**Response**:
```json
{
  "chat_id": "chat_123",
  "message_id": "msg_456",
  "answer": "The chart shows a 20% increase...",
  "sources": {"doc_1": [1]},
  "image_results": []
}
```

### 2. Standard Query
**POST** `/api/query`

**Request**: `application/json`
```json
{
  "query": "What are the risks?",
  "category_ids": ["cat_finance"]
}
```

**Response**:
```json
{
  "query": "What are the risks?",
  "answer": "The risks include market volatility...",
  "retrieved_chunks": [...],
  "sources": ["doc_1"]
}
```

### 3. Image Search
**POST** `/api/query/image-search`

**Request**: `application/json`
```json
{
  "query_text": "pie chart of expenses"
}
```

**Response**:
```json
{
  "results": [
    {
      "image_id": "img_1",
      "caption": "Expenses 2023",
      "image_path": "path/to/img.png",
      "score": 0.92
    }
  ]
}
```
