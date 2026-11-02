import hashlib

def hash_content(content: str) -> str:
    normalized = content.strip().replace("\r\n", "\n")
    
    return hashlib.sha256(
        normalized.encode('utf-8')
    ).hexdigest()
    
def hash_embedding_input(
    document_title: str,
    section_path: str,
    content: str,
) -> str:
    value = (
        f"Document: {document_title}\n"
        f"Section: {section_path}\n\n"
        f"{content}" 
    )
    
    return hash_content(value)