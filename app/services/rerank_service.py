"""
Rerank service using sentence-transformers Cross-Encoder.
Improves retrieval quality by re-scoring top-k results.
"""
from typing import List, Tuple
import logging
import time
from sentence_transformers import CrossEncoder

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class RerankService:
    """
    Service for reranking search results using a Cross-Encoder.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.model = None
        self._initialized = False
    
    def initialize(self) -> None:
        """Initialize the Cross-Encoder model."""
        if self._initialized:
            return
        
        if not self.settings.use_reranker:
            logger.info("Reranker is disabled in settings")
            return
        
        try:
            logger.info(f"Loading reranker model: {self.settings.rerank_model}")
            start_time = time.time()
            self.model = CrossEncoder(self.settings.rerank_model)
            logger.info(f"Reranker initialized in {time.time() - start_time:.2f}s")
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize reranker: {e}")
            self.model = None
    
    def rerank(self, query: str, documents: List[str]) -> List[float]:
        """
        Rerank documents based on the query.
        
        Args:
            query: The search query
            documents: List of document contents/texts
            
        Returns:
            List of scores for each document
        """
        if not self._initialized or not self.model:
            # Return uniform scores if not initialized
            return [1.0] * len(documents)
        
        if not documents:
            return []
        
        try:
            # Cross-Encoder expects pairs of (query, doc)
            pairs = [[query, doc] for doc in documents]
            scores = self.model.predict(pairs)
            
            # Apply Sigmoid to normalize scores to [0, 1]
            import numpy as np
            normalized_scores = 1 / (1 + np.exp(-scores))
            
            return normalized_scores.tolist()
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            return [0.0] * len(documents)


# Global instance
rerank_service = RerankService()


def get_rerank_service() -> RerankService:
    """Dependency for getting rerank service."""
    return rerank_service
