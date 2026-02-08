"""
IMPROVED Chunker - Clean table removal with proper ID preservation.
Enhanced with header/footer removal and tiny chunk filtering.
"""
from typing import List, Optional, Set
import logging
import uuid
import re
from collections import Counter

from app.config.settings import get_settings
from app.schemas import Chunk, ParsedSection, ExtractedImage, ExtractedTable

logger = logging.getLogger(__name__)


def strip_base64_images(text: str) -> str:
    """Remove base64 image data URIs from text."""
    pattern = r'!\[([^\]]*)\]\(data:image/[^;]+;base64,[^\)]+\)'
    
    def replacement(match):
        alt_text = match.group(1)
        return f'[Image: {alt_text}]' if alt_text else '[Image]'
    
    cleaned = re.sub(pattern, replacement, text)
    cleaned = re.sub(
        r'data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+',
        '[Image removed]',
        cleaned
    )
    
    return cleaned


def _detect_repeated_headers(sections: List[ParsedSection]) -> Set[str]:
    """
    Detect headers/footers that repeat across multiple sections.
    Returns set of lines to remove.
    """
    if not sections:
        return set()
    
    line_counter = Counter()
    block_counter = Counter()
    total_sections = len(sections)
    
    # Common header patterns - will match even in single section
    patterns = [
        r'^\s*Page\s+\d+\s*$',
        r'^\s*\d+\s*$',
        r'^\s*\d+\s*/\s*\d+\s*$',
        r'^[─═─]{3,}$',
        r'^\s*©.*\d{4}.*$',
        r'^\s*confidential\s*$',
        r'^\s*draft\s*$',
        r'^\s*proprietary\s*$',
        r'^\s*internal\s+use\s+only\s*$',
        # Company manuals (broad patterns)
        r'^.*\s+(MANUAL|HANDBOOK|GUIDE)\s*$',  # Lines ending with MANUAL/HANDBOOK/GUIDE
        r'^.*\s+(DRILLING|OPERATING|SAFETY|TECHNICAL|PROCEDURES?)\s+(MANUAL|HANDBOOK|GUIDE)\s*$',
        # Department headers with dates
        r'^.*(department|division|team|unit).*\d{4}.*$',
        # Month Year patterns
        r'^.*(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}.*$',
        # Company names in headers (common oil & gas companies as examples)
        r'^.*(ARAMCO|CHEVRON|EXXON|SHELL|BP|TOTAL|PETRONAS|ADNOC|PDO).*$',
    ]
    compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
    
    repeated_lines = set()
    
    for section in sections:
        lines = section.content.split('\n')
        header_lines = lines[:5]
        footer_lines = lines[-5:] if len(lines) > 5 else []
        
        # Count individual lines
        for line in header_lines + footer_lines:
            line_clean = line.strip()
            if 3 < len(line_clean) < 150:
                line_counter[line_clean] += 1
                
                # Check patterns - add immediately if matches
                for pattern in compiled_patterns:
                    if pattern.match(line_clean):
                        repeated_lines.add(line_clean)
                        break
        
        # Count 2-line blocks
        for i in range(len(header_lines) - 1):
            block = header_lines[i].strip() + "\n" + header_lines[i+1].strip()
            if 10 < len(block) < 300:
                block_counter[block] += 1
        
        # Count 3-line blocks  
        for i in range(len(header_lines) - 2):
            block = (header_lines[i].strip() + "\n" + 
                    header_lines[i+1].strip() + "\n" + 
                    header_lines[i+2].strip())
            if 15 < len(block) < 400:
                block_counter[block] += 1
    
    # For multi-section documents: lines appearing in >20% of sections
    if total_sections >= 2:
        threshold = max(2, int(total_sections * 0.2))
        
        for line, count in line_counter.items():
            if count >= threshold:
                repeated_lines.add(line)
        
        # Add lines from repeated blocks
        for block, count in block_counter.items():
            if count >= threshold:
                for line in block.split('\n'):
                    if line.strip():
                        repeated_lines.add(line.strip())
    
    if repeated_lines:
        logger.info(f"Detected {len(repeated_lines)} repeated header/footer lines")
    
    return repeated_lines


def _clean_content(content: str, repeated_lines: Set[str]) -> str:
    """Remove headers, footers, and excessive whitespace."""
    lines = content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        
        # Skip very short lines
        if len(line_stripped) < 5:
            continue
        
        # Skip if in repeated lines
        if line_stripped in repeated_lines:
            continue
        
        cleaned_lines.append(line)
    
    # Normalize whitespace
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    return result.strip()


