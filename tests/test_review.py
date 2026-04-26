"""Test the one-screen review: origin tracking, semantic summary, affects, bench, diff."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.gate import actions as gate
from forge.gate.origin import (
    OriginEvent,
    clear,
    read_pending,
    record_event,
)
from forge.gate.review import build_review, _semantic_summary


def _ws(tmp_path: Path) -> Path:
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])
    runner.invoke(main, ["init", "--root", str(ws)])
    return ws


# ---------- origin tracking ----------

def test_record_and_read_pending(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    record_event(
        ws,
        kind="ingest",
        summary="forge ingest --from /tmp/foo.md",
        details={"source": "/tmp/foo.md"},
        sections_touched=["preferences", "workspace"],
    )
    events = read_pending(ws)
    assert len(events) == 1
    assert events[0].kind == "ingest"
    assert events[0].sections_touched == ["preferences", "workspace"]


def test_clear_pending_removes_file(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    record_event(ws, kind="hand-edit", summary="test")
    assert read_pending(ws)
    clear(ws)
    assert read_pending(ws) == []


def test_approve_clears_pending(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    record_event(ws, kind="ingest", summary="something")
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- new rule\n",
        encoding="utf-8",
    )
    gate.approve(ws, note="test")
    assert read_pending(ws) == []


def test_reject_clears_pending(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    record_event(ws, kind="ingest", summary="something")
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- new rule\n",
        encoding="utf-8",
    )
    gate.reject(ws)
    assert read_pending(ws) == []


# ---------- semantic summary ----------

def test_semantic_summary_detects_filled_todo() -> None:
    before = "---\nname: foo\n---\n\n[TODO: write your stuff here]\n"
    after = "---\nname: foo\n---\n\n- I prefer Python\n- No emoji\n"
    summary = _semantic_summary("foo", before, after)
    assert "filled 1 TODO" in summary
    assert "+2 bullet" in summary


def test_semantic_summary_detects_subsection_change() -> None:
    before = "---\nname: foo\n---\n\n# A\n# B\n## C\n"
    after = "---\nname: foo\n---\n\n# A\n# B\n## C\n## D\n## E\n"
    summary = _semantic_summary("foo", before, after)
    assert "+2 subsections" in summary


def test_semantic_summary_falls_back_to_bytes_for_pure_body_edit() -> None:
    before = "---\nname: foo\n---\n\nplain text body\n"
    after = "---\nname: foo\n---\n\nplain text body, edited\n"
    summary = _semantic_summary("foo", before, after)
    # No TODO/bullet/heading change → fallback to byte delta
    assert "body edits" in summary or "B" in summary


# ---------- review build ----------

def test_review_no_changes(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    rev = build_review(ws)
    assert not rev.has_changes


def test_review_with_hand_edit_no_origin(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- 不要加 emoji\n",
        encoding="utf-8",
    )
    rev = build_review(ws)
    assert rev.has_changes
    assert rev.origin_events == []  # no recorded event for hand edit
    assert len(rev.section_changes) == 1
    assert rev.section_changes[0].name == "preferences"
    assert rev.output_changes  # configs affected


def test_review_with_ingest_event(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws(tmp_path)
    src = tmp_path / "input.md"
    src.write_text("imported content", encoding="utf-8")
    runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(ws)],
    )
    rev = build_review(ws)
    assert rev.has_changes
    assert len(rev.origin_events) == 1
    assert rev.origin_events[0].kind == "ingest"
    assert "input.md" in rev.origin_events[0].summary


def test_review_affects_includes_targets(tmp_path: Path) -> None:
    """Affects panel should list configured target bindings."""
    from forge.gate.sync import install_target

    ws = _ws(tmp_path)
    external = tmp_path / "external.md"
    install_target(ws, "claude-code", external, mode="copy")

    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- new rule\n",
        encoding="utf-8",
    )
    rev = build_review(ws)
    assert rev.target_bindings
    assert rev.target_bindings[0].adapter == "claude-code"


# ---------- CLI integration ----------

def test_forge_review_no_changes_message(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws(tmp_path)
    res = runner.invoke(main, ["review", "--root", str(ws), "--no-pager", "--no-color"])
    assert res.exit_code == 0
    assert "no changes" in res.output


def test_forge_review_renders_all_panels(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws(tmp_path)
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- 不要加 emoji\n- 用 type hints\n",
        encoding="utf-8",
    )
    res = runner.invoke(
        main,
        ["review", "--root", str(ws), "--no-pager", "--no-color", "--summary-only"],
    )
    assert res.exit_code == 0, res.output
    assert "Source" in res.output
    assert "What changed" in res.output
    assert "Affects" in res.output
    assert "Bench" in res.output
    assert "preferences.md" in res.output
    assert "Claude Code" in res.output  # adapter description


def test_forge_review_full_includes_diff(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws(tmp_path)
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- 不要加 emoji\n",
        encoding="utf-8",
    )
    res = runner.invoke(
        main, ["review", "--root", str(ws), "--no-pager", "--no-color"]
    )
    assert res.exit_code == 0
    assert "source diff (sp/)" in res.output  # raw diff section present
    assert "summary:" in res.output  # diff summary header


def test_forge_review_origin_panel_shows_ingest_command(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws(tmp_path)
    src = tmp_path / "import-source.md"
    src.write_text("imported content for test", encoding="utf-8")
    runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(ws)],
    )
    res = runner.invoke(
        main,
        ["review", "--root", str(ws), "--no-pager", "--no-color", "--summary-only"],
    )
    assert res.exit_code == 0
    assert "forge ingest --from" in res.output
    assert "import-source.md" in res.output
    assert "(dump)" in res.output  # method indicator in origin summary
