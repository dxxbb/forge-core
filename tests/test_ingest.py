"""Test forge ingest classifier (no-llm path + workspace integration)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.ingest import classify, write_sections, IngestError


def test_no_llm_path_dumps_to_workspace(tmp_path: Path) -> None:
    text = "I am a backend engineer. I prefer Python. Currently working on forge."
    result = classify(text, use_llm=False)
    assert result.method == "no-llm"
    assert result.sections["workspace"] == text
    # Other sections empty
    for k in ("about-me", "preferences", "knowledge-base", "skills"):
        assert result.sections[k] == ""


def test_no_llm_writes_into_workspace(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    src = tmp_path / "input.md"
    src.write_text("Some content here.\nMore content.", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--no-llm", "--root", str(tmp_path / "ws"), "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "Some content here." in workspace_md
    assert "Review carefully" in workspace_md  # source-attribution note


def test_ingest_refuses_missing_workspace(tmp_path: Path) -> None:
    src = tmp_path / "input.md"
    src.write_text("hi", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--no-llm", "--root", str(tmp_path / "no-ws")],
    )
    assert result.exit_code == 1
    assert "not a forge workspace" in result.output


def test_ingest_refuses_missing_input(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    result = runner.invoke(main, ["ingest", "--no-llm", "--root", str(tmp_path / "ws")])
    assert result.exit_code == 1
    assert "must pass --from" in result.output


def test_ingest_overwrite_refused_for_user_content(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    workspace_md = tmp_path / "ws" / "sp" / "section" / "workspace.md"
    # Replace template with user content (no [TODO: marker)
    workspace_md.write_text(
        "---\nname: workspace\ntype: workspace\n---\n\nuser real content\n",
        encoding="utf-8",
    )

    src = tmp_path / "input.md"
    src.write_text("new content from import", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--no-llm", "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_ingest_overwrites_template_placeholder(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    # Default template has [TODO: marker, so overwriting workspace section
    # is allowed without --overwrite

    src = tmp_path / "input.md"
    src.write_text("imported content", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--no-llm", "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "imported content" in workspace_md
    assert "[TODO:" not in workspace_md  # template was replaced


def test_ingest_stdin(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    result = runner.invoke(
        main,
        ["ingest", "--from-stdin", "--no-llm", "--root", str(tmp_path / "ws"), "--overwrite"],
        input="content from stdin",
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "content from stdin" in workspace_md


def test_classify_extract_json_handles_fenced_response() -> None:
    """LLM might wrap JSON in fenced block; classifier should still parse."""
    from forge.ingest.classifier import _extract_json

    out = '```json\n{"about_me": "x"}\n```'
    parsed = _extract_json(out)
    assert parsed == {"about_me": "x"}


def test_classify_extract_json_handles_inline() -> None:
    from forge.ingest.classifier import _extract_json

    out = 'Sure, here it is: {"about_me": "x"} done'
    parsed = _extract_json(out)
    assert parsed == {"about_me": "x"}


# ---------- forge ingest --detect ----------

def test_ingest_detect_finds_real_file_in_cwd(tmp_path: Path, monkeypatch) -> None:
    """A real CLAUDE.md in cwd should be detected."""
    runner = CliRunner()
    real = tmp_path / "CLAUDE.md"
    real.write_text("# real claude.md\n" + ("filler\n" * 50), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))  # isolate from real ~/.claude/
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "found 1 importable" in result.output
    assert "CLAUDE.md" in result.output


def test_ingest_detect_skips_broken_symlink(tmp_path: Path, monkeypatch) -> None:
    """Broken symlinks should be reported as skipped, not break detection."""
    runner = CliRunner()
    bad = tmp_path / "CLAUDE.md"
    bad.symlink_to(tmp_path / "does-not-exist")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "no importable sources found" in result.output
    assert "broken symlink" in result.output


def test_ingest_detect_skips_too_small_files(tmp_path: Path, monkeypatch) -> None:
    """Files under threshold (~200B) are placeholders, skip them."""
    runner = CliRunner()
    tiny = tmp_path / "CLAUDE.md"
    tiny.write_text("hi\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "placeholder?" in result.output


def test_ingest_detect_zero_found_gives_two_next_steps(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    # patch home so real ~/.claude/* doesn't bleed in
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "no importable sources found" in result.output
    assert "forge ingest --from" in result.output
    assert "$EDITOR sp/section/" in result.output


def test_ingest_detect_finds_claude_memory(tmp_path: Path, monkeypatch) -> None:
    """When ~/.claude/projects/*/memory/*.md exists, detect should surface it."""
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    # build a fake Claude Code memory layout
    mem_dir = tmp_path / ".claude" / "projects" / "-test-project" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "MEMORY.md").write_text("- [Some memory](file.md)\n", encoding="utf-8")
    (mem_dir / "feedback_x.md").write_text("Some feedback content here\n", encoding="utf-8")

    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "Claude auto-memory" in result.output
    assert "-test-project" in result.output
    assert "forge ingest --from-claude-memory" in result.output


def test_ingest_from_claude_memory_writes_section(tmp_path: Path, monkeypatch) -> None:
    """`forge ingest --from-claude-memory --no-llm` should pull all memory into a section."""
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])

    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".claude" / "projects" / "-test" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_x.md").write_text("user prefers Python\n", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from-claude-memory", "--no-llm", "--root", str(ws), "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    assert "1 Claude memory file" in result.output
    workspace_md = (ws / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "user prefers Python" in workspace_md
    assert "from: -test/feedback_x.md" in workspace_md  # provenance header preserved
