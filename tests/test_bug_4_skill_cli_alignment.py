"""Regression test for Bug 4: SKILL.md commands must match CLI reality.

The forge skill (`forge/assets/skills/forge/SKILL.md`) tells the agent to use
`forge capture --from <file>`, `forge capture --from-claude-memory`, and
`forge capture --from-codex-memory` for import. The CLI must (a) actually accept
those flags and (b) the
`forge ingest --detect` output must recommend the same commands so an agent
following detect's tail will run skill-aligned commands.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def _skill_dir() -> Path:
    return (
        Path(__file__).resolve().parent.parent
        / "forge"
        / "assets"
        / "skills"
        / "forge"
    )


def _read_skill_md() -> str:
    return (_skill_dir() / "SKILL.md").read_text("utf-8")


def _read_skill_bundle() -> str:
    return "\n".join(
        path.read_text("utf-8")
        for path in sorted(_skill_dir().rglob("*.md"))
    )


def test_skill_uses_forge_capture_for_import() -> None:
    """The skill must point at `forge capture` for the import flow."""
    skill = _read_skill_bundle()
    assert "forge capture --root <path> --from <file>" in skill
    assert "forge capture --root <path> --from-claude-memory" in skill
    assert "forge capture --root <path> --from-codex-memory" in skill


def test_cli_capture_help_supports_skill_flags() -> None:
    """The `forge capture` CLI accepts every flag the skill advertises."""
    runner = CliRunner()
    result = runner.invoke(main, ["capture", "--help"])
    assert result.exit_code == 0
    for flag in (
        "--from",
        "--from-stdin",
        "--from-claude-memory",
        "--from-codex-memory",
        "--claude-project",
        "--root",
    ):
        assert flag in result.output, f"capture --help missing {flag}"


def test_skill_and_cli_align_on_review_unit_disposition() -> None:
    skill = _read_skill_bundle()
    assert "classify-source-items" in skill
    assert "--item <unit-id>" in skill
    assert "Candidate Conclusion" in skill
    assert "--coverage-claim" in skill
    assert "--coverage-locator" in skill
    assert "--coverage-excerpt" in skill
    assert "owner_facing_projection" in skill
    assert "heartbeat_if_required" in skill
    assert "OWNER-FACING SUMMARY" in skill
    assert "原样" in skill

    result = CliRunner().invoke(main, ["run", "disposition", "--help"])
    assert result.exit_code == 0, result.output
    assert "--item" in result.output


def test_run_cli_uses_the_one_candidate_default_budget() -> None:
    runner = CliRunner()

    next_help = runner.invoke(main, ["run", "next", "--help"])
    ask_help = runner.invoke(main, ["run", "ask", "--help"])

    assert next_help.exit_code == ask_help.exit_code == 0
    assert "[default: 1]" in next_help.output
    assert "[default: 1]" in ask_help.output


def test_skill_and_cli_align_on_event_grounded_candidate_review() -> None:
    skill = _read_skill_bundle()
    for term in (
        "event-id",
        "owner-directed",
        "source-context",
        "existing-coverage",
        "asset-fit",
        "owner-correction",
        "promotion-rationale",
        "expected-effect",
        "decision-question",
    ):
        assert term in skill

    runner = CliRunner()
    candidate_help = runner.invoke(main, ["candidate", "create", "--help"])
    assert candidate_help.exit_code == 0, candidate_help.output
    for flag in (
        "--event-id",
        "--source-context",
        "--existing-coverage",
        "--asset-fit",
        "--owner-correction",
        "--promotion-rationale",
        "--expected-effect",
        "--decision-question",
        "--owner-request",
        "--risk-invariant",
        "--risk-failure",
    ):
        assert flag in candidate_help.output
    assert "[repeated|owner-directed]" in candidate_help.output
    assert "repeated|owner-directed|high-risk" not in candidate_help.output

    observation_help = runner.invoke(main, ["observation", "record", "--help"])
    assert observation_help.exit_code == 0, observation_help.output
    for flag in (
        "--signal-type",
        "--source-context",
        "--repeat-if",
        "--route-gap",
        "--event-id",
    ):
        assert flag in observation_help.output


def test_detect_recommendation_matches_skill_capture_command() -> None:
    """Bug 4 + Bug 1: detect's tail commands must match the skill's capture flow."""
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0
    # Whatever detect tells the agent to run next, it should be a `forge capture` form.
    assert "forge capture --from" in result.output


def test_skill_entrypoint_is_run_focused_and_routes_conditional_workflows() -> None:
    skill = _read_skill_md()

    assert len(skill.splitlines()) <= 360
    assert "references/initialize-and-import.md" in skill
    assert "references/legacy-workflows.md" in skill
    assert "## Forge Run" in skill
