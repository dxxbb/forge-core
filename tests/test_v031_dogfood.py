"""End-to-end regression tests for v0.3.1 dogfood fixes.

Covers the 13 problems exposed by v0.3.0 dogfood:

  P1   pr render writes inline into proposal.md body (BEGIN/END markers)
  P2   stub `disposition:` carries the enum hint, not `disposition_note:`
  P3   stub propagation has `layer` + `modification` placeholders
  P4   ARCHIVE allows empty propagation
  P6   MIXED parent's own ARCHIVE-trail is documented (not double-counted)
  P7/P8 shared_with rendering: first owner expands, others abbreviate
  P9   处理结果 line always shows ENUM_NAME + optional disposition_note
  P10  multi-line `extracted` renders as ├─/└─ tree
  P11  pure-stub fill-in flow: sed-replaces validate clean and render OK

Skill / changelog / self-install side-effects are covered by other tests.
"""

from __future__ import annotations

import re
from pathlib import Path

from click.testing import CliRunner

from forge.cli import main
from forge.proposal.renderer import render, render_inline
from forge.proposal.scaffold import (
    DISPOSITION_PLACEHOLDER,
    RENDER_BEGIN,
    RENDER_END,
    scaffold_proposal,
)
from forge.proposal.schema import (
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
    load_proposal_file,
)


# ---------------- helpers


def _seed_personal_os(tmp_path: Path, n_inbox: int = 1) -> Path:
    """Minimal personalOS layout (mirrors test_proposal_new._seed_personal_os)."""
    (tmp_path / "system" / "inbox").mkdir(parents=True)
    (tmp_path / "system" / "pr").mkdir(parents=True)
    (tmp_path / "capture" / "import").mkdir(parents=True)
    for i in range(n_inbox):
        ts = f"20260505-18305{i}"
        batch = tmp_path / "capture" / "import" / ts
        batch.mkdir(parents=True)
        (batch / "src.md").write_text(
            "---\n"
            "kind: raw import\n"
            f"source: \"/some/file{i}.md\"\n"
            "captured_at: 2026-05-05T18:30:51+08:00\n"
            "source_size: 1234\n"
            "source_digest: deadbeef00112233\n"
            "status: unreviewed\n"
            "---\n\n"
            f"file{i} body\n",
            encoding="utf-8",
        )
        (tmp_path / "system" / "inbox" / f"{ts}-source-{i}.md").write_text(
            "---\n"
            "kind: inbox\n"
            "type: import-context\n"
            "status: pending\n"
            "source:\n"
            f"  - capture/import/{ts}/\n"
            "---\n\n"
            "# Import context\n\n"
            "## Source summary\n\n"
            f"- /some/file{i}.md (1234 chars)\n\n",
            encoding="utf-8",
        )
    return tmp_path


# ---------------- P1 / P2 / P3: scaffold output shape


def test_p1_stub_body_carries_render_markers(tmp_path):
    root = _seed_personal_os(tmp_path)
    out = scaffold_proposal(root, list((root / "system" / "inbox").glob("*.md")),
                              title="dog")
    body = out.read_text(encoding="utf-8")
    assert RENDER_BEGIN in body
    assert RENDER_END in body
    # markers must appear in body order, not frontmatter
    fm_end = body.index("\n---\n", 4)
    assert body.index(RENDER_BEGIN) > fm_end


def test_p2_stub_uses_disposition_enum_hint_in_correct_field(tmp_path):
    root = _seed_personal_os(tmp_path)
    out = scaffold_proposal(root, list((root / "system" / "inbox").glob("*.md")),
                              title="dog")
    text = out.read_text(encoding="utf-8")
    # Enum hint sits in `disposition:` field, NOT in `disposition_note:`
    assert f"disposition: '{DISPOSITION_PLACEHOLDER}'" in text
    # disposition_note left empty / absent (the previous bug)
    assert "disposition_note: <APPLY|" not in text
    assert "disposition_note: '<APPLY|" not in text


def test_p3_stub_propagation_has_layer_and_modification(tmp_path):
    root = _seed_personal_os(tmp_path)
    out = scaffold_proposal(root, list((root / "system" / "inbox").glob("*.md")),
                              title="dog")
    text = out.read_text(encoding="utf-8")
    assert "layer: " in text
    assert "modification: " in text


# ---------------- P4: ARCHIVE allows empty propagation


