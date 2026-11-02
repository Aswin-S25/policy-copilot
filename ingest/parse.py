from pathlib import Path
import re

from ingest.models import ParsedDocument, ParsedSection


HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_markdown(path: str) -> ParsedDocument:
    file_path = Path(path)

    content = file_path.read_text(encoding="utf-8")

    lines = content.splitlines()

    title = file_path.stem

    sections: list[ParsedSection] = []

    current_title = title
    current_level = 0
    current_content: list[str] = []
    current_position = 0
    current_parent: int | None = None

    section_stack: list[tuple[int, int]] = []

    def flush_section():
        nonlocal current_position

        text = "\n".join(current_content).strip()

        # Keep headings even when empty so positions on the stack stay valid;
        # only drop an empty preamble.
        if not text and current_level == 0:
            return

        sections.append(
            ParsedSection(
                title=current_title,
                level=current_level,
                content=text,
                position=current_position,
                parent_position=current_parent,
            )
        )

        current_position += 1

    for line in lines:
        match = HEADING_RE.match(line)

        if not match:
            current_content.append(line)
            continue

        flush_section()

        level = len(match.group(1))
        heading = match.group(2).strip()

        while (
            section_stack
            and section_stack[-1][0] >= level
        ):
            section_stack.pop()

        current_parent = (
            section_stack[-1][1]
            if section_stack
            else None
        )

        current_title = heading
        current_level = level
        current_content = []

        section_stack.append(
            (level, current_position)
        )

    flush_section()

    return ParsedDocument(
        title=title,
        source=str(file_path),
        document_type="markdown",
        content=content,
        sections=sections,
    )