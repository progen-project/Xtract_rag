import os


class ClientConfig:
    BASE_URL = os.getenv("RAG_API_URL", "http://localhost:8080/api")
    TIMEOUT = 30.0  # seconds
    # Redis removed — caching is now handled by Nginx proxy_cache