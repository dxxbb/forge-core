"""End-to-end regression tests for v0.3.2 YAML block-scalar dumper.

Background: v0.3.1 `forge proposal new/render/validate` rendered multi-line
`extracted` / `rationale` / `covered_by` strings as either:

1. flow scalars with literal `\\n` escapes (single line of 600+ chars), or
2. folded `'…'` scalars with `''` quote-escape and double-newline paragraph
   breaks plus 6-space indents.

v0.3.2 normalizes all multi-line strings to YAML literal block scalar (`|`).
This test module pins:

  - `dump_proposal` produces `: |` for any multi-line string field
  - dumped output never contains literal `\\n` inside a quoted string
  - dumped output never contains the v0.3.1 folded-scalar tell `\\n\\n      `
  - `forge proposal reformat` converts existing v0.3.1-shaped PRs in place
  - reformat is idempotent (already-block-scalar files round-trip unchanged)
  - reformat preserves the proposal body verbatim, including the
    `<!-- BEGIN AUTO-RENDERED -->` … `<!-- END -->` block
  - `forge proposal validate` (default) auto-reformats stale PRs
"""

from __future__ import annotations

from pathlib import Path

import yaml
from click.testing import CliRunner

from forge.cli import main
from forge.proposal.reformat import (
    needs_reformat,
    reformat_file,
    reformat_text,
)
from forge.proposal.schema import (
    Item,
    Proposal,
    SubItem,
    dump_proposal,
    forge_yaml_dump,
    load_proposal,
)


# ---------------- forge_yaml_dump primitives ----------------


def test_forge_dump_emits_block_scalar_for_multiline_string():
    text = forge_yaml_dump({"extracted": "line one\nline two\nline three"})
    # block scalar marker present
    assert ": |" in text
    # no literal `\n` inside a quoted scalar
    assert "\\n" not in text
    # the actual content lines are present
    assert "line one" in text
    assert "line two" in text


def test_forge_dump_keeps_single_line_strings_plain():
    text = forge_yaml_dump({"id": "1", "monitor_info": "/foo/bar (123 chars)"})
    # No block-scalar markers expected for short single-line strings.
    assert ": |" not in text
    assert "/foo/bar (123 chars)" in text


def test_forge_dump_round_trip_idempotent():
    """dump → load → dump should produce identical output."""
    payload = {
        "items": [
            {
                "id": "1",
                "extracted": "alpha\nbeta\ngamma",
                "rationale": "first paragraph reason\n\nsecond paragraph follow-up",
            }
        ]
    }
    once = forge_yaml_dump(payload)
    reloaded = yaml.safe_load(once)
    twice = forge_yaml_dump(reloaded)
    assert once == twice


# ---------------- dump_proposal: schema-aware path ----------------


def test_dump_proposal_extracted_uses_block_scalar():
    p = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-06T00:00:00+08:00",
        items=[
            Item(
                id="1",
                monitor_info="/Users/foo/.claude/CLAUDE.md (8576 chars)",
                extracted=(
                    "capture/import/20260506-000000/claude.md\n"
                    "  - source: /Users/foo/.claude/CLAUDE.md\n"
                    "  - captured_at: 2026-05-06 00:00:00+08:00\n"
                    "内容是 forge-core 编译产物 …"
                ),
                rationale="第一段 rationale\n\n第二段 follow-up",
            )
        ],
    )
    text = dump_proposal(p)
    # block-scalar marker for both multi-line fields
    assert "  extracted: |" in text
    assert "  rationale: |" in text
    # NO literal `\n` inside any quoted string
    assert "\\n" not in text
    # NO folded-scalar quote-escape tell
    assert "''" not in text
    # NO double-newline + 6-space-indent paragraph break (v0.3.1 folded form)
    assert "\n\n      " not in text


def test_dump_proposal_subitem_extracted_uses_block_scalar():
    p = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-06T00:00:00+08:00",
        items=[
            Item(
                id="3",
                monitor_info="/Users/foo/.claude/projects/.../MEMORY.md",
                sub_items=[
                    SubItem(
                        id="3.1",
                        extracted=(
                            'claude-memory.md L215-L230\n'
                            'Why: 用户明确 "默认还是说中文"\n\n'
                            '原文承认: "工作语言简体中文为主"'
                        ),
                        rationale=(
                            "feedback-log.md §1 已收录\n"
                            "新增内容是 \"在 forge triage 中纠正\" 这一新事件"
                        ),
                    )
                ],
            )
        ],
    )
    text = dump_proposal(p)
    # block-scalar present for the sub-item too (deeper indent)
    assert "    extracted: |" in text
    assert "    rationale: |" in text
    # NO literal `\n` and NO folded `''` quote escape
    assert "\\n" not in text
    assert "''" not in text


