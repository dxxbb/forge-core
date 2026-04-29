"""Test forge ingest: dump path (default) + emit path (agent-driven)."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.ingest import classify, write_sections, IngestError


def test_default_classify_dumps_into_workspace_section() -> None:
    text = "I am a backend engineer. I prefer Python."
    result = classify(text)
    assert result.method == "dump"
    assert result.sections["workspace"] == text
    for k in ("about-me", "preferences", "knowledge-base", "skills"):
        assert result.sections[k] == ""


def test_dump_writes_into_workspace(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    src = tmp_path / "input.md"
    src.write_text("Some content here.\nMore content.", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(tmp_path / "ws"), "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "Some content here." in workspace_md
    assert "Review carefully" in workspace_md  # provenance note


def test_ingest_refuses_missing_workspace(tmp_path: Path) -> None:
    src = tmp_path / "input.md"
    src.write_text("hi", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(tmp_path / "no-ws")],
    )
    assert result.exit_code == 1
    assert "not a forge workspace" in result.output


def test_ingest_refuses_missing_input(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    result = runner.invoke(main, ["ingest", "--root", str(tmp_path / "ws")])
    assert result.exit_code == 1
    assert "must pass --from" in result.output


def test_ingest_overwrite_refused_for_user_content(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    workspace_md = tmp_path / "ws" / "sp" / "section" / "workspace.md"
    workspace_md.write_text(
        "---\nname: workspace\ntype: workspace\n---\n\nuser real content\n",
        encoding="utf-8",
    )

    src = tmp_path / "input.md"
    src.write_text("new content from import", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_ingest_overwrites_template_placeholder(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    src = tmp_path / "input.md"
    src.write_text("imported content", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "imported content" in workspace_md
    assert "[TODO:" not in workspace_md


def test_ingest_stdin(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    result = runner.invoke(
        main,
        ["ingest", "--from-stdin", "--root", str(tmp_path / "ws"), "--overwrite"],
        input="content from stdin",
    )
    assert result.exit_code == 0, result.output
    workspace_md = (tmp_path / "ws" / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "content from stdin" in workspace_md


# ---------- forge ingest --emit (agent-driven) ----------


def test_emit_prints_to_stdout_no_disk_write(tmp_path: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    src = tmp_path / "input.md"
    src.write_text("the source content", encoding="utf-8")

    workspace_md = tmp_path / "ws" / "sp" / "section" / "workspace.md"
    before = workspace_md.read_text("utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--emit", "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 0, result.output
    assert "the source content" in result.output  # printed to stdout
    # disk untouched (workspace.md still has TODO template)
    assert workspace_md.read_text("utf-8") == before


def test_emit_records_origin_event_for_review(tmp_path: Path) -> None:
    """--emit should still record an origin event so `forge review` shows
    'agent will classify' even before agent writes the sections."""
    from forge.gate.origin import read_pending

    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])
    src = tmp_path / "input.md"
    src.write_text("source content", encoding="utf-8")

    runner.invoke(
        main,
        ["ingest", "--from", str(src), "--emit", "--root", str(tmp_path / "ws")],
    )
    events = read_pending(tmp_path / "ws")
    assert len(events) == 1
    assert "--emit" in events[0].summary
    assert "agent will classify" in events[0].summary


def test_emit_with_claude_memory(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".claude" / "projects" / "-test" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback.md").write_text("user prefers Python", encoding="utf-8")
    (mem_dir / "user_role.md").write_text("user is backend engineer", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from-claude-memory", "--emit", "--root", str(tmp_path / "ws")],
    )
    assert result.exit_code == 0, result.output
    # both files appear in stdout, with provenance headers
    assert "user prefers Python" in result.output
    assert "user is backend engineer" in result.output
    assert "from: -test/feedback.md" in result.output
    assert "from: -test/user_role.md" in result.output


# ---------- forge ingest --detect ----------


def test_ingest_detect_finds_real_file_in_cwd(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    real = tmp_path / "CLAUDE.md"
    real.write_text("# real claude.md\n" + ("filler\n" * 50), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "found 1 importable" in result.output
    assert "CLAUDE.md" in result.output


def test_ingest_detect_skips_broken_symlink(tmp_path: Path, monkeypatch) -> None:
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
    monkeypatch.setenv("HOME", str(tmp_path))
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "no importable sources found" in result.output
    assert "forge ingest --from" in result.output
    assert "$EDITOR sp/section/" in result.output


def test_ingest_detect_finds_claude_memory(tmp_path: Path, monkeypatch) -> None:
    runner = CliRunner()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    mem_dir = tmp_path / ".claude" / "projects" / "-test-project" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "MEMORY.md").write_text("- [Some memory](file.md)\n", encoding="utf-8")
    (mem_dir / "feedback_x.md").write_text("Some feedback content here\n", encoding="utf-8")

    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    assert "Claude auto-memory" in result.output
    assert "-test-project" in result.output
    assert "forge ingest --from-claude-memory" in result.output


def test_ingest_from_claude_memory_dump_writes_section(tmp_path: Path, monkeypatch) -> None:
    """Default dump mode: --from-claude-memory should pull all memory into workspace.md."""
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])

    monkeypatch.setenv("HOME", str(tmp_path))
    mem_dir = tmp_path / ".claude" / "projects" / "-test" / "memory"
    mem_dir.mkdir(parents=True)
    (mem_dir / "feedback_x.md").write_text("user prefers Python\n", encoding="utf-8")

    result = runner.invoke(
        main,
        ["ingest", "--from-claude-memory", "--root", str(ws), "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (ws / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "user prefers Python" in workspace_md
    assert "from: -test/feedback_x.md" in workspace_md


# ---------- personalOS capture + monitor ----------


def _make_personalos(root: Path) -> None:
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)
    (root / "context build" / "sections" / "about.md").write_text(
        "---\nname: about\n---\n\nbody\n", encoding="utf-8"
    )
    (root / "context build" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections:\n  - about\n---\n",
        encoding="utf-8",
    )


def test_capture_writes_raw_import_and_inbox(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = tmp_path / "personal"
    _make_personalos(ws)
    src = tmp_path / "note.md"
    src.write_text("hello import\n", encoding="utf-8")

    result = runner.invoke(main, ["capture", "--root", str(ws), "--from", str(src)])

    assert result.exit_code == 0, result.output
    assert "captured raw import:" in result.output
    raw_files = list((ws / "capture" / "import").glob("*/*.md"))
    inbox_files = list((ws / "system" / "inbox").glob("*.md"))
    assert len(raw_files) == 1
    assert len(inbox_files) == 1
    raw = raw_files[0].read_text("utf-8")
    assert "kind: raw import" in raw
    assert "source_digest:" in raw
    assert "hello import" in raw
    assert "status: pending" in inbox_files[0].read_text("utf-8")


def test_monitor_reports_clean_after_captured_source_when_no_pending(tmp_path: Path, monkeypatch) -> None:
    from forge.gate import _git
    from forge.gate import actions as gate

    runner = CliRunner()
    ws = tmp_path / "personal"
    _make_personalos(ws)
    _git.init_repo(ws)
    gate.build(ws)
    _git.add(ws, ["context build"])
    _git.commit(ws, "init")

    src = tmp_path / "CLAUDE.md"
    src.write_text("# Context\n" + ("same\n" * 60), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(main, ["capture", "--root", str(ws), "--from", str(src)])
    assert result.exit_code == 0, result.output
    for inbox in (ws / "system" / "inbox").glob("*.md"):
        inbox.write_text(inbox.read_text("utf-8").replace("status: pending", "status: applied"), encoding="utf-8")

    result = runner.invoke(main, ["monitor", "--root", str(ws)])

    assert result.exit_code == 0, result.output
    assert "status: clean" in result.output


def test_monitor_detects_changed_captured_source(tmp_path: Path, monkeypatch) -> None:
    from forge.gate import _git
    from forge.gate import actions as gate

    runner = CliRunner()
    ws = tmp_path / "personal"
    _make_personalos(ws)
    _git.init_repo(ws)
    gate.build(ws)
    _git.add(ws, ["context build"])
    _git.commit(ws, "init")

    src = tmp_path / "CLAUDE.md"
    src.write_text("# Context\n" + ("before\n" * 60), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(main, ["capture", "--root", str(ws), "--from", str(src)])
    assert result.exit_code == 0, result.output
    for inbox in (ws / "system" / "inbox").glob("*.md"):
        inbox.write_text(inbox.read_text("utf-8").replace("status: pending", "status: applied"), encoding="utf-8")
    src.write_text("# Context\n" + ("after\n" * 60), encoding="utf-8")

    result = runner.invoke(main, ["monitor", "--root", str(ws)])

    assert result.exit_code == 0, result.output
    assert "status: attention" in result.output
    assert "import source updates" in result.output
    assert "CLAUDE.md" in result.output
