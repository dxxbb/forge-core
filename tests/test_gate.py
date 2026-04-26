"""v0.2 gate tests: git is the substrate; HEAD is the approved baseline."""

from pathlib import Path

import pytest

from forge.gate import actions as gate
from forge.gate import _git


def test_workspace_fixture_is_git_repo(workspace: Path) -> None:
    """Sanity: fixture leaves a git repo with a clean HEAD."""
    assert _git.is_git_repo(workspace)
    assert _git.head_hash(workspace) is not None
    assert (workspace / "output" / "CLAUDE.md").exists()


def test_init_is_noop_on_already_initialized_workspace(workspace: Path) -> None:
    """v0.2: forge init is a no-op when workspace is already a git repo with sp/."""
    head_before = _git.head_hash(workspace)
    state = gate.init(workspace)
    assert state.initialized()
    assert _git.head_hash(workspace) == head_before


def test_init_force_no_op_on_clean_workspace(workspace: Path) -> None:
    """force=True on already-initialized workspace shouldn't blow up either."""
    gate.init(workspace, force=True)


def test_status_reports_no_drift_on_fresh_workspace(workspace: Path) -> None:
    info = gate.status(workspace)
    assert info["initialized"] is True
    assert info["drifted"] is False


def test_diff_clean_when_no_changes(workspace: Path) -> None:
    result = gate.diff_summary(workspace)
    assert not result.changed
    assert result.source_diff_lines == []
    assert result.output_diffs == {}


def test_diff_detects_source_and_output_changes(workspace: Path) -> None:
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha MODIFIED.\n", encoding="utf-8"
    )
    result = gate.diff_summary(workspace)
    assert result.changed
    assert result.source_diff_lines
    assert "main" in result.output_diffs


def test_approve_creates_git_commit(workspace: Path) -> None:
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha v2.\n", encoding="utf-8"
    )
    head_before = _git.head_hash(workspace)
    result = gate.approve(workspace, note="v2")
    head_after = _git.head_hash(workspace)

    # approved_hash IS the new git HEAD (not a separate forge hash)
    assert result.approved_hash == head_after
    assert head_after != head_before

    # after approve, diff should be clean (HEAD = working tree)
    assert not gate.diff_summary(workspace).changed
    # output reflects new content
    compiled = (workspace / "output" / "CLAUDE.md").read_text("utf-8")
    assert "Alpha v2" in compiled
    # commit subject = note
    log = _git.log_for_paths(workspace, ["sp"], max_count=1)
    assert log[0]["subject"] == "v2"
    # provenance trailer present
    assert "forge-provenance" in log[0]["provenance"] or "version=0.2" in log[0]["provenance"]


def test_approve_with_no_changes_raises(workspace: Path) -> None:
    """v0.2: approve when working tree matches HEAD should fail loudly, not silent-noop."""
    with pytest.raises(RuntimeError, match="no changes"):
        gate.approve(workspace, note="empty")


def test_reject_restores_from_HEAD(workspace: Path) -> None:
    p = workspace / "sp" / "section" / "alpha.md"
    original = p.read_text("utf-8")
    p.write_text("---\nname: alpha\n---\nGARBAGE\n", encoding="utf-8")
    gate.reject(workspace)
    assert p.read_text("utf-8") == original


def test_status_reports_drift(workspace: Path) -> None:
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\n---\nchanged\n", encoding="utf-8"
    )
    info = gate.status(workspace)
    assert info["drifted"] is True


def test_build_works_outside_git_substrate(workspace: Path) -> None:
    """build does not require gate state — useful in CI / fresh clones."""
    written = gate.build(workspace)
    assert any("CLAUDE.md" in str(p) for p in written)


def test_changelog_lives_in_git_log_not_a_file(workspace: Path) -> None:
    """v0.2: there is no CHANGELOG.md file; history is in git log."""
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha v2.\n", encoding="utf-8"
    )
    gate.approve(workspace, note="add v2")

    # No CHANGELOG.md as a file — git log carries the history
    assert not (workspace / "CHANGELOG.md").exists()

    # git log shows our commit
    entries = _git.log_for_paths(workspace, ["sp"])
    assert any(e["subject"] == "add v2" for e in entries)
