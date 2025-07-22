import fitz  # PyMuPDF
from typing import List, Tuple

def read_pdf(pdf_path: str) -> List[str]:
    """Extract text from PDF, returning a list of pages"""
    doc = fitz.open(pdf_path)
    pages = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        pages.append(page.get_text())
    return pages

def split_content(pages: List[str], chunk_size: int = 2500, overlap: int = 500) -> List[str]:
    """Split PDF content into overlapping chunks to ensure context is preserved"""
    chunks = []
    current_chunk = ""
    
    for page in pages:
        if len(current_chunk) + len(page) < chunk_size:
            current_chunk += page
        else:
            # Add current chunk before starting a new one
            if current_chunk:
                chunks.append(current_chunk)
            
            # Start new chunk with overlap from previous
            if current_chunk and len(current_chunk) > overlap:
                current_chunk = current_chunk[-overlap:] + page
            else:
                current_chunk = page
    
    # Add the final chunk if it's not empty
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks
