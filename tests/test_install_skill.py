"""Test for `forge install-skill`."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def test_install_skill_copies_to_target(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "forge"
    runner = CliRunner()
    result = runner.invoke(main, ["install-skill", "--target", str(target)])
    assert result.exit_code == 0, result.output
    assert (target / "SKILL.md").exists()
    body = (target / "SKILL.md").read_text("utf-8")
    assert "forge" in body and "review" in body.lower()


def test_install_skill_refuses_when_exists_without_force(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "forge"
    runner = CliRunner()
    runner.invoke(main, ["install-skill", "--target", str(target)])

    result = runner.invoke(main, ["install-skill", "--target", str(target)])
    assert result.exit_code == 1
    assert "already exists" in result.output


def test_install_skill_force_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "forge"
    runner = CliRunner()
    runner.invoke(main, ["install-skill", "--target", str(target)])
    # Mutate the installed file to prove --force re-copies fresh source
    (target / "SKILL.md").write_text("stale", encoding="utf-8")

    result = runner.invoke(main, ["install-skill", "--target", str(target), "--force"])
    assert result.exit_code == 0, result.output
    body = (target / "SKILL.md").read_text("utf-8")
    assert body != "stale"
    assert "forge" in body


def test_install_skill_symlink(tmp_path: Path) -> None:
    target = tmp_path / "skills" / "forge"
    runner = CliRunner()
    result = runner.invoke(main, ["install-skill", "--target", str(target), "--symlink"])
    assert result.exit_code == 0, result.output
    assert target.is_symlink()
    assert (target / "SKILL.md").exists()
