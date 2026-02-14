import os

class ClientConfig:
    BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000/api")
    TIMEOUT = 30.0  # seconds
