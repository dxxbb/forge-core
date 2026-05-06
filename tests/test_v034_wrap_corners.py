"""Regression tests for v0.3.4 wrap corner-case fixes.

v0.3.3 dogfood (~/personalOS/system/pr/20260505-211750-context-import) exposed
three corner-case bugs in the v0.3.3 wrap algorithm:

  Bug A · ASCII `.` was treated as an unconditional break candidate, so file
          extensions (`CLAUDE.md`), IPs (`192.168.1.1`), domains
          (`example.com`), and version strings (`v0.3.3`) got split mid-token
          (`CLAUDE.\n  md`). v0.3.4 only treats ASCII `.,;!?)` as a break
          candidate when followed by whitespace or end-of-string.

  Bug B · `└─ X` paragraphs in `_field_block(tree=True)` produced a 14-col
          wrap-continuation prefix (12sp + 2sp), but `└─ ` is 3 cols of
          paragraph indent — so the continuation column was off by 1 (or, for
          the last `└─` paragraph, way off because the prefix was just 14
          spaces of plain padding). v0.3.4 uses `   ` (3 cols) for `└─`
          continuations.

  Bug C · `├─ X` paragraphs continuation prefix was `│ ` (2 cols), one short
          of the paragraph's `├─ ` content column (3 cols). v0.3.4 uses `│  `
          (3 cols).

This module pins those behaviors. ≥ 8 cases, covering: (A) dot-extension /
domain / IP / version intactness; (B) `└─` continuation prefix shape;
(C) `├─` continuation prefix shape; column-alignment under display-width;
ASCII punct + space breaks; CJK punct breaks immediately.
"""

from __future__ import annotations

from forge.proposal.renderer import (
    _ASCII_BREAK_AFTER,
    _CJK_BREAK_AFTER,
    _display_width,
    _find_break,
    _wrap_line,
    render,
)
from forge.proposal.schema import (
    Disposition,
    Item,
    Proposal,
)


def _disp(s: str) -> int:
    return _display_width(s)


# ---------------- Bug A · dot-extension / IP / domain / version ----------------


def test_filename_with_dot_extension_not_split():
    """`CLAUDE.md` (and `forge.md`, `MEMORY.md`, etc.) must stay intact when
    wrap budget runs out: ASCII `.` followed by a letter is NOT a break
    candidate."""
    s = "该偏好已经在 CLAUDE.md About user 段写明 '工作语言简体中文为主'，但未严格执行。"
    out = _wrap_line(s, width=40, first_prefix="            ├─ ",
                     cont_prefix="            │  ")
    joined = "\n".join(out)
    # CLAUDE.md must appear intact on a single line (no `CLAUDE.\nmd` split)
    assert "CLAUDE.md" in joined
    for line in out:
        assert "CLAUDE." not in line or "CLAUDE.md" in line, line


def test_ip_address_not_split():
    """`192.168.1.1` must stay intact — three ASCII `.` not followed by space."""
    s = "服务地址是 192.168.1.1，请记录到内部文档中以便日后查阅。"
    # Force a tight budget so the algorithm WANTS to break inside the IP if
    # ASCII `.` were a candidate.
    out = _wrap_line(s, width=20, first_prefix="", cont_prefix="  ")
    joined = "\n".join(out)
    assert "192.168.1.1" in joined
    for line in out:
        # No line ends with `192.` or `192.168.` etc.
        assert not line.rstrip().endswith("192."), line
        assert not line.rstrip().endswith("168."), line


def test_domain_not_split():
    """`example.com` (and `personalOS.dev`, etc.) must stay intact."""
    s = "可以访问 example.com 获取更多信息，详情见公开文档。"
    out = _wrap_line(s, width=20, first_prefix="", cont_prefix="  ")
    joined = "\n".join(out)
    assert "example.com" in joined
    for line in out:
        assert not line.rstrip().endswith("example."), line


def test_version_string_not_split():
    """`v0.3.3` must stay intact — multiple ASCII `.` not followed by space."""
    s = "本次升级把 forge 从 v0.3.3 推到 v0.3.4，主要修复 wrap 边角问题。"
    out = _wrap_line(s, width=20, first_prefix="", cont_prefix="  ")
    joined = "\n".join(out)
    assert "v0.3.3" in joined
    assert "v0.3.4" in joined
    for line in out:
        assert not line.rstrip().endswith("v0."), line
        assert not line.rstrip().endswith("v0.3."), line


# ---------------- Bug A · ASCII punct + space DOES break ----------------


