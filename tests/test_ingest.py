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
