"""CLI authority boundary for sibling Git worktrees."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner

from forge.cli import main


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_cli_refuses_to_escape_from_current_worktree_to_sibling_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    canonical = tmp_path / "personalOS"
    canonical.mkdir()
    _git(canonical, "init", "-b", "main")
    _git(canonical, "config", "user.name", "Forge Test")
    _git(canonical, "config", "user.email", "forge@example.com")
    (canonical / "README.md").write_text("# personalOS\n", encoding="utf-8")
    _git(canonical, "add", "README.md")
    _git(canonical, "commit", "-m", "base")

    isolated = tmp_path / "isolated"
    _git(canonical, "worktree", "add", "--detach", str(isolated))
    monkeypatch.chdir(isolated)

    result = CliRunner().invoke(
        main,
        ["run", "status", "--root", str(canonical)],
    )

    assert result.exit_code != 0
    assert "cross-worktree root" in result.output
    assert str(isolated) in result.output
    assert str(canonical) in result.output


def test_cli_accepts_the_current_detached_worktree_as_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    canonical = tmp_path / "personalOS"
    canonical.mkdir()
    _git(canonical, "init", "-b", "main")
    _git(canonical, "config", "user.name", "Forge Test")
    _git(canonical, "config", "user.email", "forge@example.com")
    (canonical / "README.md").write_text("# personalOS\n", encoding="utf-8")
    _git(canonical, "add", "README.md")
    _git(canonical, "commit", "-m", "base")

    isolated = tmp_path / "isolated"
    _git(canonical, "worktree", "add", "--detach", str(isolated))
    monkeypatch.chdir(isolated)

    result = CliRunner().invoke(
        main,
        ["run", "status", "--root", str(isolated)],
    )

    assert result.exit_code == 0, result.output

