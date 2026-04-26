"""Test the new forge diff rendering: summary, color, provenance folding, --config filter."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main, _format_diff, _summarize_diff, _fold_provenance_block
from forge.gate import actions as gate


def _ws_with_change(tmp_path: Path) -> Path:
    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])
    runner.invoke(main, ["init", "--root", str(ws)])
    section = ws / "sp" / "section" / "preferences.md"
    section.write_text(
        "---\nname: preferences\ntype: preferences\n---\n\n- 不要加 emoji\n",
        encoding="utf-8",
    )
    return ws


def test_summary_names_changed_section(tmp_path: Path) -> None:
    ws = _ws_with_change(tmp_path)
    result = gate.diff_summary(ws)

    summary = _summarize_diff(result)
    assert "1 section changed" in summary
    assert "preferences.md" in summary
    assert "agents-md" in summary
    assert "claude-code" in summary


def test_provenance_folding_collapses_digest_hunk() -> None:
    """A hunk where every -/+ line is a provenance digest/byte should collapse."""
    sample = [
        "@@ -2,10 +2,10 @@",
        " ",
        " > Compiled by forge-core",
        " ",
        "-forge-core provenance · digest=aaaa",
        "+forge-core provenance · digest=bbbb",
        "->  - foo · type=foo · 100B",
        "+>  - foo · type=foo · 200B",
        " more context",
        "@@ -39,5 +39,5 @@",
        "-real content removed",
        "+real content added",
    ]
    folded = _fold_provenance_block(sample)
    folded_text = "\n".join(folded)
    assert "provenance lines folded" in folded_text
    assert "digest=aaaa" not in folded_text  # really collapsed
    assert "real content added" in folded_text  # non-provenance hunk preserved


def test_full_provenance_flag_keeps_digest_lines(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws_with_change(tmp_path)

    folded_result = runner.invoke(
        main, ["diff", "--root", str(ws), "--no-pager", "--no-color"]
    )
    full_result = runner.invoke(
        main, ["diff", "--root", str(ws), "--no-pager", "--no-color", "--full-provenance"]
    )
    assert folded_result.exit_code == 0
    assert full_result.exit_code == 0

    assert "provenance lines folded" in folded_result.output
    assert "digest=" not in folded_result.output  # default: digest hidden

    assert "digest=" in full_result.output  # explicit: digest shown
    assert "provenance lines folded" not in full_result.output


def test_config_filter_only_shows_one_config(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws_with_change(tmp_path)

    res = runner.invoke(
        main,
        ["diff", "--root", str(ws), "--no-pager", "--no-color", "--config", "claude-code"],
    )
    assert res.exit_code == 0
    assert "▸ claude-code" in res.output
    assert "▸ agents-md" not in res.output


def test_config_filter_unknown_says_no_changes(tmp_path: Path) -> None:
    runner = CliRunner()
    ws = _ws_with_change(tmp_path)

    res = runner.invoke(
        main,
        ["diff", "--root", str(ws), "--no-pager", "--no-color", "--config", "made-up"],
    )
    assert res.exit_code == 0
    assert "no output changes for config `made-up`" in res.output


def test_summary_lists_section_when_only_one(tmp_path: Path) -> None:
    """Edge: changed=True but source-only edits → summary should still report sections."""
    ws = _ws_with_change(tmp_path)
    result = gate.diff_summary(ws)
    summary = _summarize_diff(result)
    # exactly "section" not "sections" for n=1
    assert "1 section changed" in summary
    assert "1 sections" not in summary
