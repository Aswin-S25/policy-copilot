import re

SOURCE_PATTERN = re.compile(r"\[Source\s+(\d+)\]")


def exact_citations(answer: str) -> set[int]:
    return {
        int(match)
        for match in SOURCE_PATTERN.findall(answer)
    }
    
    
def validate_citations(
    answer: str,
    available_sources: set[int],
) -> bool:
    
    cited_sources = exact_citations(answer)
    
    if not cited_sources:
        return False
    
    return cited_sources.issubset(available_sources)

def remove_invalid_citations(
    answer: str,
    available_sources: set[int],
) -> str:
    
    def replace(match: re.Match) -> str:
        source_number = int(match.group(1))
        
        if source_number in available_sources:
            return match.group(0)
        
        return ""
    return SOURCE_PATTERN.sub(replace, answer)