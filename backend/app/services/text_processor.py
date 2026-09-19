import re
import hashlib
from typing import List, Tuple
from app.core.curriculum_config import (
    CURRICULUM_CHUNK_TARGET_CHARS,
    CURRICULUM_CHUNK_MAX_CHARS,
    CURRICULUM_CHUNK_OVERLAP_CHARS
)

def normalize_text(text: str) -> str:
    # Windows CRLF to LF
    text = text.replace('\r\n', '\n')
    # Excessive blank lines (more than 2) -> 2 blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Repeated spaces inside normal prose
    # We shouldn't destroy indentation entirely, but prompt says "repeated spaces inside normal prose".
    # Let's just do multiple spaces -> single space for now, except leading/trailing.
    # Actually, standard space deduplication:
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()

def chunk_text(text: str) -> List[str]:
    norm = normalize_text(text)
    if not norm:
        return []

    # split into structural blocks (paragraphs)
    blocks = norm.split('\n\n')
    
    chunks = []
    current_chunk = ""

    def flush(force=False):
        nonlocal current_chunk
        if current_chunk:
            chunks.append(current_chunk.strip())
            current_chunk = ""

    def add_with_overlap(block: str):
        nonlocal current_chunk
        if not current_chunk:
            current_chunk = block
        else:
            combined = current_chunk + "\n\n" + block
            if len(combined) <= CURRICULUM_CHUNK_MAX_CHARS:
                current_chunk = combined
            else:
                flush()
                prev = chunks[-1] if chunks else ""
                overlap = prev[-CURRICULUM_CHUNK_OVERLAP_CHARS:] if len(prev) > CURRICULUM_CHUNK_OVERLAP_CHARS else prev
                last_space = overlap.find(' ')
                if last_space != -1 and last_space < len(overlap) - 1:
                    overlap = overlap[last_space+1:]
                current_chunk = (overlap + "\n" + block).strip() if overlap else block

        while len(current_chunk) > CURRICULUM_CHUNK_MAX_CHARS:
            split_point = current_chunk.rfind(' ', 0, CURRICULUM_CHUNK_MAX_CHARS)
            if split_point == -1 or split_point < CURRICULUM_CHUNK_MAX_CHARS // 2:
                split_point = CURRICULUM_CHUNK_MAX_CHARS
            part = current_chunk[:split_point]
            chunks.append(part.strip())
            
            rem = current_chunk[split_point:].strip()
            overlap = part[-CURRICULUM_CHUNK_OVERLAP_CHARS:] if len(part) > CURRICULUM_CHUNK_OVERLAP_CHARS else part
            ls = overlap.find(' ')
            if ls != -1 and ls < len(overlap) - 1:
                overlap = overlap[ls+1:]
            current_chunk = (overlap + " " + rem).strip() if overlap else rem

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        
        if len(block) > CURRICULUM_CHUNK_MAX_CHARS:
            # Huge block, just use add_with_overlap which has the while loop
            add_with_overlap(block)
        else:
            if current_chunk:
                combined = current_chunk + "\n\n" + block
                if len(combined) >= CURRICULUM_CHUNK_TARGET_CHARS:
                    if len(combined) <= CURRICULUM_CHUNK_MAX_CHARS:
                        current_chunk = combined
                        flush()
                    else:
                        flush()
                        add_with_overlap(block)
                else:
                    current_chunk = combined
            else:
                current_chunk = block

    flush()
    return chunks


from typing import Protocol
from dataclasses import dataclass
from app.core.exceptions import CurriculumUnsupportedFormatError

@dataclass
class ExtractedDocument:
    text: str
    metadata: dict

class DocumentTextExtractor(Protocol):
    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        ...

class PlainTextExtractor:
    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        if mime_type not in ("text/plain", "text/markdown"):
            raise CurriculumUnsupportedFormatError()
        return ExtractedDocument(text=data.decode("utf-8"), metadata={})

class PdfTextExtractor:
    def extract(self, data: bytes, mime_type: str) -> ExtractedDocument:
        raise CurriculumUnsupportedFormatError()

