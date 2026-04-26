"""Test forge target install/list/remove + auto-sync on approve."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.gate import actions as gate
from forge.gate.sync import install_target, list_targets, remove_target, TargetError


def _make_workspace(tmp_path: Path) -> Path:
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])
    runner.invoke(main, ["init", "--root", str(ws)])
    return ws


def test_install_target_copy_pushes_immediately(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external" / "CLAUDE.md"

    binding = install_target(ws, "claude-code", external, mode="copy")

    assert external.exists()
    assert binding["adapter"] == "claude-code"
    assert binding["mode"] == "copy"
    # content matches workspace output
    assert external.read_text("utf-8") == (ws / "output" / "CLAUDE.md").read_text("utf-8")


def test_install_target_symlink_creates_link(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external" / "CLAUDE.md"

    install_target(ws, "claude-code", external, mode="symlink")

    assert external.is_symlink()
    assert external.resolve() == (ws / "output" / "CLAUDE.md").resolve()


def test_install_target_refuses_existing_without_force(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    external.write_text("user wrote this", encoding="utf-8")

    with pytest.raises(TargetError, match="already exists"):
        install_target(ws, "claude-code", external)

    # still untouched
    assert external.read_text("utf-8") == "user wrote this"


def test_install_target_force_overwrites(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    external.write_text("user wrote this", encoding="utf-8")

    install_target(ws, "claude-code", external, mode="copy", force=True)

    assert "About me" in external.read_text("utf-8")


def test_install_target_unknown_adapter(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"

    with pytest.raises(TargetError, match="no config in sp/config/"):
        install_target(ws, "made-up-target", external)


def test_install_target_replaces_existing_binding(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"

    install_target(ws, "claude-code", first)
    install_target(ws, "claude-code", second)

    bindings = list_targets(ws)
    assert len(bindings) == 1
    assert bindings[0]["path"] == str(second.resolve())


def test_list_targets_empty(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    assert list_targets(ws) == []


def test_remove_target_keeps_file_by_default(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    install_target(ws, "claude-code", external)
    assert external.exists()

    removed = remove_target(ws, "claude-code")
    assert removed is not None
    assert list_targets(ws) == []
    # file still on disk
    assert external.exists()


def test_remove_target_with_delete_file(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    install_target(ws, "claude-code", external)

    remove_target(ws, "claude-code", delete_file=True)
    assert not external.exists()


def test_approve_auto_syncs_copy_mode(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    install_target(ws, "claude-code", external, mode="copy")

    # Edit a section
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\nNew preference body.\n",
        encoding="utf-8",
    )

    result = gate.approve(ws, note="test")
    assert result.targets_synced
    assert "New preference body" in external.read_text("utf-8")


def test_approve_skips_target_when_config_missing(tmp_path: Path) -> None:
    """If user removes the matching config, sync should skip silently, not crash."""
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"
    install_target(ws, "claude-code", external)

    # Now nuke the claude-code config
    (ws / "sp" / "config" / "claude-code.md").unlink()

    # Approve should still succeed (nothing to sync for that adapter now)
    result = gate.approve(ws, note="config gone")
    assert result.approved_hash
    # binding stays in manifest, just got skipped
    assert len(list_targets(ws)) == 1


def test_install_target_idempotent_for_symlink_pointing_here(tmp_path: Path) -> None:
    """Re-running install on an already-correct symlink shouldn't error."""
    ws = _make_workspace(tmp_path)
    external = tmp_path / "external.md"

    install_target(ws, "claude-code", external, mode="symlink")
    # Re-installing same binding without --force should work since target already
    # points at our output
    install_target(ws, "claude-code", external, mode="symlink")

    assert external.is_symlink()


def test_layout_migration_moves_old_paths(tmp_path: Path) -> None:
    """Old workspaces had .forge/output/ and .forge/changelog.md; migrate on touch."""
    ws = _make_workspace(tmp_path)

    # Manually rebuild old layout to simulate pre-v0.1.1 workspace
    new_output = ws / "output"
    new_changelog = ws / "CHANGELOG.md"
    legacy_output = ws / ".forge" / "output"
    legacy_changelog = ws / ".forge" / "changelog.md"

    import shutil
    if new_output.exists():
        shutil.move(str(new_output), str(legacy_output))
    if new_changelog.exists():
        shutil.move(str(new_changelog), str(legacy_changelog))
    assert legacy_output.exists()
    assert legacy_changelog.exists()
    assert not new_output.exists()
    assert not new_changelog.exists()

    # Any gate operation triggers migration
    gate.diff_summary(ws)

    assert new_output.exists()
    assert new_changelog.exists()
    assert not legacy_output.exists()
    assert not legacy_changelog.exists()
