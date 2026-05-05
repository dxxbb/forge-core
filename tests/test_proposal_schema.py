"""Tests for forge/proposal/schema.py: dataclasses + YAML round-trip."""

from __future__ import annotations

import yaml

from forge.proposal.schema import (
    DecideOption,
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
    dump_proposal,
    has_schema,
    load_proposal,
)


def test_disposition_parse_and_icons():
    # round-trip + alias
    assert Disposition.parse("APPLY") is Disposition.APPLY
    assert Disposition.parse("apply") is Disposition.APPLY
    assert Disposition.parse("ARCHIVE-ONLY") is Disposition.ARCHIVE
    assert Disposition.parse("N/A") is Disposition.NA
    # icons present
    assert Disposition.APPLY.icon == "✅"
    assert Disposition.MIXED.icon  # whatever it is, must be non-empty


def test_disposition_parse_rejects_unknown():
    import pytest

    with pytest.raises(ValueError):
        Disposition.parse("MAYBE")


def test_load_minimal_frontmatter_no_items():
    text = "---\nkind: pr\ntype: context-import\nstatus: pending\n---\n\nbody\n"
    p = load_proposal(text)
    assert p.kind == "pr"
    assert p.type == "context-import"
    assert p.status == "pending"
    assert p.items == []
    assert p.body.strip() == "body"
    assert has_schema(p) is False


def test_load_full_schema_round_trip():
    p = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-05T18:33:00+08:00",
        revised_at="2026-05-05T19:05:00+08:00",
        inbox_sources=["system/inbox/a.md", "system/inbox/b.md"],
        capture_sources=["capture/import/.../foo.md"],
        items=[
            Item(
                id="1",
                monitor_info="~/.claude/CLAUDE.md (new)",
                extracted="capture/import/.../claude.md",
                disposition=Disposition.ARCHIVE,
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
                                        path="capture/import/.../claude.md",
                                        terminal=True,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
            Item(
                id="3",
                monitor_info="Claude Code auto-memory · 28 files",
                disposition=Disposition.MIXED,
                disposition_note="capture 整体归档",
                sub_items=[
                    SubItem(
                        id="3.1",
                        extracted="forge / feedback_no_guess_lobster.md",
                        disposition=Disposition.APPLY,
                        rule="§10",
                        rationale="biographical confabulation rule",
                        propagation=[
                            PropagationBranch(
                                branch="a",
                                node=PropagationNode(
                                    path="feedback-log.md",
                                    layer="Layer 1 · asset",
                                    modification="末尾追加 §10",
                                ),
                            ),
                        ],
                    ),
                    SubItem(
                        id="3.5",
                        extracted="watermark / project_watermark.md",
                        disposition=Disposition.DECIDE,
                        rationale="external repo activity",
                        options=[
                            DecideOption(
                                id="A",
                                description="最小改动",
                                propagation=[
                                    PropagationBranch(
                                        branch="a",
                                        node=PropagationNode(
                                            path="workspace.md",
                                            modification="1 行替换",
                                        ),
                                    ),
                                ],
                            ),
                            DecideOption(id="C", description="不动", propagation=[]),
                        ],
                        recommendation="A",
                    ),
                    SubItem(
                        id="3.6",
                        extracted="feedback_default_chinese",
                        disposition=Disposition.COVERED,
                        covered_by="MEMORY.md auto-memory",
                    ),
                    SubItem(
                        id="3.24",
                        extracted="dxy-OS / MEMORY.md",
                        disposition=Disposition.NA,
                        reason="auto-memory 索引",
                    ),
                ],
            ),
        ],
    )
    text = dump_proposal(p)
    p2 = load_proposal(text)
    assert p2.kind == p.kind
    assert len(p2.items) == 2
    assert p2.items[0].disposition is Disposition.ARCHIVE
    assert p2.items[1].disposition is Disposition.MIXED
    sub = p2.items[1].sub_items
    assert [s.id for s in sub] == ["3.1", "3.5", "3.6", "3.24"]
    assert sub[0].rule == "§10"
    assert sub[1].disposition is Disposition.DECIDE
    assert [o.id for o in sub[1].options] == ["A", "C"]
    assert sub[2].covered_by == "MEMORY.md auto-memory"
    assert sub[3].reason == "auto-memory 索引"


def test_load_propagation_shared_with():
    text = (
        "---\n"
        "kind: pr\n"
        "type: context-import\n"
        "status: pending\n"
        "items:\n"
        "  - id: '3'\n"
        "    monitor_info: x\n"
        "    disposition: MIXED\n"
        "    sub_items:\n"
        "      - id: '3.1'\n"
        "        extracted: a\n"
        "        disposition: APPLY\n"
        "        rationale: r\n"
        "        propagation:\n"
        "          - branch: a\n"
        "            node:\n"
        "              path: feedback-log.md\n"
        "              modification: m\n"
        "      - id: '3.2'\n"
        "        extracted: b\n"
        "        disposition: APPLY\n"
        "        rationale: r2\n"
        "        propagation:\n"
        "          - branch: a\n"
        "            shared_with: ['3.1']\n"
        "            node:\n"
        "              path: feedback-log.md\n"
        "              modification: m2\n"
        "---\n"
    )
    p = load_proposal(text)
    sub2 = p.items[0].sub_items[1]
    assert sub2.propagation[0].shared_with == ["3.1"]


def test_dump_preserves_extra_keys():
    text = "---\nkind: pr\ntype: context-import\nstatus: pending\nfoo_bar: 42\n---\n\n"
    p = load_proposal(text)
    assert p.extra.get("foo_bar") == 42
    out = dump_proposal(p)
    assert "foo_bar: 42" in out


def test_load_handles_bad_frontmatter():
    import pytest

    # items not a list
    with pytest.raises(ValueError):
        load_proposal("---\nkind: pr\nitems: not-a-list\n---\n")
