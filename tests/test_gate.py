from pathlib import Path

import pytest

from forge.gate import actions as gate


def test_init_creates_forge_dir(workspace: Path) -> None:
    state = gate.init(workspace)
    assert state.forge_dir.exists()
    assert state.approved_sp.exists()
    assert state.manifest_path.exists()
    assert state.changelog_path.exists()
    # outputs rebuilt
    assert (state.output_dir / "CLAUDE.md").exists()


def test_init_twice_raises(workspace: Path) -> None:
    gate.init(workspace)
    with pytest.raises(RuntimeError):
        gate.init(workspace)


def test_init_force_replaces(workspace: Path) -> None:
    gate.init(workspace)
    gate.init(workspace, force=True)  # must not raise


def test_status_reports_no_drift_on_fresh_init(workspace: Path) -> None:
    gate.init(workspace)
    info = gate.status(workspace)
    assert info["initialized"] is True
    assert info["drifted"] is False


def test_diff_clean_when_no_changes(workspace: Path) -> None:
    gate.init(workspace)
    result = gate.diff_summary(workspace)
    assert not result.changed
    assert result.source_diff_lines == []
    assert result.output_diffs == {}


def test_diff_detects_source_and_output_changes(workspace: Path) -> None:
    gate.init(workspace)
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha MODIFIED.\n", encoding="utf-8"
    )
    result = gate.diff_summary(workspace)
    assert result.changed
    assert result.source_diff_lines
    assert "main" in result.output_diffs


def test_approve_promotes_and_rebuilds(workspace: Path) -> None:
    gate.init(workspace)
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha v2.\n", encoding="utf-8"
    )
    result = gate.approve(workspace, note="v2")
    assert result.approved_hash
    # after approve, diff should be clean
    assert not gate.diff_summary(workspace).changed
    # output reflects new content
    compiled = (workspace / ".forge" / "output" / "CLAUDE.md").read_text("utf-8")
    assert "Alpha v2" in compiled
    # changelog has the note
    log = (workspace / ".forge" / "changelog.md").read_text("utf-8")
    assert "v2" in log


def test_reject_restores_approved(workspace: Path) -> None:
    gate.init(workspace)
    p = workspace / "sp" / "section" / "alpha.md"
    original = p.read_text("utf-8")
    p.write_text("---\nname: alpha\n---\nGARBAGE\n", encoding="utf-8")
    gate.reject(workspace)
    assert p.read_text("utf-8") == original


def test_status_reports_drift(workspace: Path) -> None:
    gate.init(workspace)
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\n---\nchanged\n", encoding="utf-8"
    )
    info = gate.status(workspace)
    assert info["drifted"] is True


def test_build_without_init_works(workspace: Path) -> None:
    """build does NOT require .forge/ — it's for CI / fresh clones."""
    written = gate.build(workspace)
    assert any("CLAUDE.md" in str(p) for p in written)
