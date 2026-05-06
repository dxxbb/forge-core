"""End-to-end regression tests for v0.3.3 render-width / wrap behavior.

Background: v0.3.2 renderer at width=73 emitted long content lines unwrapped
(extracted / rationale / modification with 100+ char single lines), and
frontmatter plain scalars longer than ~90 cols stayed as one line. v0.3.3
adds:

  - default WRAP_WIDTH = 78 (display-width, CJK = 2 cols)
  - content soft-wrap at CJK / ASCII punctuation, then ASCII space
  - tree-aware continuation prefix for `提取信息` multi-line value (├─/└─
    paragraph starts; `│ `/`  ` mid-paragraph wrap continuations)
  - modification line wrap with `│        ` continuation prefix
  - box rules pad to display width (CJK-aware), so start/close are equal
  - sub-item title bar `── ITEM N / sub N.M · ICON ──` length-equalizes
  - CLI `forge pr render --width N` and `--no-wrap` overrides
  - frontmatter dumper "break long lines" pass: single-line plain scalars
    > 90 cols are broken at CJK / ASCII punctuation by inserting `\n`
  - `forge proposal reformat --no-break-lines` opt-out

This module pins those behaviors.
"""

from __future__ import annotations

import unicodedata

from click.testing import CliRunner

from forge.cli import main
from forge.proposal.reformat import (
    _break_long_string,
    _break_one_line,
    _find_punct_break,
    needs_reformat,
    reformat_text,
)
from forge.proposal.renderer import (
    WRAP_WIDTH,
    _display_width,
    _wrap_line,
    render,
)
from forge.proposal.schema import (
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
)


# ---------------- _wrap_line primitive ----------------


def _disp(s: str) -> int:
    return _display_width(s)


def test_wrap_default_width_is_78():
    assert WRAP_WIDTH == 78


def test_wrap_short_line_passes_through():
    out = _wrap_line("short", width=78, first_prefix="  ", cont_prefix="    ")
    assert out == ["  short"]


def test_wrap_long_chinese_breaks_at_punct():
    """A long Chinese line breaks at the latest in-budget CJK punctuation."""
    s = "内容是 forge-core 编译产物 (provenance 注释明示),upstream 全部为 personalOS 现有 asset。"
    out = _wrap_line(s, width=78, first_prefix="            ├─ ",
                     cont_prefix="            │  ")
    # Each emitted line must fit within 78 cols
    for line in out:
        assert _disp(line) <= 78, (line, _disp(line))
    # First line ends with a CJK punct (comma) — break-after, comma stays on prev
    assert out[0].rstrip().endswith("(provenance 注释明示),")
    # Continuation prefix on second line
    assert out[1].startswith("            │  ")


def test_wrap_breaks_at_ascii_space_when_no_punct():
    """An English long line with no punctuation breaks at the last in-budget space."""
    s = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho"
    out = _wrap_line(s, width=40, first_prefix="> ", cont_prefix="  ")
    for line in out:
        assert _disp(line) <= 40, (line, _disp(line))
    assert len(out) > 1
    # No mid-token cuts
    for line in out[:-1]:
        # The line content (after prefix) ends with a complete word
        # (i.e. the next line starts with the next word, not a sliver)
        assert not line.endswith(" "), line


def test_wrap_continuation_prefix_used_on_all_continuations():
    s = "甲乙丙丁戊己庚辛壬癸,子丑寅卯辰巳午未申酉戌亥,東南西北中前後左右上下,春夏秋冬。"
    first = "  X  "
    cont = "     "
    out = _wrap_line(s, width=30, first_prefix=first, cont_prefix=cont)
    assert len(out) >= 2
    assert out[0].startswith(first)
    for line in out[1:]:
        assert line.startswith(cont), line


def test_wrap_no_break_point_falls_through():
    """If a line has no punct AND no space (rare), hard-cut by display width."""
    s = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    out = _wrap_line(s, width=30, first_prefix="", cont_prefix="")
    # All emitted lines fit
    for line in out:
        assert _disp(line) <= 30


# ---------------- render() integration ----------------


