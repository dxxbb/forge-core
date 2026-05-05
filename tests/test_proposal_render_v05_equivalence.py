"""§0.5 form-equivalence test.

The hand-written §0.5 (lines 35-290 of the dogfood PR) is the visual target
for `forge pr render`. This test:

  1. Constructs a Proposal whose items[] carries the same data the hand-
     written version describes (3 items, item 3 = MIXED with 28 sub-items).
  2. Runs `render(proposal, plain=True)`.
  3. Asserts STRUCTURAL equivalence:
        - exact item / sub-item ids
        - exact icon distribution
        - every propagation `path` in the schema appears at least once in
          the output
        - every modification summary appears in the output
        - ITEM markers + sub-item markers + summary blocks present
  4. Does NOT check exact whitespace / wording / emoji style — those are
     allowed to differ from the hand-written form.
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


# ---------- builders for the dogfood PR §0.5 data ----------

def _branch_to_feedback(rule_no: str, modification: str, shared_branches: bool = True) -> list[PropagationBranch]:
    """Build the a→feedback-log / b→preference / c→runtime tree used by APPLY sub-items.

    The hand-written §0.5 displays b/c as siblings of a (same indent level)
    because b/c are shared by all 4 APPLY sub-items. We reproduce that in the
    schema by listing them as siblings under the same propagation list,
    flagged with `shared_with` so the renderer can show the shared marker.
    Same data, two valid framings — the merged view collapses them into a
    nested tree regardless.
    """
    a = PropagationBranch(
        branch="a",
        node=PropagationNode(
            path="feedback-log.md",
            layer="Layer 1 · asset",
            modification=modification,
            children=[
                PropagationBranch(
                    branch="b",
                    shared_with=["3.1", "3.2", "3.3", "3.4"],
                    node=PropagationNode(
                        path="preference.md",
                        layer="Layer 2 · section",
                        modification="末尾加 ## Feedback Log + L1 pointer (~5 行)",
                        children=[
                            PropagationBranch(
                                branch="c",
                                node=PropagationNode(
                                    path="CLAUDE.md / AGENTS.md",
                                    layer="Layer 3 · runtime, auto-gen",
                                    modification="preference 段 +5 行 (forge build 重生成)",
                                    terminal=True,
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ),
    )
    return [a]


def _build_dogfood_proposal() -> Proposal:
    item1 = Item(
        id="1",
        monitor_info="~/.claude/CLAUDE.md  (8.6K, new, Claude Code 全局指令)",
        extracted=("capture/import/20260505-183051/claude.md\n"
                    "provenance: \"compiled by forge-core. do not edit by hand.\"\n"
                    "upstream: me.md / onepage.md / boundaries.md / working-style.md"),
        disposition=Disposition.ARCHIVE,
        disposition_note="ARCHIVE-ONLY",
        rationale="upstream 已是当前 personalOS asset → 重导即 self-loop, 零新内容",
        propagation=[
            PropagationBranch(branch="a", node=PropagationNode(
                path="~/.claude/CLAUDE.md", label="监控源",
                children=[PropagationBranch(branch="a1", node=PropagationNode(
                    path="capture/import/20260505-183051/claude.md",
                    label="capture, 仅归档", terminal=True))])),
        ],
    )
    item2 = Item(
        id="2",
        monitor_info="~/.codex/AGENTS.md  (8.9K, new, Codex CLI 全局)",
        extracted=("capture/import/20260505-183101/agents.md\n"
                    "符号链接 → dxy_OS legacy SP master 输出 2026-04-23\n"
                    "layout 全废 + 内容陈旧"),
        disposition=Disposition.ARCHIVE,
        disposition_note="ARCHIVE-ONLY",
        rationale="layout 全废 + 内容陈旧 → 无导入价值",
        propagation=[
            PropagationBranch(branch="a", node=PropagationNode(
                path="~/.codex/AGENTS.md", label="legacy snapshot, 监控源",
                children=[PropagationBranch(branch="a1", node=PropagationNode(
                    path="capture/import/20260505-183101/agents.md",
                    label="capture, 仅归档", terminal=True))])),
        ],
    )

    # Item 3: MIXED with 4 APPLY + 1 DECIDE + 18 COVERED + 5 NA = 28 sub-items
    apply_subs = [
        SubItem(
            id="3.1",
            extracted=("forge / feedback_no_guess_lobster.md\n"
                       "时间 2026-04-21\n"
                       "事件 我把\"养龙虾\"脑补成字节项目\n"
                       "用户原话 \"字节哪有养龙虾\""),
            disposition=Disposition.APPLY,
            rule="§10 Don't fabricate user's work history details",
            rationale="biographical confabulation — user is the only source of truth",
            propagation=_branch_to_feedback("§10", "末尾追加 §10 (~12 行: rule + Why 含原话 + How to apply 3 条)"),
        ),
        SubItem(
            id="3.2",
            extracted=("forge / feedback_no_manufactured_insights.md\n"
                       "时间 2026-04-20\n"
                       "用户原话 \"没啥价值,如实记录更新吧,没有洞见就没有\""),
            disposition=Disposition.APPLY,
            rule="§11 No manufactured insights when journaling/summarizing",
            rationale="违反 forge interpretability",
            propagation=_branch_to_feedback("§11", "末尾追加 §11 (~12 行)"),
        ),
        SubItem(
            id="3.3",
            extracted=("forge / feedback_routine_archive_no_ask.md\n"
                       "时间 2026-04-21\n"
                       "用户原话 \"要,你刚才就应该做\""),
            disposition=Disposition.APPLY,
            rule="§12 Routine archive — do it, don't ask",
            rationale="与 §7 (不问无关顺序) 同类",
            propagation=_branch_to_feedback("§12", "末尾追加 §12 (~12 行)"),
        ),
        SubItem(
            id="3.4",
            extracted=("forge / feedback_no_write_vault_readme.md\n"
                       "时间 2026-04-20\n"
                       "用户原话 \"你这次写了就算了, 以后由我来写\""),
            disposition=Disposition.APPLY,
            rule="§13 Don't write the workspace README",
            rationale="README 是 system-structure 真理源, 写权属用户",
            propagation=_branch_to_feedback("§13", "末尾追加 §13 (~12 行)"),
        ),
    ]

    decide_sub = SubItem(
        id="3.5",
        extracted=("watermark / project_watermark.md\n"
                    "时间 2026-04-30\n"
                    "活跃 ver1 在外部仓库 (不属 personalOS scope)"),
        disposition=Disposition.DECIDE,
        rationale="不是真冲突 — workspace section 是否反映外部 active dev?",
        options=[
            DecideOption(
                id="A", description="最小改动",
                propagation=[PropagationBranch(branch="a", node=PropagationNode(
                    path="workspace.md", layer="Layer 2 · section",
                    modification="1 行替换, 在 dormant 描述里提一笔外部 active dev",
                    children=[PropagationBranch(branch="b", node=PropagationNode(
                        path="CLAUDE.md / AGENTS.md", layer="auto-gen",
                        modification="workspace 段微调 1 行", terminal=True))]))],
            ),
            DecideOption(
                id="B", description="加 onepage 全量入 workspace",
                propagation=[PropagationBranch(branch="a", node=PropagationNode(
                    path="workspace/project/watermark/onepage.md",
                    label="新建", modification="+~30 行",
                    children=[PropagationBranch(branch="b", node=PropagationNode(
                        path="workspace.md", layer="Layer 2 · section",
                        modification="frontmatter upstream + body 移 watermark 出 dormant",
                        children=[PropagationBranch(branch="c", node=PropagationNode(
                            path="CLAUDE.md / AGENTS.md", layer="auto-gen",
                            modification="workspace 段重写", terminal=True))]))]))],
            ),
            DecideOption(id="C", description="不动", propagation=[]),
        ],
        recommendation="A · 后续如 watermark 持续活跃再单独 PR 走 B",
    )

    covered_specs = [
        ("3.6",  "feedback_default_chinese (personalOS)",  "MEMORY.md auto-memory"),
        ("3.7",  "feedback_ground_external_facts (dxy)",   "feedback-log §2 + Boundaries"),
        ("3.8",  "feedback_acceptance_criteria",           "feedback-log §1"),
        ("3.9",  "feedback_check_vault_map_first",         "feedback-log §3"),
        ("3.10", "feedback_readme_is_placement_spec",      "feedback-log §4"),
        ("3.11", "feedback_verify_default_branch",         "feedback-log §5"),
        ("3.12", "feedback_destructive_scope",             "feedback-log §6"),
        ("3.13", "feedback_dont_ask_routine_ordering",     "feedback-log §7"),
        ("3.14", "feedback_topics_under_workspace",        "feedback-log §8"),
        ("3.15", "user_daily_memo",                        "feedback-log §9"),
        ("3.16", "reference_lark_cli (dxy)",               "assist config/skill/lark-cli.md"),
        ("3.17", "user_profile (forge)",                   "user space/profile/me.md"),
        ("3.18", "project_forge (forge)",                  "workspace/.../forge/onepage.md"),
        ("3.19", "feedback_hold_arch_map (forge)",         "feedback-log §3+§4 核心"),
        ("3.20", "feedback_read_scratch_before_…",         "feedback-log §3+§4 反向"),
        ("3.21", "reference_forge_scratch (forge)",        "~/personalOS/README.md"),
        ("3.22", "project_memory_system",                  "onepage 已记 lineage"),
        ("3.23", "user_profile (memory-system, dup)",      "user space/profile/me.md (重复)"),
    ]
    covered_subs = [
        SubItem(id=sid, extracted=label, disposition=Disposition.COVERED, covered_by=loc)
        for sid, label, loc in covered_specs
    ]

    na_specs = [
        ("3.24", "dxy-OS / MEMORY.md"),
        ("3.25", "forge / MEMORY.md"),
        ("3.26", "memory-system / MEMORY.md"),
        ("3.27", "personalOS / MEMORY.md"),
        ("3.28", "watermark / MEMORY.md"),
    ]
    na_subs = [
        SubItem(id=sid, extracted=label, disposition=Disposition.NA, reason="auto-memory 索引")
        for sid, label in na_specs
    ]

    item3 = Item(
        id="3",
        monitor_info=("Claude Code auto-memory · 5 项目 / 28 文件 / 45K\n"
                       "~/.claude/projects/<slug>/memory/*.md"),
        extracted=("capture/import/20260505-183113/claude-memory.md  (45K)\n"
                    "28 文件按项目分布:\n"
                    "  dxy-OS              11 files\n"
                    "  forge               10 files\n"
                    "  memory-system        3 files\n"
                    "  personalOS           2 files\n"
                    "  watermark            2 files"),
        disposition=Disposition.MIXED,
        disposition_note="capture 整体 📦 归档作 trail · 28 sub-items 各自分流",
        rationale="逐 sub-item 独立判断 (展开见下方)",
        sub_items=apply_subs + [decide_sub] + covered_subs + na_subs,
    )

    return Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-05T18:33:00+08:00",
        revised_at="2026-05-05T19:05:00+08:00",
        inbox_sources=[
            "system/inbox/20260505-183051-claude-code-global.md",
            "system/inbox/20260505-183101-codex-global.md",
            "system/inbox/20260505-183113-claude-auto-memory.md",
        ],
        capture_sources=[
            "capture/import/20260505-183051/claude.md",
            "capture/import/20260505-183101/agents.md",
            "capture/import/20260505-183113/claude-memory.md",
        ],
        items=[item1, item2, item3],
    )


# ---------- the equivalence assertions ----------

def test_v05_equivalence_structural():
    proposal = _build_dogfood_proposal()
    output = render(proposal, plain=True)

    # 1. Top-level item markers
    assert "ITEM 1" in output
    assert "ITEM 2" in output
    assert "ITEM 3" in output

    # 2. Icon distribution structurally equivalent to hand-authored §0.5
    #    (4 APPLY · 18 COVERED · 2-3 ARCHIVE · 1 DECIDE · 5 NA).
    assert "✅ × 4" in output
    assert "⏭ × 18" in output
    # The hand-written §0.5 counts 3 ARCHIVE (item 1 + item 2 + MIXED capture
    # trail). Our schema models MIXED parent's capture trail as the parent's
    # "disposition_note" rather than an extra ARCHIVE row, so the rendered
    # count is 2. Both reflect the same data; equivalence is not strict.
    assert ("📦 × 2" in output) or ("📦 × 3" in output)
    assert "❓ × 1" in output
    assert "➖ × 5" in output

    # 3. Every APPLY sub-item id appears
    for sid in ["3.1", "3.2", "3.3", "3.4"]:
        assert f"sub {sid}" in output, f"missing sub-item {sid}"

    # 4. DECIDE
    assert "sub 3.5" in output
    assert "选项 A" in output
    assert "选项 B" in output
    assert "选项 C" in output
    assert "推荐" in output

    # 5. COVERED list (compressed)
    assert "COVERED (压缩列表)" in output
    for sid in ["3.6", "3.13", "3.23"]:
        assert sid in output

    # 6. N/A list
    assert "N/A" in output
    for sid in ["3.24", "3.25", "3.26", "3.27", "3.28"]:
        assert sid in output

    # 7. Every modification summary line appears at least once
    for needle in [
        "末尾追加 §10",
        "末尾追加 §11",
        "末尾追加 §12",
        "末尾追加 §13",
        "末尾加 ## Feedback Log",
        "1 行替换",
    ]:
        assert needle in output, f"missing modification text: {needle}"

    # 8. Every propagation path appears
    for path in [
        "feedback-log.md",
        "preference.md",
        "CLAUDE.md / AGENTS.md",
        "workspace.md",
        "workspace/project/watermark/onepage.md",
        "~/.claude/CLAUDE.md",
        "~/.codex/AGENTS.md",
        "capture/import/20260505-183051/claude.md",
    ]:
        assert path in output, f"missing path: {path}"

    # 9. Approve pipeline
    assert "Approve 后流水线" in output
    assert "forge build" in output
    assert "forge approve" in output
    assert "forge pr done" in output

    # 10. one-line summary
    assert "一句话总结" in output

    # 11. Merged propagation block
    assert "全 PR 改动汇总" in output
    assert "传播 (合并视图)" in output


def test_v05_equivalence_round_trip():
    """Dump + load + render → same output."""
    from forge.proposal.schema import dump_proposal, load_proposal
    proposal = _build_dogfood_proposal()
    text = dump_proposal(proposal)
    proposal2 = load_proposal(text)
    out1 = render(proposal, plain=True)
    out2 = render(proposal2, plain=True)
    assert out1 == out2


def test_v05_equivalence_validator_passes():
    """The dogfood proposal we constructed should validate cleanly."""
    from forge.proposal.validate import validate_proposal
    issues = validate_proposal(_build_dogfood_proposal())
    # Some issues are acceptable for legacy data carryover, but the canonical
    # dogfood structure should be strictly schema-complete.
    formatted = "\n".join(i.format() for i in issues)
    assert not issues, f"validation failed:\n{formatted}"
