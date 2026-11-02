from dataclasses import dataclass

from app.retrieval import RetrievedChunk

@dataclass
class ContextChunk:
    source_number: int
    chunk: RetrievedChunk
    formatted_text: str
    estimated_tokens: int


@dataclass
class BuildContext:
    chunks: list[ContextChunk]
    text: str
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)

def format_chunk(
    source_number: int,
    chunk: RetrievedChunk,
) -> str:
    section = chunk.section_path or"Unknown section"
    
    return (
        f"[Source {source_number}]\n"
        f"Document: {chunk.document_title}\n"
        f"Section: {section}\n"
        f"Chunk: {chunk.chunk_index}\n\n"
        f"{chunk.content}"
    )
    
def build_context(
    retrieved_chunks: list[RetrievedChunk],
    max_tokens: int = 3000
) -> BuildContext:
    
    selected_chunks = []
    formatted_parts = []
    total_tokens = 0
    
    for chunk in retrieved_chunks:
        source_number = len(selected_chunks) + 1
        
        formatted = format_chunk(
            source_number=source_number,
            chunk=chunk
        )
        
        chunk_tokens = estimate_tokens(formatted)
        
        if total_tokens + chunk_tokens > max_tokens:
            break
        
        selected_chunks.append(
            ContextChunk(
                source_number=source_number,
                chunk=chunk,
                formatted_text=formatted,
                estimated_tokens=chunk_tokens,
            )
        )
        
        formatted_parts.append(formatted)
        total_tokens += chunk_tokens
        
        return BuildContext(
            chunks=selected_chunks,
            text="\n\n".join(formatted_parts),
            estimated_tokens=total_tokens,
        )