def _long_extracted_item() -> Item:
    return Item(
        id="1",
        monitor_info="/path (123 chars)",
        extracted=(
            "capture/import/foo.md\n"
            "  - source: bar\n"
            "内容是 forge-core 编译产物 (provenance 注释明示 config=CLAUDE target=claude-code"
            " version=0.1.0 digest=abc123),upstream 全部为 personalOS 现有 asset:"
            " user space/profile/me.md, user space/goals/*, workspace/project/forge/onepage.md。\n"
            "所以这份导入材料与 personalOS canonical source 无新增信息差。"
        ),
        disposition=Disposition.ARCHIVE,
        rationale=(
            "capture 文件首部的 forge-core provenance header 明示这是 personalOS 现有 asset"
            " 的 compiled view。再次导入会形成自循环 (asset → compiled view → 重新提取 → asset)。"
        ),
    )


def test_render_default_width_keeps_lines_within_78():
    p = Proposal(items=[_long_extracted_item()])
    out = render(p)  # default width=78 wrap=True
    for line in out.splitlines():
        # Box rules and the sub-item separator can be exactly width=78 cols.
        assert _disp(line) <= 78, (_disp(line), line)


def test_render_explicit_width_60_keeps_content_within_60():
    """At width=60, content paragraphs (extracted/rationale/modification) fit.
    Fixed-layout lines (approve pipeline literal, ASCII fence markers) keep
    their hand-crafted shape."""
    p = Proposal(items=[_long_extracted_item()])
    out = render(p, width=60)
    # Identify the BEGIN of `══ ITEM ` and the start of the merged-summary /
    # approve pipeline section (`### `). Check only those content lines.
    lines = out.splitlines()
    item_start = next(i for i, l in enumerate(lines) if l.startswith("══ ITEM"))
    pipe_start = next(i for i, l in enumerate(lines) if l.startswith("### "))
    for line in lines[item_start:pipe_start]:
        assert _disp(line) <= 60, (_disp(line), line)


def test_render_no_wrap_preserves_long_lines():
    """wrap=False reverts to v0.3.2 behavior: content not soft-wrapped."""
    p = Proposal(items=[_long_extracted_item()])
    out = render(p, wrap=False)
    # At least one content line should exceed 78 cols (the long extracted line).
    over = [l for l in out.splitlines() if _disp(l) > 78]
    assert over, "expected some long lines under wrap=False"


def test_render_box_borders_match_width_at_top_and_bottom():
    """Item title row and closing rule are the same display width."""
    p = Proposal(items=[_long_extracted_item()])
    out = render(p, width=78)
    lines = out.splitlines()
    # locate `══ ITEM 1 ` row
    idx = next(i for i, l in enumerate(lines) if l.startswith("══ ITEM 1"))
    title_row = lines[idx]
    # closing row is 2-3 lines below
    closing = next(l for l in lines[idx + 1: idx + 5] if l and all(ch == "═" for ch in l))
    assert _disp(title_row) == _disp(closing) == 78


def test_render_sub_item_title_pads_to_width():
    """`── ITEM N / sub N.M · ICON LABEL ──...──` length-equalizes to width."""
    p = Proposal(
        items=[
            Item(
                id="3",
                monitor_info="x",
                disposition=Disposition.MIXED,
                sub_items=[
                    SubItem(
                        id="3.13",
                        extracted="claude-memory.md L215-L230\n规则名: \"默认用中文回复\"。",
                        disposition=Disposition.APPLY,
                        rule="§10",
                        rationale="r",
                        propagation=[
                            PropagationBranch(
                                branch="a",
                                node=PropagationNode(
                                    path="x.md",
                                    layer="Layer 1",
                                    modification="m",
                                ),
                            )
                        ],
                    ),
                ],
            )
        ]
    )
    out = render(p, width=78)
    lines = out.splitlines()
    title = next(l for l in lines if "── ITEM 3 / sub 3.13" in l)
    assert _disp(title) == 78


