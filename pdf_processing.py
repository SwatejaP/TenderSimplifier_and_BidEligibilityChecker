import io
import re
import logging
from PyPDF2 import PdfReader
import pdfplumber

logger = logging.getLogger(__name__)

def clean_text(text: str) -> str:
    """
    Cleans raw extracted PDF text:
    - Normalizes spacing and line breaks.
    - Strips multiple consecutive empty lines.
    - Preserves layout/tables as much as possible.
    """
    if not text:
        return ""
        
    # Replace multiple spaces with a single space, but keep line breaks
    lines = text.split("\n")
    cleaned_lines = []
    
    for line in lines:
        # Strip trailing/leading spaces on each line
        line_stripped = line.strip()
        
        # Avoid saving repetitive page numbers or header lines if they match patterns
        # e.g., "Page 1 of 12"
        if re.match(r'^page\s+\d+\s+of\s+\d+$', line_stripped, re.IGNORECASE):
            continue
        if re.match(r'^\d+$', line_stripped): # just a page number
            continue
            
        cleaned_lines.append(line_stripped)
        
    # Join with single newlines and merge multiple consecutive empty lines
    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r'\n{3,}', '\n\n', cleaned_text)
    
    return cleaned_text.strip()

def extract_text_from_pdf(pdf_file) -> str:
    """
    Extracts text from a PDF file.
    Accepts either a string path or a file-like object (BytesIO).
    """
    raw_text = ""
    
    # 1. Try pdfplumber for high-fidelity layout (crucial for tender grids and tables)
    try:
        # If it's bytes, wrap in BytesIO
        if isinstance(pdf_file, bytes):
            pdf_file_obj = io.BytesIO(pdf_file)
        else:
            pdf_file_obj = pdf_file
            
        with pdfplumber.open(pdf_file_obj) as pdf:
            pages_text = []
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text(layout=True)
                if page_text:
                    pages_text.append(page_text)
            raw_text = "\n".join(pages_text)
            
        if len(raw_text.strip()) > 200:
            return clean_text(raw_text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}. Falling back to PyPDF2.")
        
    # 2. Fallback to PyPDF2
    try:
        if isinstance(pdf_file, bytes):
            pdf_file_obj = io.BytesIO(pdf_file)
        else:
            if hasattr(pdf_file, 'seek'):
                pdf_file.seek(0)
            pdf_file_obj = pdf_file
            
        reader = PdfReader(pdf_file_obj)
        pages_text = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text:
                pages_text.append(text)
        raw_text = "\n".join(pages_text)
    except Exception as e:
        logger.error(f"PyPDF2 fallback also failed: {e}")
        raise RuntimeError(f"Failed to extract text from PDF: {e}")
        
    return clean_text(raw_text)
