"""Test for `forge new <path>` scaffolding command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def test_forge_new_scaffolds_workspace(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-ctx"
    result = runner.invoke(main, ["new", str(target)])
    assert result.exit_code == 0, result.output

    assert (target / "sp" / "section" / "about-me.md").exists()
    assert (target / "sp" / "config" / "personal.md").exists()
    assert (target / ".gitignore").exists()

    section = (target / "sp" / "section" / "about-me.md").read_text("utf-8")
    assert "name: about-me" in section
    assert "identity" in section

    config = (target / "sp" / "config" / "personal.md").read_text("utf-8")
    assert "target: claude-code" in config
    assert "about-me" in config


def test_forge_new_refuses_existing_path(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    runner = CliRunner()
    result = runner.invoke(main, ["new", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_forge_new_output_compiles_immediately(tmp_path: Path) -> None:
    """Workspace scaffolded by `forge new` should be immediately usable by `forge init`."""
    runner = CliRunner()
    target = tmp_path / "pipeline-test"
    runner.invoke(main, ["new", str(target)])

    result = runner.invoke(main, ["init", "--root", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / ".forge" / "output" / "CLAUDE.md").exists()

    compiled = (target / ".forge" / "output" / "CLAUDE.md").read_text("utf-8")
    assert "About me" in compiled
