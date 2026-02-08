"""
Retrieval orchestrator - fetches actual objects based on search result IDs.
Handles loading tables and images from MongoDB and filesystem.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from app.schemas import ExtractedTable, ExtractedImage

logger = logging.getLogger(__name__)


class RetrievalOrchestrator:
    """
    Orchestrates retrieval of actual content objects.
    Takes search results with IDs and returns full objects.
    """
    
    def __init__(self, document_repo):
        self.document_repo = document_repo
    
    async def retrieve_tables(
        self,
        table_ids: List[str],
        document_id: Optional[str] = None
    ) -> List[ExtractedTable]:
        """
        Retrieve table objects by IDs.
        
        Args:
            table_ids: List of table IDs to fetch
            document_id: Optional document ID for optimization
            
        Returns:
            List of ExtractedTable objects
        """
        if not table_ids:
            return []
        
        tables = []
        
        try:
            if document_id:
                # Optimization: get all tables for document at once
                all_tables = await self.document_repo.get_tables_by_document(
                    document_id
                )
                
                # Filter to requested IDs
                table_map = {t.table_id: t for t in all_tables}
                tables = [
                    table_map[tid] for tid in table_ids
                    if tid in table_map
                ]
            else:
                # Fetch individually (slower)
                for table_id in table_ids:
                    # Extract document_id from table_id format: {doc_id}_table_{idx}
                    parts = table_id.split("_table_")
                    if len(parts) == 2:
                        doc_id = parts[0]
                        doc_tables = await self.document_repo.get_tables_by_document(
                            doc_id
                        )
                        for t in doc_tables:
                            if t.table_id == table_id:
                                tables.append(t)
                                break
            
            logger.info(f"Retrieved {len(tables)}/{len(table_ids)} tables")
            
        except Exception as e:
            logger.error(f"Error retrieving tables: {e}")
        
        return tables
    
    async def retrieve_images(
        self,
        image_ids: List[str],
        document_id: Optional[str] = None,
        verify_files: bool = True
    ) -> List[ExtractedImage]:
        """
        Retrieve image objects by IDs.
        
        Args:
            image_ids: List of image IDs to fetch
            document_id: Optional document ID for optimization
            verify_files: Check if image files exist on disk
            
        Returns:
            List of ExtractedImage objects with valid paths
        """
        if not image_ids:
            return []
        
        images = []
        
        try:
            if document_id:
                # Get all images for document
                all_images = await self.document_repo.get_images_by_document(
                    document_id
                )
                
                image_map = {img.image_id: img for img in all_images}
                images = [
                    image_map[iid] for iid in image_ids
                    if iid in image_map
                ]
            else:
                # Fetch individually
                for image_id in image_ids:
                    img = await self.document_repo.get_image_by_id(image_id)
                    if img:
                        images.append(img)
            
            # Verify files exist if requested
            if verify_files:
                valid_images = []
                for img in images:
                    if img.image_path and Path(img.image_path).exists():
                        valid_images.append(img)
                    else:
                        logger.warning(
                            f"Image file not found: {img.image_id} -> {img.image_path}"
                        )
                
                logger.info(
                    f"Retrieved {len(valid_images)}/{len(image_ids)} images "
                    f"({len(images) - len(valid_images)} missing files)"
                )
                return valid_images
            
            logger.info(f"Retrieved {len(images)}/{len(image_ids)} images")
            
        except Exception as e:
            logger.error(f"Error retrieving images: {e}")
        
        return images
    
    async def enrich_search_results(
        self,
        search_results: List[Any]  # List[SearchResult]
    ) -> Dict[str, Any]:
        """
        Enrich search results by fetching associated tables and images.
        
        Args:
            search_results: List of SearchResult objects
            
        Returns:
            Dict with:
                - text_chunks: List of text results
                - tables: List of table objects
                - images: List of image objects with paths
        """
        all_table_ids = set()
        all_image_ids = set()
        text_chunks = []
        
        # Collect all IDs from search results
        for result in search_results:
            if result.source_type == "text":
                text_chunks.append(result)
                all_table_ids.update(result.related_table_ids)
                all_image_ids.update(result.related_image_ids)
            elif result.source_type == "table":
                if result.table_id:
                    all_table_ids.add(result.table_id)
            elif result.source_type == "image":
                if result.image_id:
                    all_image_ids.add(result.image_id)
        
        # Fetch actual objects
        tables = await self.retrieve_tables(list(all_table_ids))
        images = await self.retrieve_images(list(all_image_ids))
        
        return {
            "text_chunks": text_chunks,
            "tables": tables,
            "images": images,
            "table_count": len(tables),
            "image_count": len(images)
        }
    
    async def get_image_paths(
        self,
        image_ids: List[str],
        max_images: Optional[int] = None
    ) -> List[str]:
        """
        Get list of valid image file paths.
        
        Args:
            image_ids: Image IDs to fetch
            max_images: Optional limit on number of images
            
        Returns:
            List of file paths (verified to exist)
        """
        images = await self.retrieve_images(image_ids, verify_files=True)
        
        paths = [img.image_path for img in images if img.image_path]
        
        if max_images and len(paths) > max_images:
            paths = paths[:max_images]
        
        return paths
