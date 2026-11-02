from dataclasses import dataclass, field

@dataclass
class ParsedSection:
    title:str
    level: int
    content: str
    position: int
    parent_position: int | None = None
    

@dataclass
class ParsedDocument:
    title: str
    source: str
    document_type: str
    content: str
    sections: list[ParsedSection] = field(default_factory=list)
    
@dataclass
class ChunkData:
    index: int
    content: str
    section_position: int | None