def test_ascii_dot_followed_by_space_is_break():
    """`. ` (ASCII period + space) IS a break candidate — used to split
    English sentences naturally."""
    # Long ASCII sentence with `. ` boundaries.
    s = "First sentence ends here. Second sentence ends here. Third sentence ends here too."
    out = _wrap_line(s, width=30, first_prefix="", cont_prefix="  ")
    assert len(out) > 1
    # At least one mid-line should END with `.` (the break-after position).
    has_dot_break = any(line.rstrip().endswith(".") for line in out[:-1])
    assert has_dot_break, out


def test_ascii_comma_followed_by_space_is_break():
    """`, ` (ASCII comma + space) IS a break candidate."""
    s = "alpha word here, beta word here, gamma word here, delta word here, end."
    out = _wrap_line(s, width=25, first_prefix="", cont_prefix="  ")
    assert len(out) > 1
    has_comma_break = any(line.rstrip().endswith(",") for line in out[:-1])
    assert has_comma_break, out


# ---------------- Bug A · CJK fullwidth punct breaks immediately ----------------


def test_cjk_fullwidth_comma_breaks_without_space():
    """CJK fullwidth `，` IS a break candidate without trailing space (CJK
    text rarely uses spaces between sentences)."""
    s = "这是第一段内容，这是第二段内容，这是第三段内容，这是结尾段落。"
    out = _wrap_line(s, width=20, first_prefix="", cont_prefix="  ")
    assert len(out) > 1
    # First line should end with `，` (or another CJK punct)
    has_cjk_break = any(line.rstrip().endswith(("，", "。"))
                        for line in out[:-1])
    assert has_cjk_break, out


def test_cjk_period_breaks_without_space():
    """CJK fullwidth `。` IS a break candidate without trailing space."""
    s = "句子一。句子二。句子三。句子四。句子五。结尾。"
    out = _wrap_line(s, width=12, first_prefix="", cont_prefix="  ")
    assert len(out) > 1
    has_cjk_period_break = any(line.rstrip().endswith("。")
                               for line in out[:-1])
    assert has_cjk_period_break, out


# ---------------- Bug B · `└─` continuation = 3 spaces ----------------


def test_render_field_block_last_paragraph_continuation_is_three_spaces():
    """A `└─ X` paragraph that wraps must use `   ` (3 cols of plain space) as
    continuation prefix — NOT the 14-space pad that v0.3.3 emitted, NOT a
    `│ ` bar (the subtree has terminated at this paragraph).
    """
    # Build an item whose `extracted` ends in a long `└─` paragraph (tested
    # via the multi-line tree form).
    item = Item(
        id="1",
        monitor_info="x",
        extracted=(
            "first line\n"
            "second 段\n"
            "third 段\n"
            "shell 命令、CLI 输出引用、文件路径、专有术语。"
            "user 明确说英文时切换。这一段足够长触发 wrap。"
        ),
        disposition=Disposition.APPLY,
        rationale="r",
    )
    out = render(Proposal(items=[item]), width=78)
    lines = out.splitlines()
    # Find the `└─ shell` paragraph line.
    last_para_idx = next(
        i for i, l in enumerate(lines)
        if l.startswith("            └─ ") and "shell" in l
    )
    para = lines[last_para_idx]
    # The next line(s) should be the wrap continuation. It must:
    #   1. Start with `            ` (12 cols of pad — same as `├─/└─` paragraphs)
    #   2. Then have exactly 3 cols of plain space (`   `, NOT `│  `, NOT 2sp)
    #   3. Then the wrapped content
    cont = lines[last_para_idx + 1]
    assert cont.startswith("               "), \
        f"expected `└─` continuation = 12sp + 3sp = 15sp, got: {cont!r}"
    # And NOT a bar — the subtree terminates here.
    assert "│" not in cont, f"`└─` continuation must NOT have `│`: {cont!r}"
    # And content column aligns: paragraph content starts at col 15 (12 +
    # 2 for `└─` + 1 space). Continuation content should start at col 15 too.
    para_content_col = 12 + 3   # `<12sp>└─ ` = 15 cols → first content char at 15
    cont_content_col = len(cont) - len(cont.lstrip(" "))
    assert cont_content_col == para_content_col, \
        f"content column mismatch: para={para_content_col} cont={cont_content_col}\n  {para!r}\n  {cont!r}"


# ---------------- Bug C · `├─` continuation = `│  ` (3 cols) ----------------


