"""Tests for config.demote_section_headings — normalizes sections whose bodies
carry their own leading heading (e.g. migrated from another compile pipeline).
"""

from __future__ import annotations

from pathlib import Path

from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render
from forge.targets.claude_code import _demote_headings


def test_demote_headings_strips_leading_and_demotes_rest() -> None:
    body = "# Title\n\n## Sub A\n\ncontent\n\n### Deep\n\nmore"
    out = _demote_headings(body)
    # leading # Title stripped, ## Sub A → ### Sub A, ### Deep → #### Deep
    assert out.startswith("### Sub A")
    assert "#### Deep" in out
    assert "# Title" not in out.splitlines()[0]


def test_demote_headings_no_leading_heading_still_demotes() -> None:
    body = "plain para\n\n## Inner\n\ntext"
    out = _demote_headings(body)
    # No leading heading to strip, but ## Inner → ### Inner
    assert "plain para" in out
    # check exact heading level via line match (substring check fails because
    # "## Inner" is a substring of "### Inner")
    heading_lines = [line for line in out.splitlines() if line.startswith("#")]
    assert heading_lines == ["### Inner"]


def test_demote_headings_idempotent_on_empty() -> None:
    assert _demote_headings("") == ""


def test_config_parses_demote_flag(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "sp" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "c.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections: [x]\n"
        "demote_section_headings: true\n---\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path, "c")
    assert cfg.demote_section_headings is True


def test_render_with_demote_produces_clean_hierarchy(tmp_path: Path) -> None:
    sec_dir = tmp_path / "sp" / "section"
    cfg_dir = tmp_path / "sp" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    # Section body starts with H2 (like dxyOS's preference.md)
    (sec_dir / "pref.md").write_text(
        "---\nname: pref\n---\n\n## Working Style\n\nrule 1\n\n## Boundaries\n\nrule 2\n",
        encoding="utf-8",
    )
    (cfg_dir / "m.md").write_text(
        "---\nname: m\ntarget: claude-code\nsections: [pref]\ndemote_section_headings: true\n---\n",
        encoding="utf-8",
    )
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "m")
    out = render(secs, cfg)
    # adapter emits `## Pref` (capitalized from name)
    assert "## Pref" in out
    # check exact heading lines — substring checks would confuse ## with ###
    heading_lines = [line for line in out.splitlines() if line.startswith("#")]
    assert "## Working Style" not in heading_lines
    assert "## Boundaries" not in heading_lines  # original H2 is gone
    assert "### Boundaries" in heading_lines     # demoted by one level


def test_render_without_demote_leaves_body_unchanged(tmp_path: Path) -> None:
    sec_dir = tmp_path / "sp" / "section"
    cfg_dir = tmp_path / "sp" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    (sec_dir / "pref.md").write_text(
        "---\nname: pref\n---\n\n## Working Style\n\nrule\n", encoding="utf-8"
    )
    (cfg_dir / "m.md").write_text(
        "---\nname: m\ntarget: claude-code\nsections: [pref]\n---\n",
        encoding="utf-8",
    )
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "m")
    out = render(secs, cfg)
    # adapter emits its own ## Pref
    assert "## Pref" in out
    # body ## Working Style is preserved (no demotion, no strip)
    assert "## Working Style" in out
