"""
IMPROVED Document Controller - Passes category_id to indexer for all collections.
"""
from typing import List, Optional
from pathlib import Path
import logging
import uuid

from app.repositories import DocumentRepository, CategoryRepository, ChunkRepository
from app.schemas import (
    DocumentMetadata, 
    DocumentStatus, 
    DocumentUploadResponse,
    ExtractedImage,
    ExtractedTable
)
from app.utils.exceptions import (
    DocumentNotFoundError, 
    CategoryNotFoundError, 
    ProcessingError
)

logger = logging.getLogger(__name__)


class DocumentController:
    """
    Document controller with proper metadata handling.
    Ensures category_id is passed to all indexing operations.
    """
    
    def __init__(
        self,
        document_repo: DocumentRepository,
        category_repo: CategoryRepository,
        chunk_repo: ChunkRepository,
        indexer,
        pdf_parser,
        chunker,
        image_embedder,
        settings,
        llm_service  # Added
    ):
        self.document_repo = document_repo
        self.category_repo = category_repo
        self.chunk_repo = chunk_repo
        self.indexer = indexer
        self.pdf_parser = pdf_parser
        self.chunker = chunker
        self.image_embedder = image_embedder
        self.settings = settings
        self.llm_service = llm_service
    
    async def upload_document(
        self,
        category_id: str,
        filename: str,
        file_path: Path,
        file_size: int
    ) -> DocumentUploadResponse:
        """Upload and create document record."""
        category = await self.category_repo.get_by_id(category_id)
        if not category:
            raise CategoryNotFoundError(category_id)
        
        document_id = f"doc_{uuid.uuid4().hex[:12]}"
        document = DocumentMetadata(
            document_id=document_id,
            category_id=category_id,
            filename=filename,
            file_path=str(file_path),
            file_size=file_size,
            page_count=0,
            status=DocumentStatus.PENDING
        )
        
        await self.document_repo.create(document)
        await self.category_repo.increment_document_count(category_id, 1)
        
        return DocumentUploadResponse(
            document_id=document_id,
            category_id=category_id,
            filename=filename,
            message="Document uploaded. Processing started.",
            status=DocumentStatus.PENDING
        )
    
    async def process_document(self, document_id: str) -> None:
        """
        Process document with proper category_id handling.
        
        IMPROVED:
        - Passes category_id to indexer.index_chunks()
        - Passes category_id to indexer.index_tables()
        - Passes category_id to indexer.index_images()
        """
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        
        category_id = document.category_id
        
        try:
            await self.document_repo.update_status(
                document_id, DocumentStatus.PROCESSING
            )
            
            # Parse PDF
            parsed = self.pdf_parser.parse_document(
                document.file_path, document_id
            )
            
            sections = parsed.get("sections", [])
            tables = parsed.get("tables", [])
            
            # Extract images
            images = []
            if "document" in parsed:
                from app.services.image_extractor import get_image_extractor
                image_extractor = get_image_extractor()
                images = image_extractor.extract_images_from_docling(
                    parsed["document"], 
                    document_id,
                    save_to_disk=True,
                    category_id=category_id
                )
            
            # Create chunks
            chunks = self.chunker.chunk_sections(
                document_id=document_id,
                sections=sections,
                images=images,
                tables=tables,
                category_id=category_id
            )
            
            # Store chunks in MongoDB
            await self.chunk_repo.store_chunks(chunks)
            
            # IMPROVED: Index chunks with category_id
            self.indexer.index_chunks(chunks)
            
            # LINKING: Associate images with sections using TOC
            if images and "toc" in parsed:
                image_extractor.associate_with_sections(images, parsed["toc"])

            # LINKING: Update images with chunk_ids
            image_map = {img.image_id: img for img in images}
            for chunk in chunks:
                if chunk.image_ids:
                    for img_id in chunk.image_ids:
                        if img_id in image_map:
                            if not image_map[img_id].chunk_ids:
                                image_map[img_id].chunk_ids = []
                            image_map[img_id].chunk_ids.append(chunk.chunk_id)
            
            # Analyze images
            if images:
                logger.info(f"Analyzing {len(images)} images with vision model...")
                # Prepare context map: image_id -> list of text
                image_context_map = {}
                for chunk in chunks:
                    if chunk.image_ids:
                        for img_id in chunk.image_ids:
                            if img_id not in image_context_map:
                                image_context_map[img_id] = []
                            image_context_map[img_id].append(chunk.content)
                
                for img in images:
                    try:
                        if img.image_path:
                            # Get context text for this image
                            context_text = "\n".join(image_context_map.get(img.image_id, []))[:2000] # Limit context size
                            
                            analysis = await self.llm_service.analyze_image(
                                image=img,
                                context_text=context_text if context_text else None
                            )
                            img.analysis = analysis
                            # Use analysis as caption if missing
                            if not img.caption:
                                img.caption = analysis[:200] + "..." if len(analysis) > 200 else analysis
                    except Exception as e:
                        logger.warning(f"Failed to analyze image {img.image_id}: {e}")

            # Store and index images
            if images:
                await self.document_repo.store_images(images)
                
                # Generate embeddings
                try:
                    image_files = []
                    for img in images:
                        if img.image_path and Path(img.image_path).exists():
                            image_files.append(img.image_path)
                        else:
                            image_files.append(None)
                    
                    if any(image_files):
                        embeddings = self.image_embedder.embed_images_batch(
                            image_files
                        )
                        
                        image_dicts = []
                        for i, img in enumerate(images):
                            if i < len(embeddings) and embeddings[i] is not None:
                                image_dicts.append({
                                    "image_id": img.image_id,
                                    "page_number": img.page_number,
                                    "embedding": embeddings[i],
                                    "section_title": img.section_title or "",
                                    "caption": img.caption or "",
                                    "image_path": img.image_path,
                                    "width": img.width,
                                    "height": img.height
                                })
                        
                        if image_dicts:
                            # IMPROVED: Pass category_id
                            self.indexer.index_images(
                                image_dicts, 
                                document_id,
                                category_id
                            )
                            logger.info(f"Indexed {len(image_dicts)} images")
                
                except Exception as e:
                    logger.error(f"Image embedding failed: {e}")
            
            # Store and index tables
            if tables:
                await self.document_repo.store_tables(tables)
                
                # Prepare table dicts with all metadata
                table_dicts = []
                for t in tables:
                    table_dicts.append({
                        "table_id": t.table_id,
                        "headers": t.headers,
                        "rows": t.rows,
                        "markdown_content": t.markdown_content,
                        "page_number": t.page_number,
                        "section_title": t.section_title or "",  # Ensure populated
                    })
                
                # IMPROVED: Pass category_id
                self.indexer.index_tables(
                    table_dicts, 
                    document_id,
                    category_id
                )
            
            await self.document_repo.update_status(
                document_id, DocumentStatus.COMPLETED
            )
            logger.info(f"Document processed successfully: {document_id}")
            
        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            await self.document_repo.update_status(
                document_id, 
                DocumentStatus.FAILED, 
                str(e)
            )
            raise ProcessingError(str(e))
    
    async def get_document(self, document_id: str) -> DocumentMetadata:
        """Get a document by ID."""
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        return document
    
    async def list_documents(
        self, 
        category_id: Optional[str] = None
    ) -> List[DocumentMetadata]:
        """List documents, optionally filtered by category."""
        if category_id:
            return await self.document_repo.get_by_category(category_id)
        return await self.document_repo.get_all()
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all related data."""
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # Delete from all vector collections
        self.indexer.delete_document(document_id)
        
        # Delete chunks
        await self.chunk_repo.delete_by_document(document_id)
        
        # Delete document (includes images and tables)
        deleted = await self.document_repo.delete(document_id)
        
        if deleted:
            await self.category_repo.increment_document_count(
                document.category_id, -1
            )
        
        return deleted
    
    async def get_document_images(
        self, 
        document_id: str
    ) -> List[ExtractedImage]:
        """Get all images for a document."""
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        return await self.document_repo.get_images_by_document(document_id)
    
    async def get_document_tables(
        self, 
        document_id: str
    ) -> List[ExtractedTable]:
        """Get all tables for a document."""
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        return await self.document_repo.get_tables_by_document(document_id)