def remove_tables_from_content(
    content: str,
    tables: List[ExtractedTable]
) -> tuple[str, List[str]]:
    """
    Remove ALL table markdown from content and return table IDs.
    
    Returns:
        (cleaned_content, table_ids)
    """
    cleaned_content = content
    found_table_ids = []
    
    for table in tables:
        if not table.markdown_content:
            continue
        
        if table.markdown_content in cleaned_content:
            marker = f"\n[TABLE:{table.table_id}]\n"
            cleaned_content = cleaned_content.replace(
                table.markdown_content,
                marker
            )
            found_table_ids.append(table.table_id)
    
    cleaned_content, extra_ids = remove_markdown_tables_regex(cleaned_content)
    
    return cleaned_content, found_table_ids


def remove_markdown_tables_regex(text: str) -> tuple[str, List[str]]:
    """Remove markdown tables using regex patterns."""
    lines = text.split('\n')
    cleaned_lines = []
    table_lines = []
    in_table = False
    extracted_ids = []
    
    for line in lines:
        marker_match = re.match(r'\[TABLE:([^\]]+)\]', line.strip())
        if marker_match:
            cleaned_lines.append(line)
            extracted_ids.append(marker_match.group(1))
            continue
        
        pipe_count = line.count('|')
        is_separator = '---' in line or '===' in line
        
        if pipe_count >= 2 or (is_separator and in_table):
            in_table = True
            table_lines.append(line)
        else:
            if in_table:
                if len(table_lines) >= 2:
                    cleaned_lines.append("[TABLE_REMOVED]")
                else:
                    cleaned_lines.extend(table_lines)
                
                table_lines = []
                in_table = False
            
            cleaned_lines.append(line)
    
    if in_table and len(table_lines) >= 2:
        cleaned_lines.append("[TABLE_REMOVED]")
    
    return '\n'.join(cleaned_lines), extracted_ids


