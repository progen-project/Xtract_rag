# How to Run PetroRAG Client App

This system consists of three parts that need to be running simultaneously:

1.  **Main API (Backend)**: The core logic (Port 8000).
2.  **Python Client Proxy**: The strict DTO layer (Port 8001).
3.  **Frontend (HTML/JS)**: The user interface.

## Prerequisites
- Python 3.10+
- Docker (optional, if running backend via Docker)
- Dependencies installed

## Step 1: Start Main API (Backend)
Open a terminal and run:

```bash
# If using requirements.txt
pip install -r requirements.txt

# Start API
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
*Alternatively, use Docker: `docker-compose up`*

## Step 2: Start Python Client Proxy
Open a **new** terminal window:

```bash
# Install client dependencies
pip install -r python_client_app/requirements.txt

# Start Client Proxy
uvicorn python_client_app.main:app --host 0.0.0.0 --port 8001 --reload
```
The Client API docs will be at: http://localhost:8001/docs

## Step 3: Start Frontend
Open a **third** terminal window in the `client` folder:

```bash
cd client
python -m http.server 8002
```
Access the UI at: http://localhost:8002

## Testing Flow
1.  Go to the UI (http://localhost:8002).
2.  **Create a Category** (e.g., "Test Project").
3.  **Upload a PDF**: Drag and drop a file. Watch the progress bar (SSE).
4.  **Chat**: Go to "New Chat", type a message.
5.  **Rename**: Go to Category, click "Rename".
6.  **Verify**: Check strict types in the Python Client terminal logs.
