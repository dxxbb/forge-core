"""Tests for forge/proposal/renderer.py.

These tests cover unit-level expectations: icons appear, tree shape is
preserved, ASCII fallback, decide/covered/n-a rendering. The full §0.5
form-equivalence test against the hand-authored proposal is in
`test_proposal_render_v05_equivalence.py`.
"""

from __future__ import annotations

from forge.proposal.renderer import render
from forge.proposal.schema import (
    DecideOption,
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
)


def _archive_item() -> Item:
    return Item(
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
    )


def test_render_top_level_archive():
    p = Proposal(items=[_archive_item()])
    out = render(p)
    assert "ITEM 1" in out
    assert "📦" in out
    assert "ARCHIVE-ONLY" in out
    assert "└─ a:" in out
    assert "└─ a1:" in out
    assert "(终止)" in out
    assert "总分布" in out


def test_render_plain_uses_ascii():
    p = Proposal(items=[_archive_item()])
    out = render(p, plain=True)
    # No box-drawing chars allowed in plain mode
    for ch in ["═", "─", "└", "├", "│"]:
        assert ch not in out
    assert "==" in out  # h_double in plain mode
    assert "ITEM 1" in out


def test_render_distribution_counts_sub_items():
    item = Item(
        id="3",
        monitor_info="claude memory",
        disposition=Disposition.MIXED,
        sub_items=[
            SubItem(id="3.1", extracted="a", disposition=Disposition.APPLY,
                    rationale="r",
                    propagation=[PropagationBranch(branch="a",
                        node=PropagationNode(path="feedback-log.md",
                                              modification="m"))]),
            SubItem(id="3.2", extracted="b", disposition=Disposition.APPLY,
                    rationale="r2",
                    propagation=[PropagationBranch(branch="a",
                        node=PropagationNode(path="feedback-log.md",
                                              modification="m2"))]),
            SubItem(id="3.6", extracted="memo file", disposition=Disposition.COVERED,
                    covered_by="feedback-log §1"),
            SubItem(id="3.24", extracted="MEMORY.md", disposition=Disposition.NA,
                    reason="index"),
        ],
    )
    out = render(Proposal(items=[item]))
    # Distribution should reflect sub-items, not the MIXED parent
    assert "✅ × 2" in out
    assert "⏭ × 1" in out
    assert "➖ × 1" in out


def test_render_decide_emits_options():
    item = Item(
        id="5",
        monitor_info="watermark",
        extracted="project_watermark.md",
        disposition=Disposition.DECIDE,
        rationale="external repo activity",
        options=[
            DecideOption(
                id="A",
                description="最小改动",
                propagation=[PropagationBranch(branch="a",
                    node=PropagationNode(path="workspace.md",
                                          modification="1 行替换"))],
            ),
            DecideOption(id="C", description="不动", propagation=[]),
        ],
        recommendation="A",
    )
    out = render(Proposal(items=[item]))
    assert "选项 A" in out
    assert "选项 C" in out
    assert "推荐    A" in out
    assert "(无传播)" in out


def test_render_covered_table_for_mixed_tail():
    parent = Item(
        id="3",
        monitor_info="memory",
        disposition=Disposition.MIXED,
        sub_items=[
            SubItem(id="3.6", extracted="feedback_default_chinese (personalOS)",
                    disposition=Disposition.COVERED,
                    covered_by="MEMORY.md auto-memory"),
            SubItem(id="3.7", extracted="feedback_ground_external_facts",
                    disposition=Disposition.COVERED,
                    covered_by="feedback-log §2"),
        ],
    )
    out = render(Proposal(items=[parent]))
    assert "COVERED (压缩列表)" in out
    assert "3.6" in out and "MEMORY.md auto-memory" in out
    assert "3.7" in out and "feedback-log §2" in out


def test_render_includes_approve_pipeline_and_summary():
    out = render(Proposal(items=[_archive_item()]))
    assert "Approve 后流水线" in out
    assert "forge build" in out
    assert "forge approve" in out
    assert "forge pr done" in out
    assert "一句话总结" in out
