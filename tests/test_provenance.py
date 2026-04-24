from pathlib import Path

from forge.compiler.loader import load_sections, load_config
from forge.compiler.provenance import compute_digest, build_block, render_markdown_header
from forge.compiler.renderer import render


def test_provenance_digest_stable(workspace: Path) -> None:
    secs = list(load_sections(workspace).values())
    cfg = load_config(workspace, "main")
    d1 = compute_digest(secs, cfg)
    d2 = compute_digest(secs, cfg)
    assert d1 == d2
    assert len(d1) == 12


def test_provenance_digest_changes_with_content(workspace: Path, tmp_path: Path) -> None:
    secs1 = load_sections(workspace)
    cfg = load_config(workspace, "main")
    d1 = compute_digest(list(secs1.values()), cfg)
    # mutate
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text("---\nname: alpha\n---\nCHANGED\n", encoding="utf-8")
    secs2 = load_sections(workspace)
    d2 = compute_digest(list(secs2.values()), cfg)
    assert d1 != d2


def test_provenance_digest_changes_with_rendering_fields(workspace: Path) -> None:
    secs = list(load_sections(workspace).values())
    cfg = load_config(workspace, "main")
    d1 = compute_digest(secs, cfg)

    cfg.demote_section_headings = True
    d2 = compute_digest(secs, cfg)
    assert d1 != d2

    cfg.demote_section_headings = False
    cfg.output_frontmatter = {"kind": "derived"}
    d3 = compute_digest(secs, cfg)
    assert d1 != d3

    secs[0].type = "wrapper"
    d4 = compute_digest(secs, cfg)
    assert d3 != d4


def test_provenance_block_fields(workspace: Path) -> None:
    secs = list(load_sections(workspace).values())
    cfg = load_config(workspace, "main")
    block = build_block(secs, cfg)
    assert block["config"] == "main"
    assert block["target"] == "claude-code"
    assert block["forge_core_version"]
    assert "compiled_at" not in block
    assert len(block["sections"]) == 2
    assert {s["name"] for s in block["sections"]} == {"alpha", "beta"}


def test_provenance_header_html(workspace: Path) -> None:
    secs = list(load_sections(workspace).values())
    cfg = load_config(workspace, "main")
    block = build_block(secs, cfg)
    header = render_markdown_header(block, "html")
    assert header.startswith("<!--")
    assert header.endswith("-->")
    assert "digest=" in header
    assert "alpha" in header


def test_provenance_header_blockquote(workspace: Path) -> None:
    secs = list(load_sections(workspace).values())
    cfg = load_config(workspace, "main")
    block = build_block(secs, cfg)
    header = render_markdown_header(block, "blockquote")
    assert all(line.startswith(">") for line in header.splitlines())


def test_render_includes_provenance(workspace: Path) -> None:
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    out = render(secs, cfg)
    assert "forge-core provenance" in out
    assert "digest=" in out
    assert "compiled_at=" not in out


def test_section_upstream_field(tmp_path: Path) -> None:
    from forge.compiler.section import Section
    p = tmp_path / "s.md"
    p.write_text(
        "---\nname: s\nkind: derived\nupstream:\n  - foo.md\n  - bar.md\ngenerated_by: test-pipeline\n---\nbody\n",
        encoding="utf-8",
    )
    s = Section.from_file(p)
    assert s.kind == "derived"
    assert s.upstream == ["foo.md", "bar.md"]
    assert s.generated_by == "test-pipeline"


def test_section_upstream_must_be_list(tmp_path: Path) -> None:
    from forge.compiler.section import Section
    import pytest
    p = tmp_path / "bad.md"
    p.write_text("---\nname: bad\nupstream: not-a-list\n---\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Section.from_file(p)


def test_section_last_rebuild_at_fallback(tmp_path: Path) -> None:
    """dxyOS-style sections have `last_rebuild_at` instead of `updated_at`."""
    from forge.compiler.section import Section
    p = tmp_path / "dxy.md"
    p.write_text(
        "---\nname: x\nkind: derived\nlast_rebuild_at: 2026-04-21T21:30:00\n---\nbody\n",
        encoding="utf-8",
    )
    s = Section.from_file(p)
    assert s.updated_at is not None
    assert "2026-04-21" in str(s.updated_at)