def test_p4_archive_with_empty_propagation_validates_clean():
    from forge.proposal.validate import validate_proposal
    p = Proposal(
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
                rationale="capture-only audit trail",
                propagation=[],   # empty — must be allowed for ARCHIVE
            ),
        ],
    )
    issues = validate_proposal(p)
    assert not any("propagation" in i.path for i in issues), \
        f"unexpected propagation issue(s): {[i.path for i in issues]}"


# ---------------- P9: disposition_note rendered in 处理结果 + title


def test_p9_disposition_title_includes_enum_and_note():
    item = Item(
        id="1",
        monitor_info="x",
        extracted="y",
        disposition=Disposition.ARCHIVE,
        disposition_note="仅归档用做审计 trail, 本 PR 不闭环",
        rationale="r",
        propagation=[],
    )
    out = render(Proposal(items=[item]))
    # ENUM_NAME always shows
    assert "ARCHIVE-ONLY" in out
    # disposition_note shows alongside (different from ENUM_NAME)
    assert "仅归档用做审计 trail" in out


def test_p9_decide_title_shows_disposition_note():
    """DECIDE node carries `disposition_note` like 待用户拍板; renderer shows it."""
    from forge.proposal.schema import DecideOption
    item = Item(
        id="1",
        monitor_info="x",
        extracted="y",
        disposition=Disposition.DECIDE,
        disposition_note="待用户拍板, 本 PR 不闭环",
        rationale="r",
        options=[
            DecideOption(id="A", description="a"),
            DecideOption(id="B", description="b"),
        ],
        recommendation="A",
    )
    out = render(Proposal(items=[item]))
    assert "DECIDE" in out
    assert "待用户拍板" in out


# ---------------- P10: extracted multi-line tree prefix


def test_p10_extracted_multiline_uses_tree_prefix():
    item = Item(
        id="1",
        monitor_info="x",
        extracted="capture/import/foo.md\n  - source: bar\n  - captured_at: 2026-05-05\n  - source_size: 1234",
        disposition=Disposition.ARCHIVE,
        rationale="r",
        propagation=[],
    )
    out = render(Proposal(items=[item]))
    # last continuation line should be `└─`, others `├─`
    assert "├─" in out
    assert "└─" in out
    # the last continuation line's content must be the last line of `extracted`
    # (loosely: the └─ appears before the source_size line)
    idx_last = out.index("source_size")
    snippet = out[max(0, idx_last - 30):idx_last]
    assert "└─" in snippet


# ---------------- P7 / P8: shared_with rendering


def _shared_branch_chain(rule_no: str, mod: str) -> list[PropagationBranch]:
    """a → feedback-log; b shared by [3.1, 3.2, 3.3, 3.4]; c terminal."""
    return [
        PropagationBranch(
            branch="a",
            node=PropagationNode(
                path="feedback-log.md",
                layer="Layer 1 · asset",
                modification=mod,
                children=[
                    PropagationBranch(
                        branch="b",
                        shared_with=["3.1", "3.2", "3.3", "3.4"],
                        node=PropagationNode(
                            path="preference.md",
                            layer="Layer 2 · section",
                            modification="末尾加 ## Feedback Log",
                            children=[
                                PropagationBranch(
                                    branch="c",
                                    node=PropagationNode(
                                        path="CLAUDE.md / AGENTS.md",
                                        layer="Layer 3 · runtime",
                                        modification="auto-gen",
                                        terminal=True,
                                    ),
                                ),
                            ],
                        ),
                    ),
                ],
            ),
        ),
    ]


def test_p7_shared_with_first_owner_lists_siblings():
    parent = Item(
        id="3",
        monitor_info="x",
        disposition=Disposition.MIXED,
        sub_items=[
            SubItem(id="3.1", extracted="a", disposition=Disposition.APPLY,
                    rationale="r", propagation=_shared_branch_chain("§10", "末尾追加 §10")),
            SubItem(id="3.2", extracted="b", disposition=Disposition.APPLY,
                    rationale="r", propagation=_shared_branch_chain("§11", "末尾追加 §11")),
        ],
    )
    out = render(Proposal(items=[parent]))
    # First owner (3.1) renders the b branch in full and lists siblings
    assert "(共享触发的子链路, 见" in out
    # Sibling list should reference at least sub 3.2 (and not include self 3.1)
    assert re.search(r"共享触发的子链路.*sub 3\.2", out)


