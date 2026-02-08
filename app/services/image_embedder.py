"""
Image embedding service using BAAI/bge-vl-base multimodal embedder.
Generates embeddings for images and text in the same embedding space.
"""
from typing import List, Optional, Union
import logging
import base64
import io
from pathlib import Path
import os

from PIL import Image
import numpy as np

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class BGEVLEmbedder:
    """
    Multimodal embedding service using BAAI/bge-vl-base.
    
    This 150M parameter model generates embeddings for both images and text
    in the same embedding space, enabling:
    - Text-to-image retrieval
    - Image-to-text retrieval
    - Combined text+image queries
    """
    
    MODEL_NAME = "BAAI/BGE-VL-base"
    
    def __init__(self):
        self.settings = get_settings()
        self.model = None
        self._initialized = False
        self._embedding_dim = 512  # BGE-VL-base dimension
        self._use_fallback = False
    
    def initialize(self) -> None:
        """Initialize the BGE-VL model."""
        if self._initialized:
            return
        
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available. Using fallback text embeddings.")
            self._use_fallback = True
            self._initialized = True
            return
        
        try:
            from transformers import AutoModel
            
            logger.info(f"Loading BGE-VL model: {self.MODEL_NAME}")
            
            # Load model with trust_remote_code (required for BGE-VL)
            self.model = AutoModel.from_pretrained(
                self.MODEL_NAME, 
                trust_remote_code=True
            )
            self.model.set_processor(self.MODEL_NAME)
            self.model.eval()
            
            # Get embedding dimension from a test
            with torch.no_grad():
                test_emb = self.model.encode(text="test")
                self._embedding_dim = test_emb.shape[-1]
            
            logger.info(f"BGE-VL initialized. Embedding dimension: {self._embedding_dim}")
            self._initialized = True
            
        except ImportError as e:
            logger.warning(f"Transformers not available: {e}")
            self._use_fallback = True
            self._initialized = True
        except Exception as e:
            logger.error(f"Failed to load BGE-VL model: {e}")
            logger.warning("Using fallback text embeddings")
            self._use_fallback = True
            self._initialized = True
    
    @property
    def embedding_dim(self) -> int:
        """Get the embedding dimension."""
        return self._embedding_dim
    
    def _get_fallback_embedder(self):
        """Get fallback text embedder for when visual model isn't available."""
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        return HuggingFaceEmbedding(model_name=self.settings.embedding_model)
    
    def embed_image(
        self, 
        image: Union[Image.Image, str, bytes],
        text: Optional[str] = None
    ) -> Optional[List[float]]:
        """
        Generate embedding for an image, optionally combined with text.
        
        Args:
            image: PIL Image, file path, or bytes
            text: Optional text to combine with image (for composed queries)
            
        Returns:
            Embedding vector as list of floats
        """
        if not self._initialized:
            self.initialize()
        
        if self._use_fallback:
            # Fallback: use text description if available
            if text:
                fallback = self._get_fallback_embedder()
                return fallback.get_text_embedding(text)
            return None
        
        try:
            # Convert to file path for model
            image_path = self._prepare_image(image)
            if image_path is None:
                return None
            
            with torch.no_grad():
                if text:
                    # Combined image + text query
                    embedding = self.model.encode(images=image_path, text=text)
                else:
                    # Image only
                    embedding = self.model.encode(images=image_path)
                
                return embedding.squeeze().tolist()
                
        except Exception as e:
            logger.error(f"Error generating image embedding: {e}")
            return None
    
    def embed_text(self, text: str) -> Optional[List[float]]:
        """
        Generate text embedding in the same space as images.
        
        Args:
            text: Text query
            
        Returns:
            Embedding vector
        """
        if not self._initialized:
            self.initialize()
        
        if self._use_fallback:
            fallback = self._get_fallback_embedder()
            return fallback.get_text_embedding(text)
        
        try:
            with torch.no_grad():
                embedding = self.model.encode(text=text)
                return embedding.squeeze().tolist()
        except Exception as e:
            logger.error(f"Error generating text embedding: {e}")
            return None
    
    def embed_images_batch(
        self, 
        images: List[Union[Image.Image, str, bytes]]
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple images in batch.
        
        Args:
            images: List of images
            
        Returns:
            List of embedding vectors
        """
        if not self._initialized:
            self.initialize()
        
        if self._use_fallback:
            return [None] * len(images)
        
        results = []
        
        # Process in batches
        batch_size = 8
        for i in range(0, len(images), batch_size):
            batch = images[i:i + batch_size]
            
            image_paths = []
            for img in batch:
                path = self._prepare_image(img)
                if path:
                    image_paths.append(path)
                else:
                    image_paths.append(None)
            
            # Filter valid paths
            valid_paths = [p for p in image_paths if p is not None]
            
            if not valid_paths:
                results.extend([None] * len(batch))
                continue
            
            try:
                with torch.no_grad():
                    embeddings = self.model.encode(images=valid_paths)
                    
                    # Map back to original order
                    valid_idx = 0
                    for path in image_paths:
                        if path is not None:
                            results.append(embeddings[valid_idx].tolist())
                            valid_idx += 1
                        else:
                            results.append(None)
                            
            except Exception as e:
                logger.error(f"Error in batch embedding: {e}")
                results.extend([None] * len(batch))
        
        return results
    
    def _prepare_image(
        self, 
        image: Union[Image.Image, str, bytes]
    ) -> Optional[str]:
        """
        Prepare image for the model (convert to file path).
        BGE-VL accepts file paths directly.
        """
        try:
            if isinstance(image, str):
                # Fix: Check length to avoid [Errno 36] File name too long
                is_valid_path = False
                if len(image) < 1024:  # Reasonable max path length
                    try:
                        if Path(image).exists():
                            is_valid_path = True
                    except OSError:
                        pass
                
                if is_valid_path:
                    return image
                else:
                    # Try as base64
                    try:
                        img_bytes = base64.b64decode(image)
                        pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
                    except Exception:
                        return None
            elif isinstance(image, bytes):
                pil_img = Image.open(io.BytesIO(image)).convert("RGB")
            elif isinstance(image, Image.Image):
                pil_img = image.convert("RGB")
            else:
                logger.warning(f"Unknown image type: {type(image)}")
                return None
            
            # Save to temp file
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                pil_img.save(f.name)
                return f.name
                
        except Exception as e:
            logger.error(f"Error preparing image: {e}")
            return None
    
    def compute_similarity(
        self, 
        embedding1: List[float], 
        embedding2: List[float]
    ) -> float:
        """Compute cosine similarity between two embeddings."""
        arr1 = np.array(embedding1)
        arr2 = np.array(embedding2)
        
        dot_product = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))


# Global image embedder instance
image_embedder = BGEVLEmbedder()


def get_image_embedder() -> BGEVLEmbedder:
    """Dependency for getting image embedder."""
    return image_embedder
