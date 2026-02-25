"""
IMPROVED Document Controller - Passes category_id to indexer for all collections.
"""
from typing import List, Optional, Dict
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
        llm_service,
        status_manager  # Added
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
        self.status_manager = status_manager
    
    async def upload_document(
        self,
        category_id: str,
        filename: str,
        file_path: Path,
        file_size: int,
        batch_id: Optional[str] = None,
        is_daily: bool = False
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
            status=DocumentStatus.PENDING,
            batch_id=batch_id,
            is_daily=is_daily
        )
        
        await self.document_repo.create(document)
        await self.category_repo.increment_document_count(category_id, 1)
        
        # Update status if batch_id provided
        if batch_id:
            await self.status_manager.update_file_status(
                batch_id, filename, "pending", "Document uploaded. Waiting for processing."
            )
        
        return DocumentUploadResponse(
            document_id=document_id,
            category_id=category_id,
            filename=filename,
            message="Document uploaded. Processing started.",
            status=DocumentStatus.PENDING,
            batch_id=batch_id
        )
    
    async def process_document(self, document_id: str, batch_id: Optional[str] = None) -> None:
        """
        Process document with proper category_id handling.
        """
        try:
            document = await self.document_repo.get_by_id(document_id)
            if not document:
                logger.error(f"Document not found during processing: {document_id}")
                if batch_id:
                     await self.status_manager.update_file_status(
                        batch_id, "unknown", "failed", f"Document {document_id} not found."
                    )
                return

            category_id = document.category_id
            filename = document.filename
        except Exception as e:
            logger.error(f"Error fetching document {document_id}: {e}")
            return
        
        try:
            await self.document_repo.update_status(
                document_id, DocumentStatus.PROCESSING
            )
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "processing", "Starting processing..."
                )
            
            # Parse PDF
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "parsing", "Parsing PDF document..."
                )
            
            # Offload blocking PDF parsing
            from starlette.concurrency import run_in_threadpool
            parsed = await run_in_threadpool(
                self.pdf_parser.parse_document,
                document.file_path, 
                document_id
            )
            
            sections = parsed.get("sections", [])
            tables = parsed.get("tables", [])
            
            # Extract images
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "extracting_images", "Extracting images from document..."
                )

            images = []
            if "document" in parsed:
                from app.services.image_extractor import get_image_extractor
                image_extractor = get_image_extractor()
                # Offload image extraction (likely file I/O and processing)
                images = await run_in_threadpool(
                    image_extractor.extract_images_from_docling,
                    parsed["document"], 
                    document_id,
                    True, # save_to_disk
                    category_id
                )
            
            # Create chunks
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "chunking", f"Chunking {len(sections)} sections..."
                )

            # Offload chunking
            chunks = await run_in_threadpool(
                self.chunker.chunk_sections,
                document_id=document_id,
                sections=sections,
                images=images,
                tables=tables,
                category_id=category_id
            )
            
            # Store chunks in MongoDB
            await self.chunk_repo.store_chunks(chunks)
            
            # IMPROVED: Index chunks with category_id
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "indexing", f"Indexing {len(chunks)} chunks..."
                )
            
            # Offload indexing (likely sync network calls to Qdrant if using standard client)
            await run_in_threadpool(
                self.indexer.index_chunks,
                chunks
            )
            
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
                if batch_id:
                    await self.status_manager.update_file_status(
                        batch_id, filename, "analyzing_images", f"Analyzing {len(images)} images..."
                    )
                
                logger.info(f"Analyzing {len(images)} images with vision model (concurrent)...")
                # Prepare context map: image_id -> list of text
                image_context_map = {}
                for chunk in chunks:
                    if chunk.image_ids:
                        for img_id in chunk.image_ids:
                            if img_id not in image_context_map:
                                image_context_map[img_id] = []
                            image_context_map[img_id].append(chunk.content)
                
                async def _analyze_single_image(img):
                    """Analyze a single image — designed for concurrent execution."""
                    try:
                        if img.image_path:
                            context_text = "\n".join(image_context_map.get(img.image_id, []))[:2000]
                            analysis = await self.llm_service.analyze_image(
                                image=img,
                                context_text=context_text if context_text else None
                            )
                            img.analysis = analysis
                            if not img.caption:
                                img.caption = analysis[:200] + "..." if len(analysis) > 200 else analysis
                    except Exception as e:
                        logger.warning(f"Failed to analyze image {img.image_id}: {e}")
                
                import asyncio
                await asyncio.gather(*(_analyze_single_image(img) for img in images))

            # Store and index images
            if images:
                if batch_id:
                    await self.status_manager.update_file_status(
                        batch_id, filename, "indexing_images", f"Indexing {len(images)} images..."
                    )

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
                        # Offload heavy embedding generation
                        embeddings = await run_in_threadpool(
                            self.image_embedder.embed_images_batch,
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
                            await run_in_threadpool(
                                self.indexer.index_images,
                                image_dicts, 
                                document_id,
                                category_id
                            )
                            logger.info(f"Indexed {len(image_dicts)} images")
                
                except Exception as e:
                    logger.error(f"Image embedding failed: {e}")
            
            # Store and index tables
            if tables:
                if batch_id:
                    await self.status_manager.update_file_status(
                        batch_id, filename, "indexing_tables", f"Indexing {len(tables)} tables..."
                    )
                
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
                await run_in_threadpool(
                    self.indexer.index_tables,
                    table_dicts, 
                    document_id,
                    category_id
                )
            
            await self.document_repo.update_status(
                document_id, DocumentStatus.COMPLETED
            )
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "completed", "Processing completed successfully."
                )
            
            logger.info(f"Document processed successfully: {document_id}")
            
        except Exception as e:
            logger.error(f"Document processing failed: {e}")
            await self.document_repo.update_status(
                document_id, 
                DocumentStatus.FAILED, 
                str(e)
            )
            if batch_id:
                await self.status_manager.update_file_status(
                    batch_id, filename, "failed", f"Processing failed: {str(e)}"
                )
            raise ProcessingError(str(e))
            
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
    
    async def terminate_batch(self, batch_id: str) -> Dict[str, int]:
        """
        Terminate a batch upload.
        Keeps completed documents, deletes everything else.
        """
        documents = await self.document_repo.get_by_batch_id(batch_id)
        
        deleted_count = 0
        kept_count = 0
        
        for doc in documents:
            if doc.status == DocumentStatus.COMPLETED:
                kept_count += 1
                continue
                
            # Delete non-completed documents
            # This handles pending, processing, failed
            try:
                await self.delete_document(doc.document_id)
                # Also try to clean up the file from disk if it exists
                if doc.file_path and Path(doc.file_path).exists():
                    try:
                        Path(doc.file_path).unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete file {doc.file_path}: {e}")
                        
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to delete document {doc.document_id} during termination: {e}")
                
        return {
            "batch_id": batch_id,
            "total_documents": len(documents),
            "kept_completed": kept_count,
            "deleted_incomplete": deleted_count
        }

    async def cleanup_daily_uploads(self) -> Dict[str, int]:
        """
        Delete 'daily' documents older than 24 hours.
        Removes from MongoDB, Qdrant, and disk (via delete_document).
        """
        from datetime import datetime, timedelta
        
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        documents = await self.document_repo.get_older_than(cutoff_time, is_daily=True)
        
        deleted_count = 0
        failed_count = 0
        
        for doc in documents:
            try:
                await self.delete_document(doc.document_id)
                
                # Ensure file is deleted from disk
                if doc.file_path and Path(doc.file_path).exists():
                    try:
                        Path(doc.file_path).unlink()
                    except Exception as e:
                        logger.warning(f"Failed to delete file {doc.file_path}: {e}")
                        
                deleted_count += 1
            except Exception as e:
                logger.error(f"Failed to cleanup document {doc.document_id}: {e}")
                failed_count += 1
                
        # Also clean up empty directories in upload folder?
        # Maybe safer to just stick to documents for now.
        
        return {
            "deleted_documents": deleted_count,
            "failed_deletions": failed_count,
            "cutoff_time": cutoff_time.isoformat()
        }

    async def burn_document(self, document_id: str) -> bool:
        """
        Completely remove a document and all traces.
        Alias for delete_document but semantically stronger as requested.
        """
        # Checks if document exists first in delete_document
        deleted = await self.delete_document(document_id)
        if deleted:
             # Double check file deletion
             # delete_document already handles vector store and db
             # We just ensure file on disk is gone too if delete_document didn't catch it
             # (delete_document currently doesn't explicit unlink the source file, only repo delete)
             # Wait, repo.delete doesn't delete the source file on disk!
             # I need to add that here or in delete_document.
             # Let's add it here to be safe and separate.
             
             # Actually I should fetch doc before deleting to get path
             pass 
             
        return deleted
        
    # Override delete_document to also delete file on disk? 
    # The existing delete_document just calls repo.delete.
    # Repo.delete deletes from collections.
    # It does NOT delete the source PDF.
    # I should update delete_document to handle file deletion too.
    
    async def delete_document(self, document_id: str) -> bool:
        """Delete a document and all related data, including source file."""
        document = await self.document_repo.get_by_id(document_id)
        if not document:
            raise DocumentNotFoundError(document_id)
        
        # Delete from all vector collections
        try:
            from starlette.concurrency import run_in_threadpool
            await run_in_threadpool(self.indexer.delete_document, document_id)
        except Exception as e:
            logger.warning(f"Failed to delete from vector store: {e}")
        
        # Delete chunks
        await self.chunk_repo.delete_by_document(document_id)
        
        # Delete document (includes images and tables)
        deleted = await self.document_repo.delete(document_id)
        
        if deleted:
            await self.category_repo.increment_document_count(
                document.category_id, -1
            )
            
            # Delete physical file
            if document.file_path and Path(document.file_path).exists():
                try:
                    Path(document.file_path).unlink()
                    logger.info(f"Deleted file: {document.file_path}")
                except Exception as e:
                    logger.warning(f"Failed to delete file {document.file_path}: {e}")
        
        return deleted