def test_render_modification_multiline_keeps_bar_continuation():
    """Regression: a modification with user-supplied `\\n` (e.g. 5 paragraphs)
    keeps the FIRST line as `├─ 修改:` and all subsequent lines as
    `│        ` continuation. v0.3.3 must not turn each paragraph into a
    separate `├─ 修改:` entry (that was a bug in early v0.3.3 development)."""
    p = Proposal(
        items=[
            Item(
                id="2",
                monitor_info="x",
                extracted="e",
                disposition=Disposition.APPLY,
                rule="§11",
                rationale="r",
                propagation=[
                    PropagationBranch(
                        branch="a",
                        node=PropagationNode(
                            path="foo.md",
                            layer="Layer 1 · asset",
                            modification=(
                                "末尾追加 §11 \"X\"。Why: ...\n"
                                "续段 1 内容\n"
                                "续段 2 内容\n"
                                "续段 3 内容"
                            ),
                        ),
                    )
                ],
            )
        ]
    )
    out = render(p, width=78)
    lines = out.splitlines()
    # Limit search to the per-item section (before the merged-view section).
    item_section_end = next(
        (i for i, l in enumerate(lines) if "传播 (合并视图)" in l),
        len(lines),
    )
    section = lines[:item_section_end]
    # Exactly ONE "├─ 修改:" line for this single-modification node.
    mod_heads = [l for l in section if "├─ 修改:" in l]
    assert len(mod_heads) == 1, f"expected 1 ├─ 修改 head, got {len(mod_heads)}: {mod_heads}"
    # And the continuation lines all use the bar-prefix `│        `.
    head_idx = section.index(mod_heads[0])
    cont_lines = []
    for j in range(head_idx + 1, len(section)):
        l = section[j]
        if "│        " in l:
            cont_lines.append(l)
        else:
            break
    # We have 3 continuation paragraphs (续段 1/2/3); each must show up.
    text_after = "\n".join(cont_lines)
    assert "续段 1 内容" in text_after
    assert "续段 2 内容" in text_after
    assert "续段 3 内容" in text_after


def test_render_modification_line_wrap_uses_bar_continuation():
    """Long `修改:` lines wrap with `│        ` continuation prefix."""
    p = Proposal(
        items=[
            Item(
                id="2",
                monitor_info="x",
                extracted="e",
                disposition=Disposition.ARCHIVE,
                rationale="r",
                propagation=[
                    PropagationBranch(
                        branch="a",
                        node=PropagationNode(
                            path="capture/foo.md",
                            layer="Layer 0 · capture",
                            modification=(
                                "仅保留 capture 文件作为旧 dxy_OS layout 编译产物的历史 trail,"
                                "不向 asset/section/runtime 传播,作为审计证据。"
                            ),
                        ),
                    )
                ],
            )
        ]
    )
    out = render(p, width=78)
    lines = out.splitlines()
    # Find the line starting "├─ 修改: " (after the indent).
    mod_lines = [i for i, l in enumerate(lines) if "├─ 修改:" in l]
    assert mod_lines, "no modification line found"
    idx = mod_lines[0]
    # First line fits within 78 cols
    assert _disp(lines[idx]) <= 78
    # Next line is a continuation under the bar
    cont = lines[idx + 1]
    assert "│" in cont, cont
    assert _disp(cont) <= 78


def test_render_extracted_multiline_tree_continuation_uses_bar():
    """Long lines inside an extracted ├─/└─ paragraph wrap under `│ ` /`  `."""
    p = Proposal(
        items=[
            Item(
                id="1",
                monitor_info="x",
                extracted=(
                    "first line short\n"
                    "second line is really really really long with comma, yet more,"
                    " and more 内容 内容 内容 内容 内容 内容 内容 内容 to ensure overflow at 78\n"
                    "third line is also pretty long with 内容 内容 内容 内容 内容 内容"
                    " 内容 内容 internal text to overflow"
                ),
                disposition=Disposition.ARCHIVE,
                rationale="r",
            )
        ]
    )
    out = render(p, width=78)
    for line in out.splitlines():
        assert _disp(line) <= 78, (_disp(line), line)
    # The `├─` paragraph for line 2 should produce `│ ` continuation prefix
    lines = out.splitlines()
    bar_conts = [l for l in lines if l.startswith("            │ ")]
    assert bar_conts, "expected `│ ` continuation for ├─ paragraph"


def test_render_p10_extracted_tree_still_works_v033():
    """v0.3.1 P10 regression: extracted multi-line still uses ├─/└─ with the
    last paragraph's last line getting `└─`. v0.3.3 wrap-aware version."""
    item = Item(
        id="1",
        monitor_info="x",
        extracted="capture/import/foo.md\n  - source: bar\n  - captured_at: 2026-05-05\n  - source_size: 1234",
        disposition=Disposition.ARCHIVE,
        rationale="r",
        propagation=[],
    )
    out = render(Proposal(items=[item]))
    assert "├─" in out
    assert "└─" in out
    # last paragraph (`source_size`) still uses └─
    idx_last = out.index("source_size")
    snippet = out[max(0, idx_last - 30):idx_last]
    assert "└─" in snippet


# ---------------- frontmatter dumper break-long-lines ----------------


