import os

class ClientConfig:
    BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8000/api")
    REDIS_URL = os.getenv("REDIS_URL", "redis://172.23.80.1:6379/0")
    TIMEOUT = 30.0  # seconds
