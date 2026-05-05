"""Tests for forge/proposal/validate.py."""

from __future__ import annotations

from forge.proposal.schema import (
    DecideOption,
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
)
from forge.proposal.validate import validate_proposal


def _ok_archive_item(idx: str = "1") -> Item:
    return Item(
        id=idx,
        monitor_info="~/.claude/CLAUDE.md (new)",
        extracted="capture/.../claude.md",
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
                                path="capture/.../claude.md",
                                terminal=True,
                            ),
                        ),
                    ],
                ),
            ),
        ],
    )


def _full_proposal() -> Proposal:
    return Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-05T18:33:00+08:00",
        items=[_ok_archive_item("1")],
    )


def test_validate_ok_when_complete():
    issues = validate_proposal(_full_proposal())
    assert issues == []


def test_validate_no_items_warns():
    issues = validate_proposal(Proposal())
    assert any(i.path == "items" for i in issues)


def test_validate_missing_top_level_fields():
    p = Proposal(items=[_ok_archive_item("1")])
    issues = validate_proposal(p)
    paths = {i.path for i in issues}
    assert "created_at" in paths


def test_validate_apply_requires_propagation_with_modification():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.APPLY,
                rationale="r",
                propagation=[
                    PropagationBranch(
                        branch="a",
                        node=PropagationNode(
                            path="feedback-log.md",
                            children=[
                                PropagationBranch(
                                    branch="b",
                                    node=PropagationNode(path="preference.md"),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ],
    )
    issues = validate_proposal(p)
    msgs = [i.message for i in issues]
    # The non-leaf node has no modification — should be flagged.
    assert any("modification" in m for m in msgs)


def test_validate_covered_requires_covered_by():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.COVERED,
                rationale="dup",
            ),
        ],
    )
    issues = validate_proposal(p)
    assert any(i.path.endswith("covered_by") for i in issues)


def test_validate_na_requires_reason():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.NA,
                rationale="r",
            ),
        ],
    )
    issues = validate_proposal(p)
    assert any(i.path.endswith("reason") for i in issues)


def test_validate_decide_requires_options():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.DECIDE,
                rationale="r",
            ),
        ],
    )
    issues = validate_proposal(p)
    assert any(i.path.endswith("options") for i in issues)


def test_validate_decide_options_need_description_and_id():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted="y",
                disposition=Disposition.DECIDE,
                rationale="r",
                options=[
                    DecideOption(id="", description=""),
                    DecideOption(id="A", description="something"),
                ],
            ),
        ],
    )
    issues = validate_proposal(p)
    paths = {i.path for i in issues}
    assert "items[0].options[0].id" in paths
    assert "items[0].options[0].description" in paths


def test_validate_mixed_requires_sub_items():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(id="3", monitor_info="x", disposition=Disposition.MIXED),
        ],
    )
    issues = validate_proposal(p)
    assert any("sub_items" in i.path for i in issues)


def test_validate_mixed_sub_item_dispositions_validated():
    # MIXED parent OK, but a sub-item is missing rationale
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="3",
                monitor_info="x",
                disposition=Disposition.MIXED,
                sub_items=[
                    SubItem(
                        id="3.1",
                        extracted="forge/.../foo.md",
                        disposition=Disposition.APPLY,
                        # no rationale, no propagation
                    ),
                ],
            ),
        ],
    )
    issues = validate_proposal(p)
    paths = {i.path for i in issues}
    assert "items[0].sub_items[0].rationale" in paths
    assert "items[0].sub_items[0].propagation" in paths


def test_validate_sub_item_cannot_be_mixed():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="3",
                monitor_info="x",
                disposition=Disposition.MIXED,
                sub_items=[
                    SubItem(id="3.1", extracted="x", disposition=Disposition.MIXED),
                ],
            ),
        ],
    )
    issues = validate_proposal(p)
    assert any("MIXED" in i.message for i in issues)


def test_validate_shared_with_must_match_sibling():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[
            Item(
                id="3",
                monitor_info="x",
                disposition=Disposition.MIXED,
                sub_items=[
                    SubItem(
                        id="3.1",
                        extracted="a",
                        disposition=Disposition.APPLY,
                        rationale="r",
                        propagation=[
                            PropagationBranch(
                                branch="a",
                                shared_with=["3.99"],
                                node=PropagationNode(
                                    path="feedback-log.md",
                                    modification="m",
                                ),
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
    issues = validate_proposal(p)
    assert any("shared_with" in i.path for i in issues)


def test_validate_unique_item_ids():
    p = Proposal(
        created_at="2026-01-01T00:00:00+00:00",
        items=[_ok_archive_item("1"), _ok_archive_item("1")],
    )
    issues = validate_proposal(p)
    assert any("duplicate" in i.message for i in issues)