def test_p8_shared_with_subsequent_owners_abbreviate():
    parent = Item(
        id="3",
        monitor_info="x",
        disposition=Disposition.MIXED,
        sub_items=[
            SubItem(id="3.1", extracted="a", disposition=Disposition.APPLY,
                    rationale="r", propagation=_shared_branch_chain("§10", "末尾追加 §10")),
            SubItem(id="3.2", extracted="b", disposition=Disposition.APPLY,
                    rationale="r", propagation=_shared_branch_chain("§11", "末尾追加 §11")),
            SubItem(id="3.3", extracted="c", disposition=Disposition.APPLY,
                    rationale="r", propagation=_shared_branch_chain("§12", "末尾追加 §12")),
        ],
    )
    out = render(Proposal(items=[parent]))
    # Subsequent owners (3.2, 3.3) collapse the shared branch to "同 sub 3.1 共享传播"
    assert "(同 sub 3.1 共享传播)" in out

    # Only the canonical owner (3.1) expands the b → c chain in the per-sub-item
    # section. Slice the output to just that section (everything before the
    # merged-propagation block); the shared mod should appear exactly once.
    head = out.split("全 PR 改动汇总", 1)[0]
    occurrences = head.count("末尾加 ## Feedback Log")
    assert occurrences == 1, (
        f"per-sub-item shared mod text should appear once (canonical owner only), "
        f"got {occurrences}"
    )

    # subsequent-owner abbreviation appears for both 3.2 and 3.3
    head_lines = head.splitlines()
    abbrev_count = sum(1 for l in head_lines if "(同 sub 3.1 共享传播)" in l)
    assert abbrev_count >= 2, (
        f"expected ≥2 abbreviation lines (sub 3.2 + sub 3.3), got {abbrev_count}"
    )


# ---------------- P1: render_inline mechanics


def test_p1_render_inline_writes_between_markers(tmp_path):
    root = _seed_personal_os(tmp_path)
    out = scaffold_proposal(root, list((root / "system" / "inbox").glob("*.md")),
                              title="dog")
    # fill in the stub by hand for one item (single inbox)
    # (we do this via Python edit because sed quoting is fragile in tests)
    text = out.read_text(encoding="utf-8")
    text = text.replace(f"'{DISPOSITION_PLACEHOLDER}'", "ARCHIVE")
    text = text.replace("<TODO: explain why this disposition>", "self-loop")
    text = text.replace("<TODO: 改动内容>", "记录入档作 trail")
    out.write_text(text, encoding="utf-8")

    rendered, wrote = render_inline(out)
    assert wrote
    body = out.read_text(encoding="utf-8")
    assert RENDER_BEGIN in body
    assert RENDER_END in body
    assert "ITEM 1" in body
    assert "📦" in body  # ARCHIVE icon
    # idempotent: second call should be a no-op write (content unchanged)
    _, wrote2 = render_inline(out)
    assert wrote2 is False


def test_p1_render_inline_preserves_non_managed_body(tmp_path):
    """User-authored content outside BEGIN/END markers must be preserved."""
    root = _seed_personal_os(tmp_path)
    out = scaffold_proposal(root, list((root / "system" / "inbox").glob("*.md")),
                              title="dog")
    text = out.read_text(encoding="utf-8")
    text = text.replace(f"'{DISPOSITION_PLACEHOLDER}'", "ARCHIVE")
    text = text.replace("<TODO: explain why this disposition>", "self-loop")
    text = text.replace("<TODO: 改动内容>", "trail")

    # add a user note BEFORE and AFTER the BEGIN/END block
    text = text.replace(
        RENDER_BEGIN,
        "## 用户手写笔记 (前)\n\nthis is mine, must survive\n\n" + RENDER_BEGIN,
    )
    text = text.replace(
        RENDER_END,
        RENDER_END + "\n\n## 用户手写笔记 (后)\n\nalso mine, must survive\n",
    )
    out.write_text(text, encoding="utf-8")

    render_inline(out)
    body = out.read_text(encoding="utf-8")
    assert "用户手写笔记 (前)" in body
    assert "用户手写笔记 (后)" in body
    assert "this is mine, must survive" in body
    assert "also mine, must survive" in body
    assert "ITEM 1" in body  # rendered into the block


# ---------------- P11: full e2e — scaffold + sed-fill + validate clean


