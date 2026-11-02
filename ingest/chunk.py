from ingest.models import ChunkData, ParsedSection

DEFAULT_CHUNK_SIZE = 1500
DEFAULT_OVERLAP = 200


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP
) -> list[str]:
    
    text = text.strip()
    
    if not text:
        return []
    
    if overlap >= chunk_size:
        raise ValueError(
            "overlap must be smaller than chunk size"
        )
        
    chunks = []
    
    start = 0
    
    while start < len(text):
        end = min(
            start + chunk_size,
            len(text)
        )
        
        chunk = text[start:end].strip()
        
        if chunk:
            chunks.append(chunk)
        
        if end == len(text):
            break
        
        start = end - overlap

    return chunks
    
def chunk_sections(
    sections: list[ParsedSection],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[ChunkData]:
    
    chunks: list[ChunkData] = []
    
    for section in sections:
        section_chunks = chunk_text(
            section.content,
            chunk_size=chunk_size,
            overlap=overlap
        )
        
        for content in section_chunks:
            chunks.append(
                ChunkData(
                    index=len(chunks),
                    content=content,
                    section_position=section.position
                )
            )
    return chunks


def build_contextual_text(
    document_title: str,
    section_path: str,
    content: str,
) -> str:
    
    return (
        f"Document: {document_title}\n"
        f"Section: {section_path}\n\n"
        f"{content}"
    )
