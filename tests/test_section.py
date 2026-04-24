from pathlib import Path

import pytest

from forge.compiler.section import Section


def test_section_from_file_with_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "s.md"
    p.write_text(
        "---\nname: foo\ntype: identity\nupdated_at: 2026-01-01\n---\n\nbody here\n",
        encoding="utf-8",
    )
    s = Section.from_file(p)
    assert s.name == "foo"
    assert s.type == "identity"
    assert s.updated_at == "2026-01-01"
    assert s.body == "body here"


def test_section_no_frontmatter_defaults_name_to_stem(tmp_path: Path) -> None:
    p = tmp_path / "bar.md"
    p.write_text("just body\n", encoding="utf-8")
    s = Section.from_file(p)
    assert s.name == "bar"
    assert s.type is None
    assert s.body == "just body"


def test_section_size_metrics(tmp_path: Path) -> None:
    p = tmp_path / "z.md"
    p.write_text("---\nname: z\n---\n\nline1\nline2\nline3\n", encoding="utf-8")
    s = Section.from_file(p)
    assert s.line_count >= 3
    assert s.byte_size == len(s.body.encode("utf-8"))


def test_section_rejects_non_mapping_frontmatter(tmp_path: Path) -> None:
    p = tmp_path / "bad.md"
    p.write_text("---\n- just a list\n---\n\nbody\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Section.from_file(p)


def test_section_filename_with_spaces(tmp_path: Path) -> None:
    p = tmp_path / "about user.md"
    p.write_text("---\ntype: identity\n---\n\nhello\n", encoding="utf-8")
    s = Section.from_file(p)
    # defaults name to stem when frontmatter has no `name` field
    assert s.name == "about user"