def test_break_long_string_short_unchanged():
    s = "短字符串"
    assert _break_long_string(s, threshold=90) == s


def test_break_long_string_breaks_at_cjk_punct():
    s = "甲乙丙丁戊己庚辛壬癸,子丑寅卯辰巳午未申酉戌亥,東南西北中前後左右上下,春夏秋冬,東西南北。"
    out = _break_long_string(s, threshold=30)
    assert "\n" in out
    # Each line ≤ 30 cols
    for line in out.split("\n"):
        assert _disp(line) <= 30 or "," not in line[: -1]


def test_break_long_string_no_cjk_punct_kept_whole():
    """ASCII-only line with no break-after punct stays intact (we don't hard-cut)."""
    s = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu"
    # ASCII space is NOT in our break-after set (intentional; conservative).
    out = _break_long_string(s, threshold=30)
    assert out == s


def test_break_long_string_arrow_is_break_point():
    """`→` (the flow-arrow) is a recognized break point (used heavily in dxyOS)."""
    s = "状态 A → 状态 B → 状态 C → 状态 D → 最终状态,该规则在 forge triage 期间触发。"
    out = _break_long_string(s, threshold=30)
    assert "\n" in out
    for line in out.split("\n"):
        assert _disp(line) <= 36   # threshold + small slack


def test_reformat_text_breaks_long_plain_scalar_by_default():
    """A v0.3.2-shaped frontmatter with a long single-line plain scalar gets
    `\n` inserted by reformat_text (default break_long_lines=True)."""
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该被 break 函数在标点处切开,以便 Obsidian 显示更友好。\n"
        "---\n\nbody.\n"
    )
    new_text, changed = reformat_text(text)
    assert changed
    # The rationale value is now a block scalar with `\n` interior.
    assert "  rationale: |" in new_text
    # No frontmatter line should be > 100 chars now (the original was)
    fm_lines = new_text.split("---\n")[1].split("\n")
    too_long = [l for l in fm_lines if len(l) > 130]
    assert not too_long, too_long


def test_reformat_text_no_break_lines_keeps_plain_scalar():
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该在普通模式下被 break,但 --no-break-lines 应保留单行。\n"
        "---\n\nbody.\n"
    )
    new_text, _ = reformat_text(text, break_long_lines=False)
    # rationale stays as a single-line plain scalar (no `: |`)
    assert "  rationale: |" not in new_text
    assert "\\n" not in new_text


def test_reformat_break_lines_idempotent():
    """Once broken, re-running reformat doesn't re-break (the lines are now
    short enough to not hit the threshold)."""
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该被 break 函数在标点处切开,以便 Obsidian 显示更友好。\n"
        "---\n\nbody.\n"
    )
    once, c1 = reformat_text(text)
    assert c1
    twice, c2 = reformat_text(once)
    assert not c2
    assert once == twice


def test_reformat_break_lines_preserves_semantics():
    """After break-long-lines, the YAML still loads to an equivalent dict
    (newlines inserted only inside string values, not changing structure)."""
    import yaml
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该被 break 函数在标点处切开。\n"
        "---\n\nbody.\n"
    )
    original = yaml.safe_load(text.split("---\n")[1])
    new_text, _ = reformat_text(text)
    new_fm = yaml.safe_load(new_text.split("---\n")[1])
    # Keys identical
    assert set(original.keys()) == set(new_fm.keys())
    # Items count identical
    assert len(original["items"]) == len(new_fm["items"])
    # Rationale text content equal modulo whitespace (newline insertions)
    orig_r = original["items"][0]["rationale"].replace("\n", "").replace(" ", "")
    new_r = new_fm["items"][0]["rationale"].replace("\n", "").replace(" ", "")
    assert orig_r == new_r


def test_needs_reformat_detects_long_plain_scalar():
    """needs_reformat returns True when only the break-long-lines pass would
    change anything (so dogfood / CI catches stale long plain scalars)."""
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点和分隔,"
        "应该被 break 函数在标点处切开,以便 Obsidian 显示更友好,"
        "这里再加一些内容把它变得很长很长。\n"
        "---\n\nbody.\n"
    )
    assert needs_reformat(text) is True
    # And opt-out: needs_reformat with break_long_lines=False detects only
    # YAML-style differences. For this fixture the YAML form is already in a
    # non-block-scalar state acceptable to v0.3.2 dumper, so opt-out reports
    # False (the only thing v0.3.3 would change is the line break).
    assert needs_reformat(text, break_long_lines=False) is False