class SectionChunker:
    """
    Chunks documents by section with NO tables in content.
    Tables referenced by ID only.
    Enhanced with automatic header removal and chunk quality control.
    """
    
    def __init__(self, overlap_percentage: Optional[float] = None):
        self.settings = get_settings()
        self.overlap_percentage = (
            overlap_percentage or self.settings.chunk_overlap_percentage
        )
        # Internal settings for quality control
        # Use 100 chars as minimum (was 30% of max = 300)
        self._min_chunk_size = 100
        self._merge_threshold = int(self.settings.max_chunk_size * 0.3)
    
    def chunk_sections(
        self,
        document_id: str,
        sections: List[ParsedSection],
        images: List[ExtractedImage],
        tables: List[ExtractedTable],
        category_id: str = ""
    ) -> List[Chunk]:
        """
        Create chunks from sections.
        Enhanced with automatic header/footer removal.
        """
        # Detect repeated headers across document
        repeated_headers = _detect_repeated_headers(sections)
        
        chunks = []
        chunk_index = 0
        
        for section in sections:
            section_chunks = self._chunk_section(
                document_id=document_id,
                section=section,
                images=images,
                tables=tables,
                start_index=chunk_index,
                category_id=category_id,
                repeated_headers=repeated_headers
            )
            chunks.extend(section_chunks)
            chunk_index += len(section_chunks)
        
        # Merge tiny chunks
        chunks = self._merge_small_chunks(chunks)
        
        # Apply overlap
        chunks = self._apply_overlap(chunks)
        
        # Filter remaining tiny chunks
        chunks = [c for c in chunks if len(c.content.strip()) >= self._min_chunk_size]
        
        # Reindex
        for idx, chunk in enumerate(chunks):
            chunk.chunk_index = idx
            chunk.chunk_id = f"{document_id}_chunk_{idx}"
        
        logger.info(f"Created {len(chunks)} chunks (headers removed, quality filtered)")
        return chunks
    
    def _chunk_section(
        self,
        document_id: str,
        section: ParsedSection,
        images: List[ExtractedImage],
        tables: List[ExtractedTable],
        start_index: int,
        category_id: str = "",
        repeated_headers: Set[str] = None
    ) -> List[Chunk]:
        """Chunk a single section with proper table ID tracking."""
        if repeated_headers is None:
            repeated_headers = set()
        
        section_tables = [
            tbl for tbl in tables
            if section.page_start <= tbl.page_number <= section.page_end
        ]
        
        section_images = [
            img for img in images
            if section.page_start <= img.page_number <= section.page_end
        ]
        
        # Clean content
        content = strip_base64_images(section.content)
        content = _clean_content(content, repeated_headers)
        content, table_ids = remove_tables_from_content(content, section_tables)
        
        # Extract table IDs
        all_table_ids = self._extract_table_ids_from_markers(content)
        for tbl in section_tables:
            if tbl.table_id not in all_table_ids:
                all_table_ids.append(tbl.table_id)
        
        # Skip if too small
        if len(content.strip()) < self._min_chunk_size:
            logger.debug(f"Skipping tiny section '{section.title}' ({len(content)} chars)")
            return []
        
        # Check if fits in one chunk
        if len(content) <= self.settings.max_chunk_size:
            chunk = Chunk(
                chunk_id=f"{document_id}_chunk_{start_index}",
                document_id=document_id,
                category_id=category_id,
                section_title=section.title,
                content=content,
                page_start=section.page_start,
                page_end=section.page_end,
                chunk_index=start_index,
                image_ids=[img.image_id for img in section_images],
                table_ids=all_table_ids,
                metadata={
                    "section_level": section.level,
                    "has_tables": len(all_table_ids) > 0,
                    "has_images": len(section_images) > 0,
                    "table_count": len(all_table_ids),
                    "image_count": len(section_images),
                }
            )
            return [chunk]
        else:
            return self._split_large_section(
                document_id=document_id,
                section=section,
                content=content,
                images=section_images,
                tables=section_tables,
                all_table_ids=all_table_ids,
                start_index=start_index,
                category_id=category_id
            )
    
    def _split_large_section(
        self,
        document_id: str,
        section: ParsedSection,
        content: str,
        images: List[ExtractedImage],
        tables: List[ExtractedTable],
        all_table_ids: List[str],
        start_index: int,
        category_id: str = ""
    ) -> List[Chunk]:
        """Split large section with proper table ID distribution."""
        chunk_size = self.settings.max_chunk_size
        chunk_overlap = int(chunk_size * self.overlap_percentage)
        
        text_chunks = self._recursive_split(content, chunk_size, chunk_overlap)
        
        chunks = []
        chunk_idx = start_index
        
        for i, chunk_text in enumerate(text_chunks):
            if len(chunk_text.strip()) < 50:
                continue
            
            # Calculate page range
            total_len = len(content) or 1
            start_pos = content.find(chunk_text)
            if start_pos == -1:
                start_pos = 0
            
            end_pos = start_pos + len(chunk_text)
            total_pages = section.page_end - section.page_start + 1
            
            page_start_ratio = start_pos / total_len
            page_end_ratio = end_pos / total_len
            
            chunk_page_start = section.page_start + int(page_start_ratio * total_pages)
            chunk_page_end = section.page_start + int(page_end_ratio * total_pages)
            
            chunk_page_start = max(section.page_start, min(chunk_page_start, section.page_end))
            chunk_page_end = max(section.page_start, min(chunk_page_end, section.page_end))
            
            chunk_images = [
                img for img in images
                if chunk_page_start <= img.page_number <= chunk_page_end
            ]
            
            chunk_table_ids = self._extract_table_ids_from_markers(chunk_text)
            
            if not chunk_table_ids:
                chunk_table_ids = [
                    tbl.table_id for tbl in tables
                    if chunk_page_start <= tbl.page_number <= chunk_page_end
                ]
            
            chunk = Chunk(
                chunk_id=f"{document_id}_chunk_{chunk_idx}",
                document_id=document_id,
                category_id=category_id,
                section_title=section.title,
                content=chunk_text,
                page_start=chunk_page_start,
                page_end=chunk_page_end,
                chunk_index=chunk_idx,
                image_ids=[img.image_id for img in chunk_images],
                table_ids=chunk_table_ids,
                metadata={
                    "section_level": section.level,
                    "is_split": True,
                    "split_part": i + 1,
                    "total_parts": len(text_chunks),
                    "has_tables": len(chunk_table_ids) > 0,
                    "has_images": len(chunk_images) > 0,
                }
            )
            chunks.append(chunk)
            chunk_idx += 1
        
        return chunks
    
    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """Merge chunks that are too small."""
        if not chunks:
            return chunks
        
        merged = []
        i = 0
        
        while i < len(chunks):
            current = chunks[i]
            
            if len(current.content) >= self._merge_threshold:
                merged.append(current)
                i += 1
                continue
            
            # Try merge with next
            if i + 1 < len(chunks):
                next_chunk = chunks[i + 1]
                combined_size = len(current.content) + len(next_chunk.content)
                
                if combined_size <= self.settings.max_chunk_size * 1.2:
                    merged_chunk = self._combine_chunks(current, next_chunk)
                    merged.append(merged_chunk)
                    i += 2
                    continue
            
            # Try merge with previous
            if merged:
                prev = merged[-1]
                combined_size = len(prev.content) + len(current.content)
                
                if combined_size <= self.settings.max_chunk_size * 1.2:
                    merged[-1] = self._combine_chunks(prev, current)
                    i += 1
                    continue
            
            # Keep if above minimum
            if len(current.content) >= self._min_chunk_size:
                merged.append(current)
            
            i += 1
        
        return merged
    
    def _combine_chunks(self, chunk1: Chunk, chunk2: Chunk) -> Chunk:
        """Combine two chunks."""
        return Chunk(
            chunk_id=chunk1.chunk_id,
            document_id=chunk1.document_id,
            category_id=chunk1.category_id,
            section_title=chunk1.section_title or chunk2.section_title,
            content=chunk1.content + "\n\n" + chunk2.content,
            page_start=min(chunk1.page_start, chunk2.page_start),
            page_end=max(chunk1.page_end, chunk2.page_end),
            chunk_index=chunk1.chunk_index,
            image_ids=list(set(chunk1.image_ids + chunk2.image_ids)),
            table_ids=list(set(chunk1.table_ids + chunk2.table_ids)),
            metadata={**chunk1.metadata, "merged": True}
        )
    
    def _recursive_split(
        self,
        text: str,
        chunk_size: int,
        chunk_overlap: int
    ) -> List[str]:
        """Recursively split text by separators."""
        separators = ["\n\n", "\n", ". ", " ", ""]
        return self._split_text(text, separators, chunk_size, chunk_overlap)
    
    def _split_text(
        self,
        text: str,
        separators: List[str],
        chunk_size: int,
        chunk_overlap: int
    ) -> List[str]:
        """Helper for recursive splitting."""
        final_chunks = []
        separator = separators[-1]
        new_separators = []
        
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1:]
                break
        
        splits = [text]
        if separator:
            splits = text.split(separator)
        
        good_splits = []
        current_doc = []
        current_length = 0
        
        for s in splits:
            s_len = len(s)
            if separator:
                s_len += len(separator)
            
            if current_length + s_len > chunk_size:
                if current_doc:
                    doc_text = (separator or "").join(current_doc)
                    if doc_text.strip():
                        good_splits.append(doc_text)
                    
                    current_doc = []
                    current_length = 0
                
                if s_len > chunk_size and new_separators:
                    sub_splits = self._split_text(
                        s, new_separators, chunk_size, chunk_overlap
                    )
                    good_splits.extend(sub_splits)
                else:
                    current_doc.append(s)
                    current_length += s_len
            else:
                current_doc.append(s)
                current_length += s_len
        
        if current_doc:
            doc_text = (separator or "").join(current_doc)
            if doc_text.strip():
                good_splits.append(doc_text)
        
        return good_splits
    
    def _apply_overlap(self, chunks: List[Chunk]) -> List[Chunk]:
        """Apply overlap between chunks."""
        if not chunks or len(chunks) < 2:
            return chunks
        
        for i in range(len(chunks)):
            chunk = chunks[i]
            content_len = len(chunk.content)
            overlap_chars = int(content_len * self.overlap_percentage)
            
            if i > 0:
                prev_chunk = chunks[i - 1]
                prev_content = prev_chunk.content
                overlap_start_text = (
                    prev_content[-overlap_chars:]
                    if len(prev_content) > overlap_chars
                    else prev_content
                )
                
                overlap_start_text = strip_base64_images(overlap_start_text)
                chunk.overlap_start = overlap_start_text.strip()
            
            if i < len(chunks) - 1:
                overlap_end_text = (
                    chunk.content[-overlap_chars:]
                    if content_len > overlap_chars
                    else chunk.content
                )
                
                overlap_end_text = strip_base64_images(overlap_end_text)
                chunk.overlap_end = overlap_end_text.strip()
        
        return chunks
    
    def _extract_table_ids_from_markers(self, content: str) -> List[str]:
        """Extract table IDs from [TABLE:id] markers."""
        pattern = r'\[TABLE:([^\]]+)\]'
        matches = re.findall(pattern, content)
        return list(set(matches))