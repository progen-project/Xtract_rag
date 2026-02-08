"""
Image extraction service using IBM Docling.
Extracts figures/images from PDFs using Docling's picture detection.
"""
from pathlib import Path
from typing import List, Optional, Dict
import logging
import base64
import io
from PIL import Image

from app.config.settings import get_settings
from app.schemas import ExtractedImage, TOCEntry

logger = logging.getLogger(__name__)


class DoclingImageExtractor:
    """
    Extracts images/figures from PDF documents using Docling.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.min_width = 100
        self.min_height = 100
    
    def extract_images_from_docling(
        self, 
        docling_doc,
        document_id: str,
        save_to_disk: bool = True,
        category_id: str = ""
    ) -> List[ExtractedImage]:
        """
        Extract images from a Docling document object.
        """
        images = []
        
        try:
            # Get all picture items from the document
            img_idx = 0
            
            for item, level in docling_doc.iterate_items():
                # Check label - Docling uses different label names
                label = None
                if hasattr(item, 'label'):
                    label = str(item.label)
                
                # Look for picture/figure labels
                if label is None:
                    continue
                
                # Docling labels can be: PICTURE, FIGURE, or in value form
                is_picture = any(x in label.upper() for x in ['PICTURE', 'FIGURE', 'IMAGE'])
                
                if not is_picture:
                    continue
                
                # Get page number
                page = 1
                if hasattr(item, 'prov') and item.prov:
                    for prov in item.prov:
                        if hasattr(prov, 'page_no'):
                            page = prov.page_no
                            break
                
                # Try to get image data
                image_data = None
                image_ext = "png"
                width = 0
                height = 0
                
                # Method 1: Get from item.image
                if hasattr(item, 'image') and item.image is not None:
                    try:
                        if hasattr(item.image, 'pil_image') and item.image.pil_image:
                            pil_img = item.image.pil_image
                            width, height = pil_img.size
                            buf = io.BytesIO()
                            pil_img.save(buf, format='PNG')
                            image_data = buf.getvalue()
                        elif hasattr(item.image, 'tobytes'):
                            image_data = item.image.tobytes()
                    except Exception as e:
                        logger.debug(f"Could not extract from item.image: {e}")
                
                # Method 2: Get from item.get_image()
                if not image_data and hasattr(item, 'get_image'):
                    try:
                        pil_img = item.get_image(docling_doc)
                        if pil_img:
                            width, height = pil_img.size
                            buf = io.BytesIO()
                            pil_img.save(buf, format='PNG')
                            image_data = buf.getvalue()
                    except Exception as e:
                        logger.debug(f"Could not extract from get_image: {e}")
                
                # Method 3: Get from document's picture export
                if not image_data and hasattr(docling_doc, 'pictures'):
                    try:
                        for pic in docling_doc.pictures:
                            if hasattr(pic, 'self_ref') and hasattr(item, 'self_ref'):
                                if pic.self_ref == item.self_ref:
                                    if hasattr(pic, 'image') and pic.image:
                                        if hasattr(pic.image, 'pil_image'):
                                            pil_img = pic.image.pil_image
                                            width, height = pil_img.size
                                            buf = io.BytesIO()
                                            pil_img.save(buf, format='PNG')
                                            image_data = buf.getvalue()
                                            break
                    except Exception as e:
                        logger.debug(f"Could not extract from pictures: {e}")
                
                if not image_data:
                    logger.debug(f"No image data found for picture on page {page}")
                    continue
                
                # Size validation
                if width < self.min_width or height < self.min_height:
                    continue
                
                # Generate ID and path - save in category/document folder
                image_id = f"{document_id}_p{page}_img{img_idx}"
                image_filename = f"p{page}_img{img_idx}.{image_ext}"
                # Create folder: extracted_images/{category_id}/{document_id}/
                if category_id:
                    doc_images_dir = self.settings.images_dir / category_id / document_id
                else:
                    doc_images_dir = self.settings.images_dir / document_id
                image_path = doc_images_dir / image_filename
                
                # Save to disk
                if save_to_disk:
                    try:
                        image_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(image_path, "wb") as f:
                            f.write(image_data)
                    except Exception as e:
                        logger.warning(f"Could not save image: {e}")
                
                # Get caption
                caption = None
                if hasattr(item, 'caption') and item.caption:
                    caption = str(item.caption)
                elif hasattr(item, 'text') and item.text:
                    caption = item.text
                
                # Create ExtractedImage - no base64_data stored
                extracted = ExtractedImage(
                    image_id=image_id,
                    document_id=document_id,
                    category_id=category_id,
                    page_number=page,
                    image_path=str(image_path),
                    image_format=image_ext,
                    width=width,
                    height=height,
                    caption=caption
                    # base64_data is not stored - images are on disk
                )
                images.append(extracted)
                img_idx += 1
                
        except Exception as e:
            logger.error(f"Error extracting images: {e}")
            import traceback
            traceback.print_exc()
        
        logger.info(f"Extracted {len(images)} images using Docling")
        return images
    
    def extract_images_from_pdf(
        self, 
        pdf_path: str, 
        document_id: str,
        save_to_disk: bool = True
    ) -> List[ExtractedImage]:
        """
        Direct extraction from PDF file using Docling with picture export.
        """
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption
            
            # Enable picture extraction
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_table_structure = True
            pipeline_options.images_scale = 2.0  # Higher resolution
            pipeline_options.generate_picture_images = True
            
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            
            result = converter.convert(pdf_path)
            
            return self.extract_images_from_docling(
                result.document, 
                document_id, 
                save_to_disk
            )
            
        except ImportError as e:
            logger.error(f"Docling not installed: {e}")
            return []
        except Exception as e:
            logger.error(f"Error parsing PDF for images: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def associate_with_sections(
        self,
        images: List[ExtractedImage],
        toc: List[TOCEntry]
    ) -> List[ExtractedImage]:
        """Associate images with sections."""
        if not toc:
            return images
        
        for image in images:
            for entry in toc:
                page_end = entry.page_end or float('inf')
                if entry.page_number <= image.page_number <= page_end:
                    image.section_title = entry.title
                    break
        
        return images
    
    def get_images_for_page_range(
        self,
        images: List[ExtractedImage],
        page_start: int,
        page_end: int
    ) -> List[ExtractedImage]:
        """Get images within page range."""
        return [
            img for img in images 
            if page_start <= img.page_number <= page_end
        ]
    
    def load_image_as_pil(self, image: ExtractedImage) -> Optional[Image.Image]:
        """Load extracted image as PIL Image."""
        try:
            if Path(image.image_path).exists():
                return Image.open(image.image_path)
        except Exception as e:
            logger.warning(f"Could not load image: {e}")
        return None


# Re-export for compatibility
ImageExtractor = DoclingImageExtractor

_extractor_instance: Optional[DoclingImageExtractor] = None

def get_image_extractor() -> DoclingImageExtractor:
    """Get singleton image extractor instance."""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = DoclingImageExtractor()
    return _extractor_instance
