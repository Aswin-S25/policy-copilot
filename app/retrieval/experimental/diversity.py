from app.retrieval.dense import RetrievedChunk

def apply_document_cap(
    chunks: list[RetrievedChunk],
    top_k: int = 5,
    max_per_document: int = 2,
) -> list[RetrievedChunk]:
    
    selected = []
    document_counts = {}
    
    for chunk in chunks:
        document_id = chunk.document_id
        
        count = document_counts.get(document_id, 0)
        
        if count >= max_per_document:
            continue
        
        selected.append(chunk)
        document_counts[document_id] = count + 1
        
        if len(selected) == top_k:
            break

    return selected


