"""Test for `forge new <path>` scaffolding command."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def test_forge_new_scaffolds_full_workspace_by_default(tmp_path: Path) -> None:
    """Default: 5 SP sections + 1 wrapper + 2 cross-runtime configs."""
    runner = CliRunner()
    target = tmp_path / "my-ctx"
    result = runner.invoke(main, ["new", str(target)])
    assert result.exit_code == 0, result.output

    section_dir = target / "sp" / "section"
    for name in (
        "_preface.md",
        "about-me.md",
        "preferences.md",
        "workspace.md",
        "knowledge-base.md",
        "skills.md",
    ):
        assert (section_dir / name).exists(), f"missing {name}"

    config_dir = target / "sp" / "config"
    assert (config_dir / "claude-code.md").exists()
    assert (config_dir / "agents-md.md").exists()

    assert (target / ".gitignore").exists()

    section = (section_dir / "about-me.md").read_text("utf-8")
    assert "name: about-me" in section
    assert "identity" in section
    assert "[TODO:" in section  # placeholder marker visible

    claude_cfg = (config_dir / "claude-code.md").read_text("utf-8")
    assert "target: claude-code" in claude_cfg
    assert "about-me" in claude_cfg
    assert "_preface" in claude_cfg

    agents_cfg = (config_dir / "agents-md.md").read_text("utf-8")
    assert "target: agents-md" in agents_cfg


def test_forge_new_minimal_one_section(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-min"
    result = runner.invoke(main, ["new", str(target), "--minimal"])
    assert result.exit_code == 0, result.output
    section_dir = target / "sp" / "section"
    config_dir = target / "sp" / "config"
    assert (section_dir / "about-me.md").exists()
    assert not (section_dir / "preferences.md").exists()
    assert (config_dir / "personal.md").exists()
    assert not (config_dir / "claude-code.md").exists()


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
    # output/ is now at workspace root, visible (not hidden in .forge/)
    assert (target / "output" / "CLAUDE.md").exists()

    compiled = (target / "output" / "CLAUDE.md").read_text("utf-8")
    assert "About me" in compiled

    # CHANGELOG.md is also at workspace root, git-trackable
    assert (target / "CHANGELOG.md").exists()