def test_dump_proposal_no_long_lines_in_frontmatter():
    """No frontmatter line should exceed 300 chars after the v0.3.2 dumper."""
    p = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at="2026-05-06T00:00:00+08:00",
        items=[
            Item(
                id="1",
                monitor_info="/foo (5000 chars)",
                extracted=("line " + "x" * 50 + "\n") * 6,  # 6 * 56 ≈ 336 wrapped
                rationale="r1\n" * 4,
            )
        ],
    )
    text = dump_proposal(p)
    # split out frontmatter (between leading `---` and next `---`)
    lines = text.splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    fm_lines = lines[1:end]
    too_long = [(i, len(line)) for i, line in enumerate(fm_lines) if len(line) > 300]
    assert not too_long, f"unexpected long frontmatter lines: {too_long}"


# ---------------- reformat_text / reformat_file ----------------


_V031_FLOW_SAMPLE = '''---
kind: pr
type: context-import
status: pending
created_at: '2026-05-06T00:00:00+08:00'
items:
- id: '1'
  monitor_info: /foo (8576 chars)
  extracted: "capture/import/20260506-000000/claude.md\\n  - source: /foo\\n内容是 forge-core 编译产物。\\n"
  disposition: COVERED
  rationale: '第一段 rationale 内容。

    第二段 rationale 内容。

    '
  covered_by: 'foo.md §1

    bar.md §2

    '
---

# Proposal body

<!-- BEGIN AUTO-RENDERED · forge pr render -->
some rendered content
<!-- END AUTO-RENDERED -->

## Usage
text after.
'''


def test_reformat_text_converts_v031_to_block_scalar():
    new_text, changed = reformat_text(_V031_FLOW_SAMPLE)
    assert changed
    # block-scalar markers appeared
    assert "  extracted: |" in new_text
    assert "  rationale: |" in new_text
    assert "  covered_by: |" in new_text
    # flow-scalar `\n` literal gone
    assert "\\n" not in new_text
    # folded-scalar quote-escape tells gone
    assert "\n\n    " not in new_text  # paragraph-break + indent for folded scalar


def test_reformat_text_preserves_body_verbatim():
    new_text, changed = reformat_text(_V031_FLOW_SAMPLE)
    assert changed
    assert "# Proposal body" in new_text
    assert "<!-- BEGIN AUTO-RENDERED · forge pr render -->" in new_text
    assert "some rendered content" in new_text
    assert "<!-- END AUTO-RENDERED -->" in new_text
    assert "## Usage" in new_text
    assert "text after." in new_text


def test_reformat_text_idempotent():
    once, changed_once = reformat_text(_V031_FLOW_SAMPLE)
    assert changed_once
    twice, changed_twice = reformat_text(once)
    assert not changed_twice
    assert once == twice


def test_reformat_text_no_frontmatter_passthrough():
    text = "no frontmatter at all\njust body\n"
    new_text, changed = reformat_text(text)
    assert not changed
    assert new_text == text


def test_reformat_text_preserves_semantics():
    """After reformat, parsing the YAML must yield the same Python objects."""
    original_fm = yaml.safe_load(_V031_FLOW_SAMPLE.split("---\n", 2)[1])
    new_text, _ = reformat_text(_V031_FLOW_SAMPLE)
    new_fm = yaml.safe_load(new_text.split("---\n", 2)[1])
    assert new_fm == original_fm


def test_reformat_file_writes_backup(tmp_path):
    f = tmp_path / "proposal.md"
    f.write_text(_V031_FLOW_SAMPLE, encoding="utf-8")
    res = reformat_file(f, backup=True)
    assert res.changed
    bak = tmp_path / "proposal.md.bak"
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == _V031_FLOW_SAMPLE


def test_reformat_file_idempotent_no_backup_no_change(tmp_path):
    f = tmp_path / "proposal.md"
    # Write a file that's already block-scalar shaped.
    initial = dump_proposal(load_proposal(_V031_FLOW_SAMPLE))
    f.write_text(initial, encoding="utf-8")
    res = reformat_file(f, backup=True)
    assert not res.changed
    bak = tmp_path / "proposal.md.bak"
    assert not bak.exists()


