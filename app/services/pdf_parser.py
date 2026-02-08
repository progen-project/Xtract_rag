"""
FULLY FIXED PDF Parser service using IBM Docling.
CRITICAL FIX: Strips base64 images from exported markdown content.
"""
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import re

from app.schemas import TOCEntry, ParsedSection, ExtractedTable
from app.config.settings import get_settings

logger = logging.getLogger(__name__)


def strip_base64_images_from_markdown(markdown: str) -> str:
    """
    Remove base64 image data URIs from markdown content.
    
    CRITICAL: Docling's export_to_markdown() includes images as:
        ![Image](data:image/png;base64,iVBORw0KGgoAAAA...)
    
    These can be MASSIVE (>100KB per image) and break LLM token limits.
    
    This function replaces them with simple placeholders.
    """
    # Pattern: matches markdown image with data URI (non-greedy)
    pattern = r'!\[([^\]]*)\]\(data:image/[^;]+;base64,[^\)]+\)'
    
    def replacement(match):
        alt_text = match.group(1)
        if alt_text:
            return f'[Image: {alt_text}]'
        return '[Image]'
    
    cleaned = re.sub(pattern, replacement, markdown)
    
    # Also remove any stray data:image URIs
    cleaned = re.sub(r'data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+', '[Image removed]', cleaned)
    
    return cleaned


