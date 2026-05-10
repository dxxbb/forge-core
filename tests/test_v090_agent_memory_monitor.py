"""v0.9.0: Claude auto-memory as a first-class governed source.

Restores the v0.2 capability (commit 95d9240, 2026-04-26) that was lost when
monitor abstraction landed in v0.4.0+ — Claude auto-memory files
(`~/.claude/projects/<slug>/memory/*.md`) are now watched by `forge monitor`
the same way workspace-project drift, web clippings, and internal content
changes are.

Tests cover:

  - first activation establishes a baseline silently (no inbox flood)
  - new memory file → monitor reports + suggests `forge capture --from`
  - modified memory file (hash drift) → monitor reports
  - unchanged file → monitor stays silent
  - `MEMORY.md` index file is excluded
  - workspace with no Claude project dir (e.g. fresh personalOS that's never
    been opened in Claude Code) → silent
  - `forge capture --from <memory file>` updates state (mark-seen)
  - state file location: `.forge/agent_memory_state.json`
  - cli integration: `forge monitor` surfaces the section
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.claude_memory import (
    MemoryState,
    compute_diff,
    discover_memory_files,
    format_monitor_lines,
    is_memory_file,
    load_state,
    mark_path_seen,
    mark_seen,
    memory_dir_for_slug,
    save_state,
    scan_all_projects,
    slug_for_memory_path,
    state_path,
    workspace_to_slug,
)


# ---------- fixtures ----------


def _make_personalos_root(tmp_path: Path) -> Path:
    """Minimal personalOS layout — capture/import + system/inbox + .forge/."""
    root = tmp_path / "ws"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / ".forge").mkdir(parents=True)
    return root


def _make_claude_layout(home: Path, slug: str) -> Path:
    """Create `<home>/.claude/projects/<slug>/memory/` and return the memory dir."""
    mem_dir = home / ".claude" / "projects" / slug / "memory"
    mem_dir.mkdir(parents=True)
    return mem_dir


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect Path.home() to a tmp dir for hermetic tests."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    # Some Path.home() implementations consult USERPROFILE on Windows; we
    # don't care here, but be defensive against env leakage.
    monkeypatch.delenv("USERPROFILE", raising=False)
    return home


# ---------- slug derivation ----------


def test_workspace_to_slug_replaces_slashes() -> None:
    # Use a concrete fake path; workspace_to_slug calls .resolve()
    p = Path("/Users/foo/personalOS")
    assert workspace_to_slug(p) == "-Users-foo-personalOS"


def test_workspace_to_slug_resolves_relative(tmp_path: Path) -> None:
    abs_workspace = tmp_path / "ws"
    abs_workspace.mkdir()
    expected = str(abs_workspace.resolve()).replace("/", "-")
    assert workspace_to_slug(abs_workspace) == expected


# ---------- discover ----------


def test_discover_memory_files_excludes_memory_md(fake_home: Path) -> None:
    slug = "-test-slug"
    mem = _make_claude_layout(fake_home, slug)
    (mem / "MEMORY.md").write_text("- index entry\n", encoding="utf-8")
    (mem / "feedback_one.md").write_text(
        "---\nname: one\ntype: feedback\n---\nrule one body\n",
        encoding="utf-8",
    )

    out = discover_memory_files(slug)
    names = [f.name for f in out]
    assert names == ["feedback_one.md"]
    assert "MEMORY.md" not in names


def test_discover_memory_files_returns_empty_for_missing_slug(fake_home: Path) -> None:
    assert discover_memory_files("-nonexistent-slug") == []


def test_discover_memory_files_hashes_content(fake_home: Path) -> None:
    slug = "-test-slug"
    mem = _make_claude_layout(fake_home, slug)
    (mem / "rule.md").write_text("body A", encoding="utf-8")

    [f] = discover_memory_files(slug)
    assert f.name == "rule.md"
    assert len(f.sha256) == 64  # sha256 hex
    assert f.size == len(b"body A")


# ---------- baseline-on-activation ----------


def test_format_monitor_lines_first_activation_writes_baseline(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "rule_a.md").write_text("a body", encoding="utf-8")
    (mem / "rule_b.md").write_text("b body", encoding="utf-8")
    (mem / "MEMORY.md").write_text("- index\n", encoding="utf-8")

    # State file must not exist yet
    assert not state_path(workspace).exists()

    issues, actions = format_monitor_lines(workspace)

    # Baseline: one info issue, no per-file actions
    assert any("initialized baseline" in i for i in issues)
    assert "2 files tracked" in issues[0]  # MEMORY.md excluded
    assert actions == []

    # State file now exists, with both files baselined
    state = load_state(workspace)
    assert state is not None
    assert len(state.last_seen) == 2


def test_format_monitor_lines_silent_when_no_claude_dir(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    # No `~/.claude/projects/<slug>/memory/` exists
    issues, actions = format_monitor_lines(workspace)
    assert issues == []
    assert actions == []
    # No state file is created when there's no claude dir
    assert not state_path(workspace).exists()


def test_format_monitor_lines_silent_when_baselined_and_unchanged(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "rule.md").write_text("body", encoding="utf-8")

    # First call: baseline
    format_monitor_lines(workspace)
    # Second call: no drift
    issues, actions = format_monitor_lines(workspace)
    assert issues == []
    assert actions == []


# ---------- new / modified detection ----------


def test_new_memory_file_after_baseline_triggers_action(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "old.md").write_text("old body", encoding="utf-8")

    # First call: baseline
    format_monitor_lines(workspace)

    # Agent writes a new memory file
    (mem / "new_rule.md").write_text("new rule body", encoding="utf-8")

    issues, actions = format_monitor_lines(workspace)
    assert any("agent-memory updates" in i and "new 1" in i for i in issues)
    assert any(
        "agent-memory NEW" in a and "new_rule.md" in a for a in actions
    )
    # Suggested capture command is included
    assert any("forge capture --from" in a for a in actions)


def test_modified_memory_file_triggers_action(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text("v1 body", encoding="utf-8")

    # Baseline
    format_monitor_lines(workspace)

    # Agent edits the memory file
    f.write_text("v2 body, expanded", encoding="utf-8")

    issues, actions = format_monitor_lines(workspace)
    assert any("modified 1" in i for i in issues)
    assert any("agent-memory MODIFIED" in a and "rule.md" in a for a in actions)


def test_deleted_memory_file_silent_and_pruned(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text("body", encoding="utf-8")

    # Baseline includes the file
    format_monitor_lines(workspace)
    state = load_state(workspace)
    assert state is not None and len(state.last_seen) == 1

    # Agent deletes the file
    f.unlink()

    issues, actions = format_monitor_lines(workspace)
    # Silent: deletes don't surface as monitor actions
    assert issues == []
    assert actions == []

    # But state was pruned
    state = load_state(workspace)
    assert state is not None and len(state.last_seen) == 0


def test_memory_md_changes_never_surface(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "rule.md").write_text("body", encoding="utf-8")
    (mem / "MEMORY.md").write_text("- v1 index\n", encoding="utf-8")

    # Baseline
    format_monitor_lines(workspace)

    # MEMORY.md churns (typical when agents add/remove memory entries)
    (mem / "MEMORY.md").write_text("- v2 index\n- another\n", encoding="utf-8")

    issues, actions = format_monitor_lines(workspace)
    assert issues == []
    assert actions == []


# ---------- mark-seen at capture ----------


def test_is_memory_file_recognizes_layout(tmp_path: Path, fake_home: Path) -> None:
    slug = "-test-slug"
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text("body", encoding="utf-8")

    assert is_memory_file(f)
    assert not is_memory_file(mem / "MEMORY.md")  # excluded by name (even if exists)
    assert not is_memory_file(tmp_path / "unrelated.md")


def test_slug_for_memory_path(fake_home: Path) -> None:
    slug = "-Users-foo-personalOS"
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text("body", encoding="utf-8")

    assert slug_for_memory_path(f) == slug
    assert slug_for_memory_path(Path("/tmp/random.md")) == ""


def test_mark_path_seen_updates_state(tmp_path: Path, fake_home: Path) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text("v1", encoding="utf-8")

    ok = mark_path_seen(workspace, f)
    assert ok

    state = load_state(workspace)
    assert state is not None
    assert str(f.resolve()) in state.last_seen
    assert len(state.last_seen[str(f.resolve())]["hash"]) == 64


def test_mark_path_seen_silent_for_non_memory_file(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    f = tmp_path / "random.md"
    f.write_text("body", encoding="utf-8")

    ok = mark_path_seen(workspace, f)
    assert not ok
    # No state file created for unrelated path
    assert not state_path(workspace).exists()


def test_capture_from_memory_path_marks_seen(
    tmp_path: Path, fake_home: Path
) -> None:
    """End-to-end: `forge capture --from <memory file>` updates state.

    A subsequent `forge monitor` run should NOT re-report the same file.
    """
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    f = mem / "rule.md"
    f.write_text(
        "---\nname: rule\ntype: feedback\n---\nbody\n", encoding="utf-8"
    )

    runner = CliRunner()
    res = runner.invoke(
        cli_main,
        ["capture", "--root", str(workspace), "--from", str(f)],
    )
    assert res.exit_code == 0, res.output

    # State was created with this file's hash
    state = load_state(workspace)
    assert state is not None
    assert str(f.resolve()) in state.last_seen

    # Monitor on a workspace whose state already covers the file → silent
    issues, actions = format_monitor_lines(workspace)
    assert issues == []
    assert actions == []


# ---------- state file location and schema ----------


def test_state_file_location_is_dot_forge(tmp_path: Path) -> None:
    workspace = _make_personalos_root(tmp_path)
    expected = workspace / ".forge" / "agent_memory_state.json"
    assert state_path(workspace) == expected


def test_state_serialization_round_trip(tmp_path: Path) -> None:
    workspace = _make_personalos_root(tmp_path)
    state = MemoryState()
    state.last_seen["/abs/path.md"] = {
        "hash": "abc",
        "size": 123,
        "seen_at": "2026-05-09T12:00:00+00:00",
    }
    save_state(workspace, state)

    loaded = load_state(workspace)
    assert loaded is not None
    assert loaded.last_seen == state.last_seen


def test_state_file_is_valid_json(tmp_path: Path, fake_home: Path) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "rule.md").write_text("body", encoding="utf-8")

    format_monitor_lines(workspace)

    raw = state_path(workspace).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert parsed["schema_version"] == 1
    assert "last_seen" in parsed


# ---------- cross-slug isolation ----------


def test_default_scope_only_watches_current_workspace_slug(
    tmp_path: Path, fake_home: Path
) -> None:
    """A new memory file under a DIFFERENT slug must not trigger this
    workspace's monitor — scope is the workspace's matched slug only.
    """
    workspace = _make_personalos_root(tmp_path)
    slug_self = workspace_to_slug(workspace)
    slug_other = "-some-other-project"

    mem_self = _make_claude_layout(fake_home, slug_self)
    (mem_self / "self.md").write_text("self", encoding="utf-8")
    mem_other = _make_claude_layout(fake_home, slug_other)
    (mem_other / "other.md").write_text("other", encoding="utf-8")

    # Baseline this workspace
    format_monitor_lines(workspace)

    # Add a new file under the OTHER slug
    (mem_other / "new_other.md").write_text("new other body", encoding="utf-8")

    issues, actions = format_monitor_lines(workspace)
    assert issues == []
    assert actions == []


# ---------- compatibility: ingest --detect path still works ----------


def test_scan_all_projects_excludes_memory_md(fake_home: Path) -> None:
    """The `forge ingest --detect` compat shim shouldn't count MEMORY.md."""
    slug = "-detect-slug"
    mem = _make_claude_layout(fake_home, slug)
    (mem / "feedback_x.md").write_text("body", encoding="utf-8")
    (mem / "MEMORY.md").write_text("- index\n", encoding="utf-8")

    out = scan_all_projects()
    assert len(out) == 1
    found_slug, count, _ = out[0]
    assert found_slug == slug
    assert count == 1  # MEMORY.md not counted


# ---------- monitor cli integration ----------


def test_monitor_cli_reports_agent_memory_drift(
    tmp_path: Path, fake_home: Path
) -> None:
    workspace = _make_personalos_root(tmp_path)
    slug = workspace_to_slug(workspace)
    mem = _make_claude_layout(fake_home, slug)
    (mem / "old.md").write_text("v1", encoding="utf-8")

    runner = CliRunner()
    # First run: baseline (so the monitor info-line appears once, then state
    # exists; a clean second run should not add new actions).
    runner.invoke(cli_main, ["monitor", "--root", str(workspace)])

    # Add a new memory file
    (mem / "new_rule.md").write_text("new body", encoding="utf-8")

    res = runner.invoke(cli_main, ["monitor", "--root", str(workspace)])
    # We don't assert on exit code (monitor exits 1 when status=attention,
    # which is exactly what we want here) but on output content.
    assert "agent-memory" in res.output
    assert "new_rule.md" in res.output