def test_p11_pure_stub_fill_validates_clean(tmp_path):
    """A naive agent that *only* edits scaffold-provided placeholders
    (not the schema itself) should produce a validate-clean proposal."""
    root = _seed_personal_os(tmp_path, n_inbox=1)
    runner = CliRunner()

    # 1) scaffold
    r = runner.invoke(main, ["proposal", "new", "--root", str(root)])
    assert r.exit_code == 0, r.output
    pr_dirs = list((root / "system" / "pr").iterdir())
    assert len(pr_dirs) == 1
    proposal_path = pr_dirs[0] / "proposal.md"
    pr_id = pr_dirs[0].name

    # 2) sed-style fill (only the placeholders that the stub ships with).
    #    No schema modification — same as a fresh agent reading the stub.
    text = proposal_path.read_text(encoding="utf-8")
    text = text.replace(f"'{DISPOSITION_PLACEHOLDER}'", "ARCHIVE")
    text = text.replace("<TODO: explain why this disposition>",
                        "capture-only audit trail")
    text = text.replace("<TODO: 改动内容>", "归档监控文件副本")
    proposal_path.write_text(text, encoding="utf-8")

    # 3) validate (schema must be clean — *and* auto-render fires)
    r = runner.invoke(main, ["proposal", "validate", pr_id, "--root", str(root)])
    assert r.exit_code == 0, r.output
    assert "OK" in r.output
    assert "schema is complete" in r.output
    assert "auto-rendered" in r.output

    # 4) the BEGIN/END block now contains the §0.5 view
    body = proposal_path.read_text(encoding="utf-8")
    assert "ITEM 1" in body
    assert "📦" in body  # ARCHIVE
    assert "ARCHIVE-ONLY" in body  # ENUM_NAME shows in title


# ---------------- validate auto-render flag


def test_validate_no_render_flag_skips_auto_render(tmp_path):
    """`--no-render` must not modify the proposal body even when schema is OK."""
    root = _seed_personal_os(tmp_path, n_inbox=1)
    runner = CliRunner()
    runner.invoke(main, ["proposal", "new", "--root", str(root)])
    proposal_path = next((root / "system" / "pr").iterdir()) / "proposal.md"
    pr_id = proposal_path.parent.name

    text = proposal_path.read_text(encoding="utf-8")
    text = text.replace(f"'{DISPOSITION_PLACEHOLDER}'", "ARCHIVE")
    text = text.replace("<TODO: explain why this disposition>", "trail")
    text = text.replace("<TODO: 改动内容>", "trail")
    proposal_path.write_text(text, encoding="utf-8")

    before = proposal_path.read_text(encoding="utf-8")
    r = runner.invoke(main, ["proposal", "validate", pr_id, "--root", str(root),
                              "--no-render"])
    assert r.exit_code == 0
    assert "auto-rendered" not in r.output
    after = proposal_path.read_text(encoding="utf-8")
    # block contents unchanged (auto-render skipped)
    assert before == after


# ---------------- P6: MIXED parent capture trail — counted only via sub_items


def test_p6_mixed_parent_capture_not_double_counted():
    """The MIXED parent's own ARCHIVE-trail is a *parent-level* archive marker,
    and the disposition distribution only counts each sub-item exactly once
    (the parent itself is not added). This is the documented contract."""
    parent = Item(
        id="3",
        monitor_info="x",
        disposition=Disposition.MIXED,
        disposition_note="capture 整体 📦 归档作 trail",
        sub_items=[
            SubItem(id="3.1", extracted="a", disposition=Disposition.APPLY,
                    rationale="r",
                    propagation=[PropagationBranch(branch="a",
                        node=PropagationNode(path="x.md", modification="m"))]),
            SubItem(id="3.2", extracted="b", disposition=Disposition.ARCHIVE,
                    rationale="trail", propagation=[]),
        ],
    )
    out = render(Proposal(items=[parent]))
    # APPLY × 1 (only sub 3.1) + ARCHIVE × 1 (only sub 3.2) — parent not counted
    assert "✅ × 1" in out
    assert "📦 × 1" in out
    # MIXED parent itself is NOT counted as ARCHIVE — explicit guard
    assert "📦 × 2" not in out


# ---------------- skill version sync sanity (P5/P13)


def test_skill_md_carries_v031_version():
    """The packaged SKILL.md should advertise the current forge version so the
    agent picks up the right operating manual after `forge self-install`."""
    from forge import __version__
    assert __version__ == "0.3.1"
    # The packaged asset's frontmatter version should match.
    src = Path(__file__).resolve().parent.parent / "forge" / "assets" / "skills" / "forge" / "SKILL.md"
    text = src.read_text(encoding="utf-8")
    m = re.search(r"^version:\s*(\S+)", text, re.MULTILINE)
    assert m, "SKILL.md missing `version:` frontmatter key"
    assert m.group(1) == "0.3.1", \
        f"SKILL.md version is {m.group(1)}, expected 0.3.1"