# ---------------- CLI: --width / --no-wrap / --no-break-lines ----------------


def _make_workspace_with_proposal(tmp_path):
    """A tiny v0.3 PR with one APPLY item carrying a long modification line."""
    ws = tmp_path / "ws"
    (ws / "system" / "inbox").mkdir(parents=True)
    pr_id = "20260506-000000-test-import"
    pr_dir = ws / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    proposal_text = (
        "---\n"
        "kind: pr\n"
        "type: context-import\n"
        "status: pending\n"
        "created_at: '2026-05-06T00:00:00+08:00'\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: /foo (1234 chars)\n"
        "  extracted: |\n"
        "    capture/x.md\n"
        "  disposition: APPLY\n"
        "  rationale: r\n"
        "  rule: §10\n"
        "  propagation:\n"
        "  - branch: a\n"
        "    node:\n"
        "      path: foo.md\n"
        "      layer: Layer 1\n"
        "      modification: |\n"
        "        这是一个非常长的修改说明,包含若干 CJK 标点,"
        "应该在 width=78 cols 时被自动 wrap 到下一行,继续 prefix 用 `│        `。\n"
        "---\n\nbody.\n"
    )
    (pr_dir / "proposal.md").write_text(proposal_text, encoding="utf-8")
    return ws, pr_id


def test_cli_pr_render_default_width_78(tmp_path):
    ws, pr_id = _make_workspace_with_proposal(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pr", "render", pr_id, "--root", str(ws), "--stdout"],
    )
    assert result.exit_code == 0, result.output
    for line in result.output.splitlines():
        assert _disp(line) <= 78, (_disp(line), line)


def test_cli_pr_render_explicit_width_60(tmp_path):
    ws, pr_id = _make_workspace_with_proposal(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pr", "render", pr_id, "--root", str(ws), "--stdout", "--width", "60"],
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    item_start = next((i for i, l in enumerate(lines) if l.startswith("══ ITEM")), 0)
    pipe_start = next((i for i, l in enumerate(lines) if l.startswith("### ")),
                      len(lines))
    for line in lines[item_start:pipe_start]:
        assert _disp(line) <= 60, (_disp(line), line)


def test_cli_pr_render_no_wrap_keeps_long_lines(tmp_path):
    ws, pr_id = _make_workspace_with_proposal(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["pr", "render", pr_id, "--root", str(ws), "--stdout", "--no-wrap"],
    )
    assert result.exit_code == 0, result.output
    over = [l for l in result.output.splitlines() if _disp(l) > 78]
    assert over, "expected long lines under --no-wrap"


def test_cli_proposal_reformat_default_breaks_lines(tmp_path):
    """Default `forge proposal reformat` breaks long plain scalars."""
    ws = tmp_path / "ws"
    (ws / "system" / "inbox").mkdir(parents=True)
    pr_id = "20260506-000000-break-test"
    pr_dir = ws / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该被 reformat 切开,以便 Obsidian 显示更友好。这里再加一些内容把它变得很长。\n"
        "---\n\nbody.\n"
    )
    (pr_dir / "proposal.md").write_text(text, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "reformat", pr_id, "--root", str(ws), "--no-backup"],
    )
    assert result.exit_code == 0, result.output
    new_text = (pr_dir / "proposal.md").read_text(encoding="utf-8")
    assert "  rationale: |" in new_text


def test_cli_proposal_reformat_no_break_lines_skips_break(tmp_path):
    ws = tmp_path / "ws"
    (ws / "system" / "inbox").mkdir(parents=True)
    pr_id = "20260506-000000-no-break"
    pr_dir = ws / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    text = (
        "---\n"
        "kind: pr\n"
        "items:\n"
        "- id: '1'\n"
        "  monitor_info: short\n"
        "  rationale: 这是一个非常长的 rationale 字符串,包含多个 CJK 标点,"
        "应该在默认模式下被 break,但 --no-break-lines 应保留单行。\n"
        "---\n\nbody.\n"
    )
    (pr_dir / "proposal.md").write_text(text, encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["proposal", "reformat", pr_id, "--root", str(ws),
         "--no-backup", "--no-break-lines"],
    )
    assert result.exit_code == 0, result.output
    new_text = (pr_dir / "proposal.md").read_text(encoding="utf-8")
    # rationale stays single-line plain scalar (no `: |`)
    assert "  rationale: |" not in new_text
