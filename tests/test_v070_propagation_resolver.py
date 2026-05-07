"""v0.7 propagation-resolver tests.

Covers:
  1. KB topic single file → asset → section → runtime
  2. Asset (assist config) → section → runtime
  3. Multiple KB topic files share same section → grouping
  4. KB index/log → terminal
  5. Raw clipping → terminal
  6. propagation_hint=terminal explicit
  7. propagation_hint=light explicit (terminal + label "light")
  8. Sections file directly → runtime
  9. Unmatched path → terminal + warn
 10. Empty modified_files → behaves like v0.6 (validator still requires
     propagation for APPLY)
 11. Both propagation + modified_files → resolver skips, propagation kept
 12. e2e: TSMC-style PR with 5 modified files; resolver builds the same
     structural shape as a hand-drawn tree
 13. Multiple unrelated sections → independent branches (regression guard)
 14. Path under config dir → config terminal
 15. Modifications dict propagates to leaf nodes
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.proposal.resolver import (
    ResolveReport,
    classify_path,
    load_workspace_index,
    resolve_owner,
    resolve_proposal,
)
from forge.proposal.schema import (
    Disposition,
    Item,
    Proposal,
    PropagationBranch,
    PropagationNode,
    SubItem,
    dump_proposal,
    load_proposal,
)
from forge.proposal.validate import validate_proposal


# ----------------------------------------------------------------------------
# personalOS-style workspace fixture (separate from the conftest one — the
# resolver lives in a `context build/` layout, not `sp/`).
# ----------------------------------------------------------------------------


@pytest.fixture
def pos_workspace(tmp_path: Path) -> Path:
    """personalOS-style workspace with sections + configs that mirror the real
    layout (knowledge base / preference / about user / workspace / skill).
    """
    sec_dir = tmp_path / "context build" / "sections"
    cfg_dir = tmp_path / "context build" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)

    (sec_dir / "knowledge base.md").write_text(
        "---\nname: knowledge base\ntype: knowledge-base\n"
        "upstream:\n  - public knowledge base/topic/\n---\n\n"
        "KB body.\n",
        encoding="utf-8",
    )
    (sec_dir / "preference.md").write_text(
        "---\nname: preference\ntype: preference\nupstream:\n"
        "  - assist config/work preference/working-style.md\n"
        "  - assist config/work preference/boundaries.md\n---\n\n"
        "Pref body.\n",
        encoding="utf-8",
    )
    (sec_dir / "about user.md").write_text(
        "---\nname: about user\ntype: identity\nupstream:\n"
        "  - assist config/about user.md\n---\n\nIdentity body.\n",
        encoding="utf-8",
    )
    (sec_dir / "workspace.md").write_text(
        "---\nname: workspace\ntype: workspace\nupstream:\n"
        "  - workspace/project/\n---\n\nWorkspace body.\n",
        encoding="utf-8",
    )
    (sec_dir / "skill.md").write_text(
        "---\nname: skill\ntype: skill\nupstream:\n"
        "  - assist config/skill/\n---\n\nSkill body.\n",
        encoding="utf-8",
    )

    (cfg_dir / "claude-code.md").write_text(
        "---\nname: CLAUDE\ntarget: claude-code\nsections:\n"
        "  - about user\n  - workspace\n  - knowledge base\n"
        "  - preference\n  - skill\n---\n",
        encoding="utf-8",
    )
    (cfg_dir / "agents-md.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - about user\n  - workspace\n  - knowledge base\n"
        "  - preference\n  - skill\n---\n",
        encoding="utf-8",
    )
    return tmp_path


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _flatten_paths(branches: list[PropagationBranch]) -> list[str]:
    """Walk a propagation tree and collect every node.path (in DFS order)."""
    out: list[str] = []

    def walk(node: PropagationNode) -> None:
        if node.path:
            out.append(node.path)
        for child in node.children:
            walk(child.node)

    for br in branches:
        walk(br.node)
    return out


def _flatten_labels(branches: list[PropagationBranch]) -> list[str]:
    out: list[str] = []

    def walk(node: PropagationNode) -> None:
        if node.label:
            out.append(node.label)
        for child in node.children:
            walk(child.node)

    for br in branches:
        walk(br.node)
    return out


def _make_item(
    *,
    item_id: str = "1",
    modified_files: list[str] | None = None,
    modifications: dict[str, str] | None = None,
    propagation_hints: dict[str, str] | None = None,
    disposition: Disposition = Disposition.APPLY,
) -> Item:
    return Item(
        id=item_id,
        monitor_info=f"item-{item_id}",
        extracted=f"extracted-{item_id}",
        disposition=disposition,
        rationale="reason",
        modified_files=list(modified_files or []),
        modifications=dict(modifications or {}),
        propagation_hints=dict(propagation_hints or {}),
    )


# ----------------------------------------------------------------------------
# Case 1 — KB topic single file → asset → section → runtime
# ----------------------------------------------------------------------------


def test_kb_topic_single_file(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "public knowledge base/topic/tech/ai/compute/ai-compute.md",
    ])
    res = resolve_owner(item, index)
    assert res.status == "resolved"
    assert len(item.propagation) == 1, "single file → single top branch"

    paths = _flatten_paths(item.propagation)
    # asset path → section path → runtime config paths (claude + agents)
    assert "public knowledge base/topic/tech/ai/compute/ai-compute.md" in paths
    assert "context build/sections/knowledge base.md" in paths
    assert any("claude-code.md" in p for p in paths), \
        f"expected runtime claude-code in tree; got {paths}"
    assert any("agents-md.md" in p for p in paths), \
        f"expected runtime agents-md in tree; got {paths}"


# ----------------------------------------------------------------------------
# Case 2 — asset (assist config/) → section → runtime
# ----------------------------------------------------------------------------


def test_asset_to_preference_section(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "assist config/work preference/boundaries.md",
    ])
    resolve_owner(item, index)
    paths = _flatten_paths(item.propagation)
    assert "context build/sections/preference.md" in paths
    # boundaries.md is upstream of `preference`, so claude-code + agents-md
    # both compile preference → both runtime nodes appear.
    assert paths.count("context build/sections/preference.md") == 1
    assert sum(p.startswith("context build/config/") for p in paths) == 2


# ----------------------------------------------------------------------------
# Case 3 — multiple KB topic files share same section → grouping
# ----------------------------------------------------------------------------


def test_multiple_files_share_section(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "public knowledge base/topic/tech/ai/compute/ai-compute.md",
        "public knowledge base/topic/tech/ai/codex.md",
        "public knowledge base/topic/tech/ai/claude-code.md",
    ])
    resolve_owner(item, index)
    # All three files map to `knowledge base` section → one grouped branch.
    assert len(item.propagation) == 1
    branch = item.propagation[0]
    # Container label encodes the count + section name.
    assert "3 assets" in branch.node.label
    # The section node should appear ONCE in the tree (shared subtree).
    paths = _flatten_paths(item.propagation)
    assert paths.count("context build/sections/knowledge base.md") == 1
    # All three asset paths should be present.
    for f in [
        "public knowledge base/topic/tech/ai/compute/ai-compute.md",
        "public knowledge base/topic/tech/ai/codex.md",
        "public knowledge base/topic/tech/ai/claude-code.md",
    ]:
        assert f in paths


# ----------------------------------------------------------------------------
# Case 4 — KB index/log files → terminal (no section / runtime)
# ----------------------------------------------------------------------------


def test_kb_index_log_terminal(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "public knowledge base/topic/index.md",
        "public knowledge base/topic/log.md",
    ])
    res = resolve_owner(item, index)
    # Both files match the directory pattern `public knowledge base/topic/`
    # so they DO get classified as upstream (since pattern is dir-prefix).
    # That's actually a v0.7 design Q — but in personalOS the topic/ dir
    # itself is upstream of `knowledge base` section, so index+log will
    # propagate too. The test guards the resolver behaviour explicitly:
    # they ARE classified as section_upstream because the pattern is dir-
    # level. Authors must mark them as terminal via propagation_hints.
    paths = _flatten_paths(item.propagation)
    assert "public knowledge base/topic/index.md" in paths
    assert "public knowledge base/topic/log.md" in paths


def test_kb_index_terminal_via_hint(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(
        modified_files=[
            "public knowledge base/topic/index.md",
            "public knowledge base/topic/log.md",
        ],
        propagation_hints={
            "public knowledge base/topic/index.md": "terminal",
            "public knowledge base/topic/log.md": "terminal",
        },
    )
    resolve_owner(item, index)
    # When hinted terminal both files become single-node terminal branches —
    # no section/runtime.
    for br in item.propagation:
        assert not br.node.children, \
            f"hinted terminal node should have no children; got {br.node.children}"
        assert br.node.terminal


# ----------------------------------------------------------------------------
# Case 5 — raw clipping → terminal
# ----------------------------------------------------------------------------


def test_raw_clipping_terminal(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "capture/web clipping/2026-04-29-some-source.md",
    ])
    res = resolve_owner(item, index)
    # capture/ is not upstream of any section in the fixture → terminal +
    # warn.
    assert res.status == "resolved"
    assert any("not in any section.upstream" in w for w in res.warnings)
    assert len(item.propagation) == 1
    assert item.propagation[0].node.terminal


# ----------------------------------------------------------------------------
# Case 6 — propagation_hint=terminal explicit
# ----------------------------------------------------------------------------


def test_hint_terminal_explicit(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    # ai-compute.md normally goes asset → section → runtime, but with hint
    # `terminal` the resolver should stop at the file.
    item = _make_item(
        modified_files=["public knowledge base/topic/tech/ai/compute/ai-compute.md"],
        propagation_hints={
            "public knowledge base/topic/tech/ai/compute/ai-compute.md": "terminal",
        },
    )
    resolve_owner(item, index)
    branch = item.propagation[0]
    assert branch.node.terminal
    assert not branch.node.children


# ----------------------------------------------------------------------------
# Case 7 — propagation_hint=light explicit (terminal + label "light")
# ----------------------------------------------------------------------------


def test_hint_light_explicit(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(
        modified_files=["public knowledge base/topic/tech/ai/ai-policy.md"],
        propagation_hints={
            "public knowledge base/topic/tech/ai/ai-policy.md": "light",
        },
    )
    resolve_owner(item, index)
    branch = item.propagation[0]
    assert branch.node.terminal
    assert "light" in branch.node.label.lower()


# ----------------------------------------------------------------------------
# Case 8 — sections file directly → runtime (no section parent)
# ----------------------------------------------------------------------------


def test_sections_file_direct_to_runtime(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    # Direct edit of the section file itself.
    item = _make_item(modified_files=[
        "context build/sections/preference.md",
    ])
    resolve_owner(item, index)
    branch = item.propagation[0]
    # Children are runtime branches (claude-code + agents-md), not another
    # section.
    assert branch.node.label == "section"
    paths = _flatten_paths(item.propagation)
    # The asset path is the section file itself; section node is NOT
    # duplicated as a child. Children point straight to runtime configs.
    assert paths[0] == "context build/sections/preference.md"
    assert all(
        not p.startswith("context build/sections/")
        for p in paths[1:]
    ), f"sections file shouldn't repeat as child; got {paths}"


# ----------------------------------------------------------------------------
# Case 9 — unmatched path → terminal + warn
# ----------------------------------------------------------------------------


def test_unmatched_path_terminal_with_warn(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "system/inbox/random-file.md",  # not in any section.upstream
    ])
    res = resolve_owner(item, index)
    assert any("not in any section.upstream" in w for w in res.warnings)
    assert item.propagation[0].node.terminal


# ----------------------------------------------------------------------------
# Case 10 — empty modified_files → no resolve, validator still requires
# propagation for APPLY
# ----------------------------------------------------------------------------


def test_empty_modified_files_falls_back_to_v06(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[])
    res = resolve_owner(item, index)
    assert res.status == "skipped_no_files"
    assert item.propagation == []

    # Validator should still complain because APPLY needs a propagation tree
    # AND there's no modified_files alternative either.
    proposal = Proposal(items=[item], status="pending", created_at="2026-05-07T00:00:00")
    issues = validate_proposal(proposal)
    assert any("propagation" in i.path and "must declare" in i.message for i in issues)


# ----------------------------------------------------------------------------
# Case 11 — both propagation + modified_files → resolver skips, propagation kept
# ----------------------------------------------------------------------------


def test_existing_propagation_takes_precedence(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    hand_drawn = [PropagationBranch(
        branch="z",
        node=PropagationNode(path="hand/drawn.md", terminal=True),
    )]
    item = _make_item(modified_files=[
        "public knowledge base/topic/tech/ai/compute/ai-compute.md",
    ])
    item.propagation = list(hand_drawn)
    res = resolve_owner(item, index)
    assert res.status == "skipped_existing"
    assert any("already filled" in w or "skipped" in w for w in res.warnings)
    # propagation untouched.
    assert item.propagation == hand_drawn


# ----------------------------------------------------------------------------
# Case 12 — TSMC-style e2e: 5 modified files, mix of asset / index / clipping;
# resolver builds the structurally-equivalent tree.
# ----------------------------------------------------------------------------


def test_e2e_tsmc_style_proposal(pos_workspace: Path):
    """e2e: a PR that creates a new KB topic ai-compute.md (TSMC-flavoured),
    updates two adjacent KB topics (ai-policy + claude-code), and bumps the
    KB index + log. Total = 5 modified files. The resolver should:

      - cluster the three KB-topic edits under a single grouped branch
        sharing one `knowledge base` section subtree
      - mark index/log as terminals (via hint, since they'd otherwise dir-
        match the topic/ pattern)
      - only the grouped branch reaches runtime (claude-code + agents-md)
    """
    index = load_workspace_index(pos_workspace)
    item = _make_item(
        modified_files=[
            "public knowledge base/topic/tech/ai/compute/ai-compute.md",
            "public knowledge base/topic/tech/ai/ai-policy.md",
            "public knowledge base/topic/tech/ai/claude-code.md",
            "public knowledge base/topic/index.md",
            "public knowledge base/topic/log.md",
        ],
        modifications={
            "public knowledge base/topic/tech/ai/compute/ai-compute.md":
                "新建 ai-compute.md (TSMC supercycle)",
            "public knowledge base/topic/tech/ai/ai-policy.md":
                "ai-policy 段加 TSMC capacity 引用",
            "public knowledge base/topic/tech/ai/claude-code.md":
                "claude-code 段加 sub-section 链接",
            "public knowledge base/topic/index.md":
                "tech/ai/ 段加 ai/compute/ sub-section",
            "public knowledge base/topic/log.md":
                "+ ai-compute.md created",
        },
        propagation_hints={
            "public knowledge base/topic/index.md": "terminal",
            "public knowledge base/topic/log.md": "terminal",
        },
    )
    res = resolve_owner(item, index)
    assert res.status == "resolved"

    # Three branches: 1 grouped (3 asset files share KB section) + 2 terminals
    # for index/log.
    assert len(item.propagation) == 3, [
        b.node.path or b.node.label for b in item.propagation
    ]
    grouped_branches = [b for b in item.propagation if "assets →" in b.node.label]
    assert len(grouped_branches) == 1
    assert "3 assets" in grouped_branches[0].node.label

    # Grouped branch should contain the section node exactly once.
    paths = _flatten_paths(grouped_branches)
    assert paths.count("context build/sections/knowledge base.md") == 1
    # Two runtime configs reached.
    runtime_count = sum(
        "context build/config/" in p for p in paths
    )
    assert runtime_count == 2, paths

    # The two index/log branches are terminal, no runtime in their subtree.
    terminal_branches = [b for b in item.propagation if b not in grouped_branches]
    assert len(terminal_branches) == 2
    for br in terminal_branches:
        assert br.node.terminal
        assert not br.node.children


# ----------------------------------------------------------------------------
# Case 13 — multiple unrelated sections → independent branches
# ----------------------------------------------------------------------------


def test_files_targeting_different_sections(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "assist config/work preference/working-style.md",  # → preference
        "public knowledge base/topic/tech/ai/codex.md",     # → knowledge base
    ])
    resolve_owner(item, index)
    # Two independent branches — no group container.
    assert len(item.propagation) == 2
    assert all("assets →" not in b.node.label for b in item.propagation)


# ----------------------------------------------------------------------------
# Case 14 — config file path → config terminal (recompiles runtime)
# ----------------------------------------------------------------------------


def test_config_file_classified_as_config(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(modified_files=[
        "context build/config/claude-code.md",
    ])
    resolve_owner(item, index)
    branch = item.propagation[0]
    assert branch.node.terminal
    assert "config" in branch.node.label.lower()


# ----------------------------------------------------------------------------
# Case 15 — modifications dict propagates to leaf nodes
# ----------------------------------------------------------------------------


def test_modifications_carry_to_leaf(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    item = _make_item(
        modified_files=[
            "public knowledge base/topic/tech/ai/compute/ai-compute.md",
        ],
        modifications={
            "public knowledge base/topic/tech/ai/compute/ai-compute.md":
                "新建文件, 含 frontmatter + summary",
        },
    )
    resolve_owner(item, index)
    # The asset node carries the modification text.
    asset_node = item.propagation[0].node
    assert "新建文件" in asset_node.modification


# ----------------------------------------------------------------------------
# Schema round-trip: modified_files / modifications / propagation_hints
# survive load → dump.
# ----------------------------------------------------------------------------


def test_schema_round_trip_v07_fields():
    src = """---
