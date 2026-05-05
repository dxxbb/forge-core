"""Regression test for Bug 1: `forge ingest --detect` recommends legacy ingest.

Old behavior: trailing "to ingest:" block printed `forge ingest --from ...`
recommendations. In the new architecture, `forge ingest` does not work in
personalOS roots (Bug 2). Detect should recommend `forge capture --from ...`
instead — that is the personalOS-layout-first command used by the skill.

Bug 4 (skill alignment) is verified by ensuring detect output uses the same
command name (`forge capture`) the skill's SKILL.md tells the agent to run.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def test_detect_recommends_forge_capture_not_ingest(tmp_path: Path) -> None:
    """Detect's "to ingest:" block must point to `forge capture`, not `forge ingest`."""
    # Make a non-empty file in a place detect scans, just so detect has output.
    # We don't actually rely on a discovered candidate — we test the recommendation
    # block, which prints whether any candidate was found or not.
    runner = CliRunner()
    result = runner.invoke(main, ["ingest", "--detect"])
    assert result.exit_code == 0, result.output

    # Bug 1 / Bug 4: the recommended next-step command must be `forge capture`.
    # Old code recommended `forge ingest --from <path>` — that text must be gone
    # from the recommendation block.
    assert "forge capture --from" in result.output, result.output
    # Make sure we don't recommend the legacy invocation in the action block.
    # (We tolerate `forge ingest` mentions elsewhere in help, but not in the
    #  "to capture:" / "to ingest:" instruction lines.)
    instruction_lines = [
        line
        for line in result.output.splitlines()
        if line.strip().startswith("forge ")
    ]
    legacy_recommendations = [
        line for line in instruction_lines if "ingest --from" in line
    ]
    assert not legacy_recommendations, (
        f"unexpected legacy `forge ingest --from` recommendation: {legacy_recommendations}"
    )