def test_needs_reformat_helper():
    assert needs_reformat(_V031_FLOW_SAMPLE) is True
    once, _ = reformat_text(_V031_FLOW_SAMPLE)
    assert needs_reformat(once) is False


# ---------------- CLI: forge proposal reformat ----------------


def _make_workspace(tmp_path: Path, proposal_text: str) -> tuple[Path, str]:
    ws = tmp_path / "ws"
    (ws / "system" / "inbox").mkdir(parents=True)
    pr_id = "20260506-000000-test-import"
    pr_dir = ws / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    (pr_dir / "proposal.md").write_text(proposal_text, encoding="utf-8")
    return ws, pr_id


def test_cli_proposal_reformat_changes_file(tmp_path):
    ws, pr_id = _make_workspace(tmp_path, _V031_FLOW_SAMPLE)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "reformat", pr_id, "--root", str(ws), "--no-backup"],
    )
    assert result.exit_code == 0, result.output
    assert "reformatted" in result.output

    text = (ws / "system" / "pr" / pr_id / "proposal.md").read_text(encoding="utf-8")
    assert "  extracted: |" in text
    assert "\\n" not in text


def test_cli_proposal_reformat_idempotent_says_no_change(tmp_path):
    """Run reformat twice; second invocation reports `no change`."""
    ws, pr_id = _make_workspace(tmp_path, _V031_FLOW_SAMPLE)
    runner = CliRunner()
    runner.invoke(main, ["proposal", "reformat", pr_id, "--root", str(ws), "--no-backup"])
    result = runner.invoke(
        main,
        ["proposal", "reformat", pr_id, "--root", str(ws), "--no-backup"],
    )
    assert result.exit_code == 0, result.output
    assert "no change" in result.output


def test_cli_proposal_reformat_writes_backup_by_default(tmp_path):
    ws, pr_id = _make_workspace(tmp_path, _V031_FLOW_SAMPLE)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "reformat", pr_id, "--root", str(ws)],
    )
    assert result.exit_code == 0, result.output
    bak = ws / "system" / "pr" / pr_id / "proposal.md.bak"
    assert bak.exists()
    assert bak.read_text(encoding="utf-8") == _V031_FLOW_SAMPLE


def test_cli_proposal_validate_auto_reformats(tmp_path):
    """v0.3.2: validate's default flow runs reformat first; once a v0.3.1
    PR with stale flow-scalar frontmatter goes through validate, the file is
    re-shaped to block-scalar form."""
    ws, pr_id = _make_workspace(tmp_path, _V031_FLOW_SAMPLE)
    runner = CliRunner()
    # Validate will also report schema issues for this fixture (it's missing
    # a propagation/etc), but the reformat side-effect must run first.
    runner.invoke(main, ["proposal", "validate", pr_id, "--root", str(ws)])

    text = (ws / "system" / "pr" / pr_id / "proposal.md").read_text(encoding="utf-8")
    # Reformat happened: block-scalar markers appear, flow `\n` gone.
    assert "  extracted: |" in text
    assert "\\n" not in text


def test_cli_proposal_validate_no_reformat_skips(tmp_path):
    """When validate runs `--no-reformat` AND validation fails (so the
    auto-render step is skipped), the file stays in its original v0.3.1
    flow-scalar form. (When validation passes, render_inline still goes
    through dump_proposal which uses the v0.3.2 block-scalar dumper, so
    the file shape changes regardless — that's intentional.)"""
    # Build a fixture that's intentionally missing required fields so validate
    # fails and skips the render-inline step.
    incomplete = '''---
kind: pr
type: context-import
status: pending
created_at: '2026-05-06T00:00:00+08:00'
items:
- id: '1'
  monitor_info: /foo (8576 chars)
  extracted: "line one\\n  - source: /foo\\nmore content here\\n"
---

# Proposal body
'''
    ws, pr_id = _make_workspace(tmp_path, incomplete)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "validate", pr_id, "--root", str(ws), "--no-reformat"],
    )
    # validation fails → auto-render skipped → file untouched
    assert result.exit_code != 0
    text = (ws / "system" / "pr" / pr_id / "proposal.md").read_text(encoding="utf-8")
    # File still has the v0.3.1 flow-scalar form — reformat did NOT run.
    assert "\\n" in text
    assert "  extracted: |" not in text