class DoclingParser:
    """
    PDF parsing service using IBM Docling.
    Uses AI-based TableFormer model for accurate table detection.
    
    CRITICAL: All exported markdown is cleaned of base64 images.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self._converter = None
        self._initialized = False
    
    def _ensure_initialized(self):
        """Lazy initialization of Docling converter."""
        if self._initialized:
            return
        
        try:
            from docling.document_converter import DocumentConverter
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import PdfFormatOption
            
            # Configure pipeline for table and figure extraction
            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_table_structure = True
            pipeline_options.do_ocr = True  # ENABLED: Handle scanned PDFs
            pipeline_options.images_scale = 2.0
            pipeline_options.generate_picture_images = True
            
            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            self._initialized = True
            logger.info("Docling converter initialized")
            
        except ImportError as e:
            logger.error(f"Docling not installed: {e}")
            logger.error("Install with: pip install docling")
            raise
    
    def parse_document(
        self, 
        pdf_path: str, 
        document_id: str
    ) -> Dict[str, Any]:
        """
        Parse a PDF document and extract all content.
        
        CRITICAL: Strips base64 images from all content.
        
        Returns:
            Dict with 'sections', 'tables', 'toc', 'markdown'
        """
        self._ensure_initialized()
        
        logger.info(f"Parsing PDF with Docling: {pdf_path}")
        
        # Convert document
        result = self._converter.convert(pdf_path)
        doc = result.document
        
        # Extract TOC
        toc = self._extract_toc(doc)
        
        # Extract sections with content (CLEANED)
        sections = self._extract_sections(doc, document_id, toc)
        
        # Extract tables
        tables = self._extract_tables(doc, document_id)
        
        # Get markdown representation (CLEANED)
        markdown_raw = doc.export_to_markdown()
        markdown = strip_base64_images_from_markdown(markdown_raw)
        
        # Log size reduction
        size_before = len(markdown_raw)
        size_after = len(markdown)
        if size_before > size_after:
            logger.info(f"Stripped base64 images: {size_before} -> {size_after} bytes ({100*(1-size_after/size_before):.1f}% reduction)")
        
        logger.info(f"Parsed: {len(sections)} sections, {len(tables)} tables")
        
        return {
            "sections": sections,
            "tables": tables,
            "toc": toc,
            "markdown": markdown,
            "document": doc  # Keep for image extraction
        }
    
    def _extract_toc(self, doc) -> List[TOCEntry]:
        """Extract table of contents from Docling document."""
        toc_entries = []
        
        try:
            from docling_core.types.doc import DocItemLabel
            
            current_page = 1
            
            for item, level in doc.iterate_items():
                if hasattr(item, 'label'):
                    if item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]:
                        page = current_page
                        if hasattr(item, 'prov') and item.prov:
                            for prov in item.prov:
                                if hasattr(prov, 'page_no'):
                                    page = prov.page_no
                                    current_page = page
                                    break
                        
                        text = ""
                        if hasattr(item, 'text'):
                            text = item.text
                        elif hasattr(item, 'export_to_text'):
                            text = item.export_to_text()
                        
                        if text:
                            toc_entries.append(TOCEntry(
                                title=text.strip()[:200],
                                level=level,
                                page_number=page,
                                page_end=None
                            ))
            
            # Calculate page_end
            for i, entry in enumerate(toc_entries):
                if i + 1 < len(toc_entries):
                    entry.page_end = toc_entries[i + 1].page_number - 1
                    if entry.page_end < entry.page_number:
                        entry.page_end = entry.page_number
        
        except Exception as e:
            logger.warning(f"Error extracting TOC: {e}")
        
        if not toc_entries:
            toc_entries.append(TOCEntry(
                title="Document Content",
                level=1,
                page_number=1,
                page_end=None
            ))
        
        logger.info(f"Extracted {len(toc_entries)} TOC entries")
        return toc_entries
    
    def _extract_sections(
        self, 
        doc, 
        document_id: str, 
        toc: List[TOCEntry]
    ) -> List[ParsedSection]:
        """
        Extract text sections from Docling document.
        
        CRITICAL: Strips base64 images from ALL section content.
        """
        sections = []
        
        # Initialize sections from TOC
        for entry in toc:
            sections.append(ParsedSection(
                title=entry.title,
                level=entry.level,
                content="", 
                page_start=entry.page_number,
                page_end=entry.page_end or entry.page_number,
                tables=[],
                images=[]
            ))
        
        if not sections:
            # Fallback
            try:
                markdown = doc.export_to_markdown()
                # CRITICAL: Clean markdown
                markdown = strip_base64_images_from_markdown(markdown)
            except:
                markdown = ""
                
            sections.append(ParsedSection(
                title="Document Content",
                level=1,
                content=markdown,
                page_start=1,
                page_end=1,
                tables=[],
                images=[]
            ))
            return sections

        # Iterate through document items
        current_section_idx = 0
        from docling_core.types.doc import DocItemLabel
        
        for item, level in doc.iterate_items():
            # Check if header for new section
            is_header = hasattr(item, 'label') and item.label in [DocItemLabel.SECTION_HEADER, DocItemLabel.TITLE]
            
            if is_header and current_section_idx + 1 < len(sections):
                next_title = sections[current_section_idx + 1].title
                
                item_text = ""
                if hasattr(item, 'text'):
                    item_text = item.text
                elif hasattr(item, 'export_to_text'):
                    item_text = item.export_to_text()
                
                if item_text.strip() == next_title.strip():
                    current_section_idx += 1
            
            # Export item to markdown
            item_markdown = ""
            if hasattr(item, 'export_to_markdown'):
                try:
                    item_markdown = item.export_to_markdown()
                except TypeError:
                    try:
                        item_markdown = item.export_to_markdown(doc)
                    except Exception as e:
                        logger.warning(f"Failed to export item to markdown: {e}")
                        if hasattr(item, 'text'):
                            item_markdown = item.text
            elif hasattr(item, 'text'):
                item_markdown = item.text
            
            if item_markdown:
                # CRITICAL: Clean base64 images
                item_markdown = strip_base64_images_from_markdown(item_markdown)
                sections[current_section_idx].content += item_markdown + "\n\n"
        
        # Final cleaning pass on all sections
        for section in sections:
            section.content = strip_base64_images_from_markdown(section.content)
        
        return sections
    
    def _extract_tables(self, doc, document_id: str) -> List[ExtractedTable]:
        """Extract tables from Docling document."""
        tables = []
        
        try:
            from docling_core.types.doc import DocItemLabel
            
            table_idx = 0
            
            for item, level in doc.iterate_items():
                if hasattr(item, 'label') and item.label == DocItemLabel.TABLE:
                    page = 1
                    if hasattr(item, 'prov') and item.prov:
                        for prov in item.prov:
                            if hasattr(prov, 'page_no'):
                                page = prov.page_no
                                break
                    
                    markdown = ""
                    if hasattr(item, 'export_to_markdown'):
                        markdown = item.export_to_markdown()
                    
                    # Tables shouldn't have images, but clean anyway
                    markdown = strip_base64_images_from_markdown(markdown)
                    
                    headers = []
                    rows = []
                    
                    if hasattr(item, 'data') and item.data:
                        table_data = item.data
                        if hasattr(table_data, 'grid'):
                            grid = table_data.grid
                            if grid and len(grid) > 0:
                                headers = [str(cell.text if hasattr(cell, 'text') else cell) for cell in grid[0]]
                                rows = [
                                    [str(cell.text if hasattr(cell, 'text') else cell) for cell in row]
                                    for row in grid[1:]
                                ]
                    
                    if markdown and not headers:
                        headers, rows = self._parse_markdown_table(markdown)
                    
                    if headers or markdown:
                        tables.append(ExtractedTable(
                            table_id=f"{document_id}_table_{table_idx}",
                            document_id=document_id,
                            page_number=page,
                            headers=headers,
                            rows=rows,
                            markdown_content=markdown
                        ))
                        table_idx += 1
        
        except Exception as e:
            logger.warning(f"Error extracting tables: {e}")
        
        logger.info(f"Extracted {len(tables)} tables")
        return tables
    
    def _parse_markdown_table(self, markdown: str) -> tuple:
        """Parse markdown table into headers and rows."""
        lines = markdown.strip().split('\n')
        headers = []
        rows = []
        
        for i, line in enumerate(lines):
            if '|' not in line:
                continue
            
            cells = [c.strip() for c in line.split('|')[1:-1]]
            
            if i == 0:
                headers = cells
            elif '---' not in line:
                rows.append(cells)
        
        return headers, rows


# Singleton instance
_parser_instance: Optional[DoclingParser] = None


def get_pdf_parser() -> DoclingParser:
    """Get singleton PDF parser instance."""
    global _parser_instance
    if _parser_instance is None:
        _parser_instance = DoclingParser()
    return _parser_instance