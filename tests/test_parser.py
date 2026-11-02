from pathlib import Path

from ingest.parse import parse_markdown


def test_markdown_parser(tmp_path: Path):

    document = tmp_path / "employee_handbook.md"

    document.write_text(
        """# Employee Handbook

## Leave Policy

### Casual Leave

Employees receive 12 days of casual leave.

### Sick Leave

Employees receive 10 days of sick leave.

## Remote Work

Employees may work remotely.
""",
        encoding="utf-8",
    )

    result = parse_markdown(str(document))

    assert result.title == "employee_handbook"
    assert result.document_type == "markdown"

    # Empty headings are kept so parent_position always points at a real section.
    assert [
        (s.title, s.level, s.position, s.parent_position)
        for s in result.sections
    ] == [
        ("Employee Handbook", 1, 0, None),
        ("Leave Policy", 2, 1, 0),
        ("Casual Leave", 3, 2, 1),
        ("Sick Leave", 3, 3, 1),
        ("Remote Work", 2, 4, 0),
    ]

    assert result.sections[2].content == "Employees receive 12 days of casual leave."
    assert result.sections[4].content == "Employees may work remotely."