kind: pr
type: context-import
status: pending
created_at: 2026-05-07T00:00:00
items:
- id: '1'
  monitor_info: source
  extracted: e
  disposition: APPLY
  rationale: r
  modified_files:
  - public knowledge base/topic/tech/ai/codex.md
  - public knowledge base/topic/log.md
  modifications:
    public knowledge base/topic/tech/ai/codex.md: |
      multi-line
      modification
    public knowledge base/topic/log.md: '+ codex updated'
  propagation_hints:
    public knowledge base/topic/log.md: terminal
---

body
"""
    p = load_proposal(src)
    item = p.items[0]
    assert item.modified_files == [
        "public knowledge base/topic/tech/ai/codex.md",
        "public knowledge base/topic/log.md",
    ]
    assert "multi-line" in item.modifications[
        "public knowledge base/topic/tech/ai/codex.md"
    ]
    assert item.propagation_hints == {
        "public knowledge base/topic/log.md": "terminal"
    }
    # Round-trip
    out = dump_proposal(p)
    p2 = load_proposal(out)
    assert p2.items[0].modified_files == item.modified_files
    assert p2.items[0].modifications == item.modifications
    assert p2.items[0].propagation_hints == item.propagation_hints


# ----------------------------------------------------------------------------
# resolve_proposal walks all items + sub-items
# ----------------------------------------------------------------------------


def test_resolve_proposal_walks_subitems(pos_workspace: Path):
    index = load_workspace_index(pos_workspace)
    sub = SubItem(
        id="3.1",
        extracted="sub-extracted",
        disposition=Disposition.APPLY,
        rationale="r",
        modified_files=[
            "assist config/work preference/working-style.md",
        ],
    )
    item = Item(
        id="3",
        monitor_info="mixed-source",
        extracted="overview",
        disposition=Disposition.MIXED,
        sub_items=[sub],
    )
    proposal = Proposal(items=[item], status="pending", created_at="2026-05-07T00:00:00")
    report: ResolveReport = resolve_proposal(proposal, index)
    assert report.resolved == 1
    # Sub now has propagation populated.
    assert sub.propagation
    paths = _flatten_paths(sub.propagation)
    assert "context build/sections/preference.md" in paths


# ----------------------------------------------------------------------------
# Validate is permissive when modified_files is supplied (no propagation
# required at validation time — resolver is expected to fill it)
# ----------------------------------------------------------------------------


def test_validate_accepts_modified_files_alternative():
    item = Item(
        id="1",
        monitor_info="m",
        extracted="e",
        disposition=Disposition.APPLY,
        rationale="r",
        modified_files=["public knowledge base/topic/x.md"],
    )
    proposal = Proposal(
        items=[item],
        status="pending",
        created_at="2026-05-07T00:00:00",
    )
    issues = validate_proposal(proposal)
    # No "propagation must be declared" issue since modified_files is set.
    assert not any(
        i.path.endswith(".propagation") and "must declare" in i.message
        for i in issues
    ), [i.format() for i in issues]


# ----------------------------------------------------------------------------
# CLI integration: `forge proposal validate` runs the resolver in-place.
# ----------------------------------------------------------------------------


def test_cli_proposal_validate_resolves_in_place(pos_workspace: Path, tmp_path: Path):
    """End-to-end: write a proposal.md with `modified_files`, run `forge
    proposal validate <pr-id>`, and check the file now contains a populated
    propagation tree.
    """
    from click.testing import CliRunner
    from forge.cli import main

    pr_id = "20260507-120000-tsmc"
    pr_dir = pos_workspace / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    proposal_path = pr_dir / "proposal.md"
    proposal_path.write_text(
        """---
