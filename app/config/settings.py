"""
Configuration settings for PetroRAG application.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # MongoDB Configuration
    mongodb_uri: str = Field(default="mongodb://localhost:27017", alias="MONGODB_URI")
    mongodb_database: str = Field(default="petro_rag", alias="MONGODB_DATABASE")
    
    # Redis Configuration
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    
    # GROQ API Configuration
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    qwen_text_model: str = Field(default="qwen/qwen3-32b", alias="QWEN_TEXT_MODEL")
    groq_vision_model: str = Field(default="meta-llama/llama-4-maverick-17b-128e-instruct", alias="GROQ_VISION_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=5000, alias="LLM_MAX_TOKENS")
    
    # Optional: OpenAI for vision tasks
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    
    # File Storage Paths
    upload_dir: Path = Field(default=Path("./uploads"), alias="UPLOAD_DIR")
    images_dir: Path = Field(default=Path("./extracted_images"), alias="IMAGES_DIR")
    max_image_width: int = Field(default=800, alias="MAX_IMAGE_WIDTH")
    
    # Chunking Configuration
    chunk_overlap_percentage: float = Field(default=0.20, alias="CHUNK_OVERLAP_PERCENTAGE")
    min_chunk_size: int = Field(default=100, alias="MIN_CHUNK_SIZE")
    max_chunk_size: int = Field(default=2000, alias="MAX_CHUNK_SIZE")
    
    # LlamaIndex Configuration
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", alias="EMBEDDING_MODEL")
    
    # Qdrant Configuration
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")
    qdrant_collection: str = Field(default="petro_rag_vectors", alias="QDRANT_COLLECTION")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    
    # MongoDB Collection Names
    documents_collection: str = Field(default="rag_documents", alias="DOCUMENTS_COLLECTION")
    categories_collection: str = Field(default="rag_categories", alias="CATEGORIES_COLLECTION")
    chunks_collection: str = Field(default="rag_chunks", alias="CHUNKS_COLLECTION")
    images_collection: str = Field(default="rag_images", alias="IMAGES_COLLECTION")
    tables_collection: str = Field(default="rag_tables", alias="TABLES_COLLECTION")
    chats_collection: str = Field(default="rag_chats", alias="CHATS_COLLECTION")
    
    # Chat Configuration
    chat_images_dir: Path = Field(default=Path("./chat_images"), alias="CHAT_IMAGES_DIR")
    chat_context_window: int = Field(default=10, alias="CHAT_CONTEXT_WINDOW")
    max_chat_images: int = Field(default=10, alias="MAX_CHAT_IMAGES")
    
    # Reranking Configuration
    use_reranker: bool = Field(default=True, alias="USE_RERANKER")
    rerank_model: str = Field(default="cross-encoder/ms-marco-MiniLM-L-6-v2", alias="RERANKER_MODEL")
    rerank_top_k: int = Field(default=10, alias="RERANK_TOP_K")
    similarity_threshold: float = Field(default=0.0, alias="SIMILARITY_THRESHOLD")
    top_k: int = Field(default=60, alias="TOP_K")
    
    # Logging Configuration
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_dir: Path = Field(default=Path("./logs"), alias="LOG_DIR")
    log_json: bool = Field(default=True, alias="LOG_JSON")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
    
    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.chat_images_dir.mkdir(parents=True, exist_ok=True)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings
