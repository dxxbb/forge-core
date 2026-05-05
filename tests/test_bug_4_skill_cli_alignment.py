"""Regression test for Bug 4: SKILL.md commands must match CLI reality.

The forge skill (`forge/assets/skills/forge/SKILL.md`) tells the agent to use
`forge capture --from <file>` and `forge capture --from-claude-memory` for
import. The CLI must (a) actually accept those flags and (b) the
`forge ingest --detect` output must recommend the same commands so an agent
following detect's tail will run skill-aligned commands.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def _read_skill_md() -> str:
    skill_path = (
        Path(__file__).resolve().parent.parent
        / "forge"
        / "assets"
        / "skills"
        / "forge"
        / "SKILL.md"
    )
    return skill_path.read_text("utf-8")


def test_skill_uses_forge_capture_for_import() -> None:
    """The skill must point at `forge capture` for the import flow."""
    skill = _read_skill_md()
    assert "forge capture --root <path> --from <file>" in skill
    assert "forge capture --root <path> --from-claude-memory" in skill


def test_cli_capture_help_supports_skill_flags() -> None:
    """The `forge capture` CLI accepts every flag the skill advertises."""
    runner = CliRunner()
    result = runner.invoke(main, ["capture", "--help"])
    assert result.exit_code == 0
    for flag in ("--from", "--from-stdin", "--from-claude-memory", "--claude-project", "--root"):
        assert flag in result.output, f"capture --help missing {flag}"


def test_detect_recommendation_matches_skill_capture_command() -> None:
    """Bug 4 + Bug 1: detect's tail commands must match the skill's capture flow."""
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    # Whatever detect tells the agent to run next, it should be a `forge capture` form.
    assert "forge capture --from" in result.output
