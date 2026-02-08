"""
IMPROVED Indexer - Clean implementation with proper metadata handling.
"""
from llama_index.core import (
    VectorStoreIndex,
    StorageContext,
    Settings as LlamaSettings
)
from llama_index.core.schema import TextNode
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore

from qdrant_client import QdrantClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, SparseVectorParams, SparseIndexParams, SparseVector
from fastembed import SparseTextEmbedding
from typing import List, Optional
import logging

from app.config.settings import get_settings
from app.schemas import Chunk, RetrievedChunk

logger = logging.getLogger(__name__)


class Indexer:
    """
    Document indexing service with Qdrant vector store.
    Manages 3 collections: text chunks, tables, images.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.embed_model: Optional[HuggingFaceEmbedding] = None
        self.sparse_embed_model: Optional[SparseTextEmbedding] = None
        self.qdrant_client: Optional[QdrantClient] = None
        self.vector_store: Optional[QdrantVectorStore] = None
        self.index: Optional[VectorStoreIndex] = None
        self._initialized = False
        self._embedding_dim = 384
    
    def initialize(self) -> None:
        """Initialize embedding model and Qdrant connection."""
        if self._initialized:
            return
        
        logger.info(f"Loading embedding model: {self.settings.embedding_model}")
        self.embed_model = HuggingFaceEmbedding(
            model_name=self.settings.embedding_model
        )
        
        logger.info("Loading sparse embedding model: Qdrant/bm25")
        self.sparse_embed_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        
        test_embedding = self.embed_model.get_text_embedding("test")
        self._embedding_dim = len(test_embedding)
        logger.info(f"Embedding dimension: {self._embedding_dim}")
        
        LlamaSettings.embed_model = self.embed_model
        LlamaSettings.chunk_size = self.settings.max_chunk_size
        LlamaSettings.chunk_overlap = int(
            self.settings.max_chunk_size * self.settings.chunk_overlap_percentage
        )
        
        try:
            if self.settings.qdrant_api_key:
                self.qdrant_client = QdrantClient(
                    url=self.settings.qdrant_url,
                    api_key=self.settings.qdrant_api_key
                )
            else:
                self.qdrant_client = QdrantClient(url=self.settings.qdrant_url)
            
            self._ensure_collections()
            
            try:
                self.vector_store = QdrantVectorStore(
                    client=self.qdrant_client,
                    collection_name=self.settings.qdrant_collection
                )
                logger.info(f"Initialized Qdrant: {self.settings.qdrant_collection}")
            except Exception as vs_error:
                logger.warning(f"QdrantVectorStore init failed: {vs_error}")
                self.vector_store = None
            
        except Exception as e:
            logger.warning(f"Qdrant connection failed: {e}")
            self.qdrant_client = None
            self.vector_store = None
        
        self._initialized = True
    
    def _ensure_collections(self) -> None:
        """Create Qdrant collections if they don't exist."""
        import httpx
        
        try:
            response = httpx.get(f"{self.settings.qdrant_url}/collections")
            collection_data = response.json()
            collection_names = [
                c["name"] for c in collection_data.get("result", {}).get("collections", [])
            ]
        except Exception as e:
            logger.warning(f"Could not get collections: {e}")
            collection_names = []
        
        # Text chunks collection (Hybrid)
        if self.settings.qdrant_collection not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config={
                    "dense": VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(
                            on_disk=False,
                        )
                    )
                }
            )
            logger.info(f"Created hybrid collection: {self.settings.qdrant_collection}")
        
        # Images collection
        image_collection = f"{self.settings.qdrant_collection}_images"
        image_dim = 512  # BGE-VL-base dimension
        
        if image_collection in collection_names:
            try:
                resp = httpx.get(
                    f"{self.settings.qdrant_url}/collections/{image_collection}"
                )
                info = resp.json()
                existing_dim = (
                    info.get("result", {})
                    .get("config", {})
                    .get("params", {})
                    .get("vectors", {})
                    .get("size", 0)
                )
                if existing_dim != image_dim:
                    logger.warning(
                        f"Image collection wrong dimension ({existing_dim}), recreating..."
                    )
                    httpx.delete(
                        f"{self.settings.qdrant_url}/collections/{image_collection}"
                    )
                    collection_names.remove(image_collection)
            except:
                pass
        
        if image_collection not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=image_collection,
                vectors_config=VectorParams(size=image_dim, distance=Distance.COSINE)
            )
            logger.info(f"Created collection: {image_collection}")
        
        # Tables collection (Hybrid)
        table_collection = f"{self.settings.qdrant_collection}_tables"
        if table_collection not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=table_collection,
                vectors_config={
                    "dense": VectorParams(
                        size=self._embedding_dim,
                        distance=Distance.COSINE
                    )
                },
                sparse_vectors_config={
                    "sparse": SparseVectorParams(
                        index=SparseIndexParams(
                            on_disk=False,
                        )
                    )
                }
            )
            logger.info(f"Created hybrid collection: {table_collection}")
    
    # ============================================
    # TEXT CHUNKS INDEXING
    # ============================================
    
    def index_chunks(self, chunks: List[Chunk]) -> str:
        """
        Index text chunks (tables already removed from content).
        
        Metadata stored:
        - chunk_id, document_id, category_id
        - section_title, page_start, page_end
        - image_ids (comma-separated string)
        - table_ids (comma-separated string)
        - has_images, has_tables (booleans)
        
        REMOVED: tables_removed flag (unnecessary)
        """
        if not self._initialized:
            self.initialize()
        
        if not chunks:
            raise ValueError("No chunks to index")
        
        document_id = chunks[0].document_id
        category_id = chunks[0].category_id
        
        if self.qdrant_client:
            points = []
            
            for chunk in chunks:
                embedding = self.embed_model.get_text_embedding(chunk.content)
                
                # Prepare IDs as comma-separated strings
                image_ids_str = ",".join(chunk.image_ids) if chunk.image_ids else ""
                table_ids_str = ",".join(chunk.table_ids) if chunk.table_ids else ""
                
                # Generate sparse embedding
                sparse_gen = list(self.sparse_embed_model.embed([chunk.content]))[0]
                sparse_vector = SparseVector(
                    indices=sparse_gen.indices.tolist(),
                    values=sparse_gen.values.tolist()
                )

                point = PointStruct(
                    id=abs(hash(chunk.chunk_id)) % (2**63),
                    vector={
                        "dense": embedding,
                        "sparse": sparse_vector
                    },
                    payload={
                        "chunk_id": chunk.chunk_id,
                        "document_id": document_id,
                        "category_id": category_id,
                        "text": chunk.content,
                        "section_title": chunk.section_title,
                        "page_start": chunk.page_start,
                        "page_end": chunk.page_end,
                        "image_ids": image_ids_str,
                        "table_ids": table_ids_str,
                        "has_images": len(chunk.image_ids) > 0,
                        "has_tables": len(chunk.table_ids) > 0,
                    }
                )
                points.append(point)
            
            # Batch upsert
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.qdrant_client.upsert(
                    collection_name=self.settings.qdrant_collection,
                    points=batch
                )
            
            logger.info(f"Indexed {len(points)} chunks for {document_id}")
            
            if self.vector_store:
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store,
                    embed_model=self.embed_model
                )
        else:
            nodes = self._create_nodes_from_chunks(chunks)
            self.index = VectorStoreIndex(nodes, embed_model=self.embed_model)
            logger.info(f"Indexed {len(nodes)} chunks in memory")
        
        return document_id
    
    def _create_nodes_from_chunks(self, chunks: List[Chunk]) -> List[TextNode]:
        """Create LlamaIndex TextNodes from chunks."""
        nodes = []
        
        for chunk in chunks:
            content = chunk.content
            if chunk.overlap_start:
                content = f"[Context:] {chunk.overlap_start}\n\n{chunk.content}"
            
            metadata = {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "category_id": chunk.category_id,
                "section_title": chunk.section_title,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "chunk_index": chunk.chunk_index,
                "has_images": len(chunk.image_ids) > 0,
                "has_tables": len(chunk.table_ids) > 0,
                "image_ids": ",".join(chunk.image_ids) if chunk.image_ids else "",
                "table_ids": ",".join(chunk.table_ids) if chunk.table_ids else "",
            }
            
            if chunk.metadata:
                metadata.update(chunk.metadata)
            
            node = TextNode(
                text=content,
                id_=chunk.chunk_id,
                metadata=metadata,
                excluded_embed_metadata_keys=[
                    "chunk_id", "image_ids", "table_ids", "category_id"
                ],
                excluded_llm_metadata_keys=[
                    "chunk_id", "image_ids", "table_ids", "category_id"
                ]
            )
            nodes.append(node)
        
        return nodes
    
    # ============================================
    # TABLES INDEXING - FIXED
    # ============================================
    
    def index_tables(
        self,
        tables: List[dict],
        document_id: str,
        category_id: str = ""
    ) -> int:
        """
        Index tables into separate collection.
        
        FIXED:
        1. section_title always stored (not None)
        2. category_id added for filtering
        """
        if not self._initialized:
            self.initialize()
        
        if not self.qdrant_client or not tables:
            return 0
        
        table_collection = f"{self.settings.qdrant_collection}_tables"
        points = []
        
        for table in tables:
            table_text = self._table_to_text(table)
            if not table_text:
                continue
            
            embedding = self.embed_model.get_text_embedding(table_text)
            
            markdown = table.get("markdown_content") or table.get("markdown", "")
            
            row_count = table.get("row_count", 0)
            if row_count == 0 and "rows" in table:
                row_count = len(table["rows"])
            
            # CRITICAL FIX: section_title always populated
            section_title = table.get("section_title", "")
            if not section_title and "section" in table:
                section_title = table["section"]
            
            # Generate sparse embedding
            sparse_gen = list(self.sparse_embed_model.embed([table_text]))[0]
            sparse_vector = SparseVector(
                indices=sparse_gen.indices.tolist(),
                values=sparse_gen.values.tolist()
            )
            
            point = PointStruct(
                id=abs(hash(table.get("table_id", str(len(points))))) % (2**63),
                vector={
                    "dense": embedding,
                    "sparse": sparse_vector
                },
                payload={
                    "table_id": table.get("table_id", ""),
                    "document_id": document_id,
                    "category_id": category_id,  # ADDED
                    "page_number": table.get("page_number", 0),
                    "section_title": section_title,  # FIXED
                    "headers": table.get("headers", []),
                    "row_count": row_count,
                    "markdown": markdown,
                }
            )
            points.append(point)
        
        if points:
            self.qdrant_client.upsert(
                collection_name=table_collection,
                points=points
            )
            logger.info(f"Indexed {len(points)} tables for {document_id}")
        
        return len(points)
    
    def _table_to_text(self, table: dict) -> str:
        """Convert table to searchable text."""
        parts = []
        
        if table.get("section_title"):
            parts.append(f"Section: {table['section_title']}")
        
        headers = table.get("headers", [])
        if headers:
            parts.append("Headers: " + ", ".join(str(h) for h in headers))
        
        markdown = table.get("markdown_content") or table.get("markdown")
        if markdown:
            parts.append(markdown)
        
        return "\n".join(parts)[:2000]
    
    # ============================================
    # IMAGES INDEXING
    # ============================================
    
    def index_images(
        self,
        images: List[dict],
        document_id: str,
        category_id: str = ""
    ) -> int:
        """Index images with multimodal embeddings."""
        if not self._initialized:
            self.initialize()
        
        if not self.qdrant_client or not images:
            return 0
        
        image_collection = f"{self.settings.qdrant_collection}_images"
        points = []
        
        for img in images:
            if not img.get("embedding"):
                continue
            
            point = PointStruct(
                id=hash(img["image_id"]) % (2**63),
                vector=img["embedding"],
                payload={
                    "image_id": img["image_id"],
                    "document_id": document_id,
                    "category_id": category_id,  # ADDED
                    "page_number": img.get("page_number", 0),
                    "section_title": img.get("section_title", ""),
                    "caption": img.get("caption", ""),
                    "image_path": img.get("image_path", ""),
                    "width": img.get("width", 0),
                    "height": img.get("height", 0),
                }
            )
            points.append(point)
        
        if points:
            self.qdrant_client.upsert(
                collection_name=image_collection,
                points=points
            )
            logger.info(f"Indexed {len(points)} images for {document_id}")
        
        return len(points)
    
    # ============================================
    # QUERYING
    # ============================================
    
    def query(
        self,
        query_text: str,
        top_k: int = 5,
        document_ids: Optional[List[str]] = None,
        category_ids: Optional[List[str]] = None
    ) -> List[RetrievedChunk]:
        """Query text chunks collection."""
        if not self._initialized:
            self.initialize()
        
        if not self.index:
            if self.vector_store:
                self.index = VectorStoreIndex.from_vector_store(
                    vector_store=self.vector_store,
                    embed_model=self.embed_model
                )
            else:
                raise ValueError("Index not initialized")
        
        filter_conditions = []
        
        if document_ids:
            from qdrant_client.models import FieldCondition, MatchAny
            filter_conditions.append(
                FieldCondition(
                    key="document_id",
                    match=MatchAny(any=document_ids)
                )
            )
        
        if category_ids:
            from qdrant_client.models import FieldCondition, MatchAny
            filter_conditions.append(
                FieldCondition(
                    key="category_id",
                    match=MatchAny(any=category_ids)
                )
            )
        
        if filter_conditions:
            from qdrant_client.models import Filter
            qdrant_filter = Filter(must=filter_conditions)
            retriever = self.index.as_retriever(
                similarity_top_k=top_k,
                vector_store_kwargs={"qdrant_filters": qdrant_filter}
            )
        else:
            retriever = self.index.as_retriever(similarity_top_k=top_k)
        
        nodes_with_scores = retriever.retrieve(query_text)
        
        results = []
        for node_score in nodes_with_scores:
            node = node_score.node
            metadata = node.metadata
            
            retrieved = RetrievedChunk(
                chunk_id=metadata.get("chunk_id", node.node_id),
                content=node.text,
                score=node_score.score or 0.0,
                section_title=metadata.get("section_title", ""),
                page_start=metadata.get("page_start", 0),
                page_end=metadata.get("page_end", 0),
                images=[],
                tables=[]
            )
            results.append(retrieved)
        
        logger.info(f"Query returned {len(results)} results")
        return results
    
    # ============================================
    # DELETION
    # ============================================
    
    def delete_document(self, document_id: str) -> bool:
        """Delete all vectors for a document from all collections."""
        if not self.qdrant_client:
            return False
        
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        filter_obj = Filter(
            must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
        )
        
        try:
            # Delete from text chunks
            self.qdrant_client.delete(
                collection_name=self.settings.qdrant_collection,
                points_selector=filter_obj
            )
            
            # Delete from tables
            table_collection = f"{self.settings.qdrant_collection}_tables"
            self.qdrant_client.delete(
                collection_name=table_collection,
                points_selector=filter_obj
            )
            
            # Delete from images
            image_collection = f"{self.settings.qdrant_collection}_images"
            self.qdrant_client.delete(
                collection_name=image_collection,
                points_selector=filter_obj
            )
            
            logger.info(f"Deleted all vectors for document {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            return False


# Global instance
indexer = Indexer()


def get_indexer() -> Indexer:
    """Get indexer instance."""
    return indexer