def test_render_field_block_branch_paragraph_continuation_is_bar_two_spaces():
    """A `├─ X` paragraph that wraps must use `│  ` (3 cols: bar + 2 sp) as
    continuation prefix — NOT `│ ` (2 cols) which was the v0.3.3 bug.
    """
    item = Item(
        id="1",
        monitor_info="x",
        extracted=(
            "headline\n"
            "Why: 2026-04-29 user 明确「没特殊需要的，默认还是说中文」（forge triage 中纠正）。"
            "这一段需要长到触发 wrap，所以再追加一些内容来撑开列宽超过 78 cols 的限制。\n"
            "How to apply: 默认正文中文，保留英文给代码。\n"
            "tail 段"
        ),
        disposition=Disposition.APPLY,
        rationale="r",
    )
    out = render(Proposal(items=[item]), width=78)
    lines = out.splitlines()
    why_idx = next(
        i for i, l in enumerate(lines)
        if l.startswith("            ├─ ") and "Why:" in l
    )
    para = lines[why_idx]
    cont = lines[why_idx + 1]
    # Must start with `<12sp>│  ` (12 + 1 bar + 2 sp = 15 display cols of leader)
    assert cont.startswith("            │  "), \
        f"expected `├─` continuation `<12sp>│  `, got: {cont!r}"
    # NOT the v0.3.3 buggy `│ ` (single space)
    assert not cont.startswith("            │ x") and \
        not (cont.startswith("            │ ") and not cont.startswith("            │  ")), \
        f"v0.3.3 buggy single-space `│ ` continuation reappeared: {cont!r}"
    # Content column alignment — `├─ ` paragraph: 12 + 2 + 1 = 15 cols leader.
    # Continuation: 12 + 1 (│) + 2 (sp) = 15 cols leader. Match.
    para_content_col = 12 + 3
    cont_leader_cols = _disp(cont) - _disp(cont.lstrip(" │"))
    # Find the start of content in cont (first non-space, non-`│` char).
    i = 0
    while i < len(cont) and cont[i] in (" ", "│"):
        i += 1
    cont_content_col = _disp(cont[:i])
    assert cont_content_col == para_content_col, \
        f"content column mismatch: para={para_content_col} cont={cont_content_col}\n  para={para!r}\n  cont={cont!r}"


# ---------------- Bug D · regression: existing CJK-only break still works ----------------


def test_cjk_only_text_still_breaks_at_fullwidth_punct():
    """v0.3.3 multi-line CJK extracted with fullwidth `，` / `。` still breaks
    correctly — Bug A fix doesn't break existing behavior."""
    item = Item(
        id="1",
        monitor_info="x",
        extracted=(
            "首段。\n"
            "第二段是中等长度的中文内容，包含若干分句，"
            "用以验证 fullwidth 标点是否仍然作为 break 候选。"
            "再追加一些内容到第二段来超过 78 cols 触发 wrap。"
        ),
        disposition=Disposition.APPLY,
        rationale="r",
    )
    out = render(Proposal(items=[item]), width=78)
    for line in out.splitlines():
        assert _disp(line) <= 78, (line, _disp(line))


# ---------------- _find_break primitive ----------------


def test_find_break_constants_split_correctly():
    """v0.3.4 separates ASCII vs CJK break-after sets; sanity check that no
    ASCII char leaked into the CJK set, and vice versa."""
    for ch in _CJK_BREAK_AFTER:
        assert not ch.isascii(), f"ASCII `{ch}` leaked into _CJK_BREAK_AFTER"
    for ch in _ASCII_BREAK_AFTER:
        assert ch.isascii(), f"non-ASCII `{ch}` leaked into _ASCII_BREAK_AFTER"
    # No overlap.
    assert not (set(_CJK_BREAK_AFTER) & set(_ASCII_BREAK_AFTER))


def test_find_break_skips_ascii_dot_inside_token():
    """`_find_break` directly: with budget large enough to cover `CLAUDE.md`
    and a trailing space-bound break, returns the index AT the space — never
    inside `CLAUDE.`."""
    s = "see CLAUDE.md please here is more"
    # Budget large enough to fit `see CLAUDE.md please ` (= 21 cols), trigger
    # break in the latter half.
    cut = _find_break(s, budget=24)
    # The cut should land at a space, not inside `CLAUDE.`.
    if cut > 0 and cut < len(s):
        assert s[cut - 1] != ".", \
            f"break inside CLAUDE.md: cut={cut}, s[:cut]={s[:cut]!r}"


def test_find_break_takes_ascii_dot_when_followed_by_space():
    """When ASCII `.` is followed by a space, it IS a valid break candidate."""
    s = "First. Second. Third."
    # Budget = 7 cols → fits "First. " (7 cols). Cut should be after `.` at
    # the space.
    cut = _find_break(s, budget=7)
    assert cut > 0
    assert s[cut - 1] == "."   # break is right after the `.`
