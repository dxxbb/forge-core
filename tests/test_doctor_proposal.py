"""Tests for `forge doctor`'s proposal-schema scan (v0.3)."""

from __future__ import annotations

from pathlib import Path

from forge.gate.doctor import run as doctor_run
from forge.proposal.schema import (
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    dump_proposal,
)


def _seed_personal_os(tmp_path: Path) -> Path:
    """Minimal personalOS layout that doctor can scan."""
    (tmp_path / "context build" / "sections").mkdir(parents=True)
    (tmp_path / "context build" / "config").mkdir(parents=True)
    (tmp_path / "system" / "pr").mkdir(parents=True)
    # one section + one config so doctor doesn't error out
    (tmp_path / "context build" / "sections" / "alpha.md").write_text(
        "---\nname: alpha\ntype: identity\n---\n\nbody\n", encoding="utf-8"
    )
    (tmp_path / "context build" / "config" / "main.md").write_text(
        "---\nname: M\ntarget: claude-code\nsections:\n  - alpha\n---\n",
        encoding="utf-8",
    )
    return tmp_path


def _ok_proposal() -> Proposal:
    return Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-05T18:33:00+08:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.ARCHIVE,
                rationale="r",
                propagation=[PropagationBranch(branch="a", node=PropagationNode(
                    path="a.md", terminal=True))],
            ),
        ],
    )


def test_doctor_reports_schema_complete_proposals(tmp_path):
    root = _seed_personal_os(tmp_path)
    pr_dir = root / "system" / "pr" / "20260505-183300-test"
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(dump_proposal(_ok_proposal()), encoding="utf-8")

    report = doctor_run(root)
    assert report.ok
    assert any("schema=ok" in line for line in report.info)


def test_doctor_reports_schema_issues_as_info(tmp_path):
    root = _seed_personal_os(tmp_path)
    bad = Proposal(items=[Item(id="1", disposition=Disposition.APPLY)])
    pr_dir = root / "system" / "pr" / "20260505-200000-bad"
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(dump_proposal(bad), encoding="utf-8")

    report = doctor_run(root)
    # Schema violations are info-only; doctor remains ok.
    assert report.ok
    assert any("issue(s)" in line for line in report.info)


def test_doctor_marks_legacy_handwritten_proposal_as_opt_out(tmp_path):
    root = _seed_personal_os(tmp_path)
    pr_dir = root / "system" / "pr" / "20260505-183300-legacy"
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(
        "---\nkind: pr\ntype: context-import\nstatus: pending\n---\n\n# hand-written\n",
        encoding="utf-8",
    )

    report = doctor_run(root)
    assert report.ok
    assert any("opt-out" in line for line in report.info)


def test_doctor_warn_on_malformed_frontmatter(tmp_path):
    root = _seed_personal_os(tmp_path)
    pr_dir = root / "system" / "pr" / "20260505-200000-broken"
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(
        "---\nkind: pr\nitems: this-should-be-a-list\n---\n",
        encoding="utf-8",
    )

    report = doctor_run(root)
    assert any("frontmatter parse" in w or "items" in w for w in report.warnings + report.info)


def test_doctor_no_pr_dir_is_quiet(tmp_path):
    root = _seed_personal_os(tmp_path)
    # remove the system/pr dir
    import shutil
    shutil.rmtree(root / "system" / "pr")
    (root / "system").mkdir(exist_ok=True)
    report = doctor_run(root)
    assert report.ok
    # no proposal-related lines
    assert not any("schema=" in line for line in report.info)
