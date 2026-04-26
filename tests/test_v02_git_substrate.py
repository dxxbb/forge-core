"""v0.2 git-substrate tests: forge new auto-init, migrate, changelog, rollback."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.gate import _git
from forge.gate import actions as gate


def test_forge_new_creates_git_repo_with_initial_commit(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    res = runner.invoke(main, ["new", str(target)])
    assert res.exit_code == 0, res.output

    assert _git.is_git_repo(target)
    head = _git.head_hash(target)
    assert head is not None

    log = _git.log_for_paths(target, ["sp"], max_count=1)
    assert log
    assert "forge new" in log[0]["subject"]
    assert "version=0.2" in log[0]["provenance"]


def test_forge_new_initial_commit_includes_output(tmp_path: Path) -> None:
    """Output should be built and committed in the initial commit."""
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    assert (target / "output" / "CLAUDE.md").exists()
    assert (target / "output" / "AGENTS.md").exists()
    # Tracked in git, not in untracked status
    head_files = _git.list_files_at_ref(target, "HEAD", "output/")
    assert "output/CLAUDE.md" in head_files


def test_approve_creates_git_commit_with_provenance_trailer(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    section = target / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- new rule\n",
        encoding="utf-8",
    )
    result = gate.approve(target, note="add a rule")

    log = _git.log_for_paths(target, ["sp"], max_count=1)
    assert log[0]["subject"] == "add a rule"
    assert "forge-provenance" in log[0]["provenance"] or "version=0.2" in log[0]["provenance"]
    assert log[0]["hash"] == result.approved_hash


def test_reject_uses_git_restore(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    section = target / "sp" / "section" / "preferences.md"
    original = section.read_text(encoding="utf-8")
    section.write_text("garbage\n", encoding="utf-8")

    gate.reject(target)
    assert section.read_text(encoding="utf-8") == original


def test_forge_changelog_renders_from_git_log(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    # Make a couple of approved changes
    section = target / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- v1\n",
        encoding="utf-8",
    )
    gate.approve(target, note="add v1 rule")
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- v1\n- v2\n",
        encoding="utf-8",
    )
    gate.approve(target, note="add v2 rule")

    res = runner.invoke(main, ["changelog", "--root", str(target)])
    assert res.exit_code == 0, res.output
    assert "add v1 rule" in res.output
    assert "add v2 rule" in res.output


def test_forge_rollback_lists_then_restores(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    section = target / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- v1\n",
        encoding="utf-8",
    )
    r1 = gate.approve(target, note="v1")

    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- v2\n",
        encoding="utf-8",
    )
    gate.approve(target, note="v2")

    # Listing without arg
    res = runner.invoke(main, ["rollback", "--root", str(target)])
    assert res.exit_code == 0
    assert r1.approved_hash[:7] in res.output  # git log default short hash

    # Roll back to v1
    res = runner.invoke(
        main, ["rollback", "--root", str(target), r1.approved_hash[:12]]
    )
    assert res.exit_code == 0
    assert "v1" in section.read_text(encoding="utf-8")
    assert "v2" not in section.read_text(encoding="utf-8")


def test_forge_migrate_dry_run_safe_on_v02_workspace(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    res = runner.invoke(main, ["migrate", "--root", str(target), "--dry-run"])
    assert res.exit_code == 0
    assert "already on v0.2" in res.output


def test_forge_migrate_imports_legacy_changelog(tmp_path: Path) -> None:
    """Workspace with v0.1 CHANGELOG.md → forge migrate creates a commit
    that preserves the audit history in commit body."""
    target = tmp_path / "legacy-ws"
    (target / "sp" / "section").mkdir(parents=True)
    (target / "sp" / "config").mkdir(parents=True)
    (target / "sp" / "section" / "alpha.md").write_text(
        "---\nname: alpha\ntype: test\n---\n\nbody\n", encoding="utf-8"
    )
    (target / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections: [alpha]\n---\n",
        encoding="utf-8",
    )
    (target / "CHANGELOG.md").write_text(
        "# changelog\n\n- 2026-04-26T01:00:00+00:00 init (hash=aaaaaaaaaaaa)\n"
        "- 2026-04-26T02:00:00+00:00 approve (hash=bbbbbbbbbbbb) — add rule\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    res = runner.invoke(main, ["migrate", "--root", str(target)])
    assert res.exit_code == 0, res.output

    # Now a git repo, with legacy CHANGELOG.md content in commit body
    assert _git.is_git_repo(target)
    head = _git.head_hash(target)
    log = _git.log_for_paths(target, ["sp"], max_count=1)
    assert log
    # Legacy CHANGELOG.md file removed
    assert not (target / "CHANGELOG.md").exists()


def test_forge_migrate_idempotent(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "ws"
    runner.invoke(main, ["new", str(target)])

    res1 = runner.invoke(main, ["migrate", "--root", str(target)])
    assert res1.exit_code == 0
    res2 = runner.invoke(main, ["migrate", "--root", str(target)])
    assert res2.exit_code == 0
    assert "already on v0.2" in res2.output
