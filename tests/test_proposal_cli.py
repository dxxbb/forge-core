"""Tests for `forge proposal validate` and `forge pr render` CLI."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main
from forge.proposal.schema import (
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
    dump_proposal,
)


def _make_pr(workspace: Path, pr_id: str, proposal: Proposal) -> Path:
    pr_dir = workspace / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    (pr_dir / "proposal.md").write_text(dump_proposal(proposal), encoding="utf-8")
    return pr_dir


def _ok_proposal() -> Proposal:
    return Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-05T18:33:00+08:00",
        items=[
            Item(
                id="1",
                monitor_info="~/.claude/CLAUDE.md (8.6K, new)",
                extracted="capture/.../claude.md",
                disposition=Disposition.ARCHIVE,
                disposition_note="ARCHIVE-ONLY",
                rationale="self-loop",
                propagation=[
                    PropagationBranch(
                        branch="a",
                        node=PropagationNode(
                            path="~/.claude/CLAUDE.md",
                            label="监控源",
                            children=[
                                PropagationBranch(
                                    branch="a1",
                                    node=PropagationNode(
                                        path="capture/.../claude.md",
                                        terminal=True,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ],
    )


def test_validate_cli_passes_for_ok_proposal(tmp_path):
    _make_pr(tmp_path, "20260505-183300-test", _ok_proposal())
    r = CliRunner().invoke(main, [
        "proposal", "validate", "20260505-183300-test", "--root", str(tmp_path),
    ])
    assert r.exit_code == 0
    assert "OK" in r.output
    assert "schema is complete" in r.output


def test_validate_cli_fails_for_missing_fields(tmp_path):
    p = Proposal(items=[Item(id="1", disposition=Disposition.APPLY)])
    _make_pr(tmp_path, "20260505-200000-broken", p)
    r = CliRunner().invoke(main, [
        "proposal", "validate", "20260505-200000-broken", "--root", str(tmp_path),
    ])
    assert r.exit_code != 0
    assert "FAIL" in r.output
    assert "issue(s)" in r.output


def test_validate_cli_handles_legacy_handwritten_proposal(tmp_path):
    legacy = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        items=[],
        body="\n# my hand-written proposal body, no schema\n",
    )
    _make_pr(tmp_path, "20260505-200000-legacy", legacy)
    r = CliRunner().invoke(main, [
        "proposal", "validate", "20260505-200000-legacy", "--root", str(tmp_path),
    ])
    # legacy → 1 issue (`schema not opted in`), exit non-zero
    assert r.exit_code != 0
    assert "items" in r.output


def test_render_cli_outputs_view(tmp_path):
    _make_pr(tmp_path, "20260505-183300-test", _ok_proposal())
    r = CliRunner().invoke(main, [
        "pr", "render", "20260505-183300-test", "--root", str(tmp_path),
    ])
    assert r.exit_code == 0
    assert "ITEM 1" in r.output
    assert "📦" in r.output


def test_render_cli_plain_mode(tmp_path):
    _make_pr(tmp_path, "20260505-183300-test", _ok_proposal())
    r = CliRunner().invoke(main, [
        "pr", "render", "20260505-183300-test", "--root", str(tmp_path), "--plain",
    ])
    assert r.exit_code == 0
    for ch in ["═", "─", "└"]:
        assert ch not in r.output


def test_render_cli_rejects_legacy_handwritten_proposal(tmp_path):
    legacy = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        items=[],
        body="# legacy\nbody only\n",
    )
    _make_pr(tmp_path, "20260505-200000-legacy", legacy)
    r = CliRunner().invoke(main, [
        "pr", "render", "20260505-200000-legacy", "--root", str(tmp_path),
    ])
    assert r.exit_code != 0
    assert "no v0.3 schema" in r.output


def test_render_cli_unknown_pr(tmp_path):
    (tmp_path / "system" / "pr").mkdir(parents=True)
    r = CliRunner().invoke(main, [
        "pr", "render", "does-not-exist", "--root", str(tmp_path),
    ])
    assert r.exit_code != 0
