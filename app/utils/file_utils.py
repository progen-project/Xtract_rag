"""
File utilities for PetroRAG.
"""
from pathlib import Path
import uuid
import aiofiles
from typing import Optional
from fastapi import UploadFile


def generate_unique_filename(original_filename: str, prefix: str = "") -> str:
    """
    Generate a unique filename preserving the original extension.
    
    Args:
        original_filename: Original file name
        prefix: Optional prefix for the filename
        
    Returns:
        Unique filename
    """
    ext = Path(original_filename).suffix if original_filename else ".bin"
    unique_id = uuid.uuid4().hex[:12]
    if prefix:
        return f"{prefix}_{unique_id}{ext}"
    return f"{unique_id}{ext}"


async def save_uploaded_file(
    file: UploadFile,
    destination_dir: Path,
    filename: Optional[str] = None
) -> Path:
    """
    Save an uploaded file to disk.
    
    Args:
        file: FastAPI UploadFile object
        destination_dir: Directory to save the file
        filename: Optional custom filename (generates unique if None)
        
    Returns:
        Path to the saved file
    """
    destination_dir.mkdir(parents=True, exist_ok=True)
    
    if filename is None:
        filename = generate_unique_filename(file.filename or "file")
    
    file_path = destination_dir / filename
    
    content = await file.read()
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)
    
    return file_path
