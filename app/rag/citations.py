import re

SOURCE_PATTERN = re.compile(r"\[Source\s+(\d+)\]")

# Some models cite in their own native style instead of the prompt's
# "[Source N]": gpt-oss uses lenticular brackets, sometimes with a span
# suffix ("【Source 1】", "【Source 1†L3-L5】"). Same meaning, so they are
# normalized before validation; anything else is left to the usual checks.
NATIVE_CITATION_PATTERN = re.compile(r"【\s*Source\s+(\d+)[^】\n]{0,40}】")


def normalize_citations(answer: str) -> str:
    return NATIVE_CITATION_PATTERN.sub(r"[Source \1]", answer)


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