kind: pr
type: context-import
status: pending
created_at: 2026-05-07T12:00:00
items:
- id: '1'
  monitor_info: TSMC supercycle synthesis
  extracted: |
    new KB topic ai-compute.md (TSMC supercycle); index/log bump
  disposition: APPLY
  rationale: distill 4 clippings into one topic page
  modified_files:
  - public knowledge base/topic/tech/ai/compute/ai-compute.md
  - public knowledge base/topic/index.md
  - public knowledge base/topic/log.md
  modifications:
    public knowledge base/topic/tech/ai/compute/ai-compute.md: |
      新建文件, frontmatter + summary
    public knowledge base/topic/index.md: 'tech/ai/ 段加 ai/compute/ sub-section'
    public knowledge base/topic/log.md: '+ ai-compute.md created'
  propagation_hints:
    public knowledge base/topic/index.md: terminal
    public knowledge base/topic/log.md: terminal
---
body
""",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "validate", pr_id, "--root", str(pos_workspace)],
    )
    assert result.exit_code == 0, result.output
    assert "resolved propagation for 1 item(s)" in result.output

    # Re-read: propagation should now be present in YAML.
    text = proposal_path.read_text(encoding="utf-8")
    assert "propagation:" in text
    assert "context build/sections/knowledge base.md" in text
    # Index/log are terminal hints — no section node attached.
    # The grouped/inline asset for ai-compute should reach runtime configs.
    assert "context build/config/claude-code.md" in text
    assert "context build/config/agents-md.md" in text
