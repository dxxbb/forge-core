r"""Deterministic renderer for the §0.5 monitor-item view.

Reads a Proposal (loaded by `forge.proposal.schema.load_proposal`) and
produces a text view that's structurally equivalent to the hand-authored
§0.5 in `system/pr/.../proposal.md` (the form a human reviewer expects to
see when triaging a context-import PR).

Layout — all literal:

    Icon legend
    ✅ APPLY · ⏭ COVERED · 📦 ARCHIVE · ❓ DECIDE · ➖ N/A · 🔀 MIXED

    Distribution
    ✅ × N · ⏭ × N · 📦 × N · ❓ × N · ➖ × N (top-level + sub-items)

    ══ ITEM 1 ═══════════════════════════════
       监控:  <monitor_info>
    ═════════════════════════════════════════
      提取信息    <extracted multi-line>
      处理结果    <icon> <disposition> · <note>
      理由        <rationale>
      传播链路
      └─ a: <node.path or label>
         ├─ 修改: <modification line>
         └─ b: <child node.path>
            └─ (终止)

For MIXED items, sub-items are rendered as compact blocks with
`── ITEM N / sub N.M · ICON ──` headers. COVERED/N-A sub-items at the tail
are rendered as compressed list tables.

Box-drawing: default uses ═ ─ │ └ ├. `--plain` falls back to ASCII (`==`,
`--`, `|`, `\`, `+`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from forge.proposal.scaffold import RENDER_BEGIN, RENDER_END
from forge.proposal.schema import (
    DecideOption,
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
    dump_proposal,
    load_proposal,
)


# ------------------------------------------------------------------ glyphs

@dataclass(frozen=True)
class _Glyphs:
    h_double: str   # heavy horizontal — top/bot rule
    h_single: str   # light horizontal — sub-item rule
    v: str          # vertical bar
    branch: str     # ├─
    last: str       # └─
    indent: str     # one indent unit (3 cols)


_BOX = _Glyphs(
    h_double="═",
    h_single="─",
    v="│",
    branch="├─",
    last="└─",
    indent="   ",
)

_PLAIN = _Glyphs(
    h_double="=",
    h_single="-",
    v="|",
    branch="+-",
    last="\\-",
    indent="   ",
)


_DISP_LABEL = {
    Disposition.APPLY: "APPLY",
    Disposition.COVERED: "COVERED",
    Disposition.ARCHIVE: "ARCHIVE-ONLY",
    Disposition.DECIDE: "DECIDE",
    Disposition.NA: "N/A",
    Disposition.MIXED: "MIXED",
}


# v0.3.3: default render wrap width. Long extracted/rationale/modification
# lines are soft-wrapped to this column count (display-width, CJK = 2 cols)
# preferentially at CJK punctuation, then ASCII space. Box rules
# (`══════` / `──────`) and sub-item title bars also length-equalize to
# this width. CLI exposes `--width N` and `--no-wrap` overrides.
WRAP_WIDTH = 78

# CJK punctuation that's a natural break point for soft-wrap (after this
# punctuation, before next char). Includes the flow-arrow `→` used as a step
# separator in dxyOS / forge content. ASCII `:` is intentionally excluded
# so label-value patterns like `**Icon**: ✅` don't break right after the colon.
_CJK_BREAK_AFTER = "，。、；：！？,;.!?）)】」』→"


# ------------------------------------------------------------------ render

def render(
    proposal: Proposal,
    *,
    plain: bool = False,
    width: int = WRAP_WIDTH,
    wrap: bool = True,
) -> str:
    """Render the §0.5 view of a Proposal. Returns the full text.

    `width` is the target column count for box rules and the soft-wrap
    threshold for content lines (display width: CJK / fullwidth = 2 cols).
    `wrap=False` disables content soft-wrap entirely (legacy v0.3.2-and-earlier
    behavior). Box rules still use `width`.
    """
    glyphs = _PLAIN if plain else _BOX
    out: list[str] = []

    out.append("§0.5 · 监控 item 视图 (per-item · disposition + 传播树)")
    out.append("")
    legend = "**Icon**: ✅ APPLY · ⏭ COVERED · 📦 ARCHIVE · ❓ DECIDE · ➖ N/A · 🔀 MIXED"
    if wrap and _display_width(legend) > width:
        # Wrap at ` · ` separators by using them as ASCII-space breaks.
        out.extend(_wrap_line(legend, width=width, first_prefix="", cont_prefix="          "))
    else:
        out.append(legend)

    counts = _count_dispositions(proposal)
    if counts:
        parts = []
        for d in [Disposition.APPLY, Disposition.COVERED, Disposition.ARCHIVE,
                  Disposition.DECIDE, Disposition.NA, Disposition.MIXED]:
            n = counts.get(d, 0)
            if n:
                parts.append(f"{d.icon} × {n}")
        out.append(f"**总分布**: {' · '.join(parts)}")
    out.append("")

    for item in proposal.items:
        out.extend(_render_item(item, glyphs, width=width, wrap=wrap))
        out.append("")

    # Summary: merged propagation
    merged = _render_merged_propagation(proposal, glyphs, width=width, wrap=wrap)
    if merged:
        out.append(_rule(glyphs.h_single, width))
        out.append("")
        out.append("### 全 PR 改动汇总 (合并 APPLY 传播)")
        out.append("")
        out.extend(merged)
        out.append("")

    # Approve pipeline
    out.append(_rule(glyphs.h_single, width))
    out.append("")
    out.append("### Approve 后流水线")
    out.append("")
    out.extend(_render_approve_pipeline(glyphs))
    out.append("")

    # one-liner summary
    summary_line = _render_summary_line(proposal)
    if summary_line:
        out.append(_rule(glyphs.h_single, width))
        out.append("")
        if wrap:
            out.extend(_wrap_line(summary_line, width=width,
                                  first_prefix="**一句话总结**: ",
                                  cont_prefix="                "))
        else:
            out.append(f"**一句话总结**: {summary_line}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------ items


def _render_item(item: Item, glyphs: _Glyphs, *, width: int, wrap: bool = True) -> list[str]:
    out: list[str] = []
    title = f"══ ITEM {item.id} " if glyphs is _BOX else f"== ITEM {item.id} "
    # Box title row: pad to `width` columns of display width (CJK = 2 cols).
    title_cols = _display_width(title)
    fill_count = max(2, width - title_cols)
    out.append(title + glyphs.h_double * fill_count)
    monitor_label = "   监控:  "
    out.append(monitor_label + (item.monitor_info or "").splitlines()[0]
               if item.monitor_info else (monitor_label + "(no monitor info)"))
    for line in (item.monitor_info or "").splitlines()[1:]:
        out.append("           " + line)
    # Closing rule: same column width as title row.
    out.append(glyphs.h_double * width)
    out.append("")

    if item.disposition == Disposition.MIXED:
        # parent extracted (overview), then disposition note, then sub-items
        if item.extracted:
            out.extend(_field_block("提取信息", item.extracted, tree=True, width=width, wrap=wrap))
        if item.disposition:
            out.extend(_one_line_field_lines("处理结果", _disposition_title(item), width=width, wrap=wrap))
        if item.rationale:
            out.extend(_field_block("理由", item.rationale, width=width, wrap=wrap))
        out.append("")
        # render each sub-item
        # group COVERED & NA sub-items at the tail in compressed list form
        prominent = [s for s in item.sub_items
                     if s.disposition not in (Disposition.COVERED, Disposition.NA)]
        covered = [s for s in item.sub_items if s.disposition == Disposition.COVERED]
        na = [s for s in item.sub_items if s.disposition == Disposition.NA]

        for sub in prominent:
            out.extend(_render_sub_item(sub, item.id, glyphs, width=width, wrap=wrap))
            out.append("")

        if covered:
            out.extend(_render_covered_table(item.id, covered, glyphs, width=width))
            out.append("")
        if na:
            out.extend(_render_na_list(item.id, na, glyphs, width=width))
            out.append("")
        return out

    # Non-MIXED top-level item
    if item.extracted:
        out.extend(_field_block("提取信息", item.extracted, tree=True, width=width, wrap=wrap))
    if item.disposition:
        out.extend(_one_line_field_lines("处理结果", _disposition_title(item), width=width, wrap=wrap))
    if item.rationale:
        out.extend(_field_block("理由", item.rationale, width=width, wrap=wrap))
    if item.disposition == Disposition.COVERED and item.covered_by:
        out.extend(_one_line_field_lines("已覆盖于", item.covered_by, width=width, wrap=wrap))
    if item.disposition == Disposition.NA and item.reason:
        out.extend(_one_line_field_lines("原因", item.reason, width=width, wrap=wrap))
    if item.propagation:
        out.append("")
        out.append("  传播链路")
        out.extend(_render_propagation(item.propagation, glyphs, indent="  ", width=width, wrap=wrap))
    if item.disposition == Disposition.DECIDE and item.options:
        out.append("")
        out.append("  传播链路 (多选项, 等用户选)")
        for opt in item.options:
            out.append("")
            out.append(f"  选项 {opt.id} · {opt.description}")
            if opt.propagation:
                out.extend(_render_propagation(opt.propagation, glyphs, indent="  ", width=width, wrap=wrap))
            else:
                out.append(f"  {glyphs.last} (无传播)")
        if item.recommendation:
            out.append("")
            out.append(f"  推荐    {item.recommendation}")
    if item.risk:
        out.append("")
        out.extend(_field_block("风险", item.risk, width=width, wrap=wrap))
    return out


def _render_sub_item(sub: SubItem, parent_id: str, glyphs: _Glyphs, *, width: int, wrap: bool = True) -> list[str]:
    out: list[str] = []
    icon = sub.disposition.icon if sub.disposition else "?"
    label = _DISP_LABEL[sub.disposition] if sub.disposition else "?"
    rule_extra = f" · {sub.rule}" if sub.rule else ""
    title_left = f"  ── ITEM {parent_id} / sub {sub.id} · {icon} {label}{rule_extra} "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    # Pad sub-item title bar to `width` cols of display width (CJK = 2 cols).
    title_cols = _display_width(title_left)
    fill_count = max(2, width - title_cols)
    out.append(title_left + glyphs.h_single * fill_count)
    out.append("")
    if sub.extracted:
        out.extend(_field_block("提取信息", sub.extracted, tree=True, width=width, wrap=wrap))

    if sub.disposition:
        out.extend(_one_line_field_lines("处理结果", _disposition_title(sub), width=width, wrap=wrap))
    if sub.rationale:
        out.extend(_field_block("理由", sub.rationale, width=width, wrap=wrap))

    if sub.disposition == Disposition.COVERED and sub.covered_by:
        out.extend(_one_line_field_lines("已覆盖于", sub.covered_by, width=width, wrap=wrap))
    if sub.disposition == Disposition.NA and sub.reason:
        out.extend(_one_line_field_lines("原因", sub.reason, width=width, wrap=wrap))

    if sub.propagation:
        out.append("")
        out.append("  传播链路")
        out.extend(_render_propagation(sub.propagation, glyphs, indent="  ",
                                          owner_id=sub.id, width=width, wrap=wrap))

    if sub.disposition == Disposition.DECIDE and sub.options:
        out.append("")
        out.append("  传播链路 (多选项, 等用户选)")
        for opt in sub.options:
            out.append("")
            out.append(f"  选项 {opt.id} · {opt.description}")
            if opt.propagation:
                out.extend(_render_propagation(opt.propagation, glyphs, indent="  ", width=width, wrap=wrap))
            else:
                out.append(f"  {glyphs.last} (无传播)")
        if sub.recommendation:
            out.append("")
            out.append(f"  推荐    {sub.recommendation}")
    if sub.risk:
        out.append("")
        out.extend(_field_block("风险", sub.risk, width=width, wrap=wrap))
    return out


def _render_covered_table(
    parent_id: str,
    subs: list[SubItem],
    glyphs: _Glyphs,
    *,
    width: int,
) -> list[str]:
    """Render the compressed COVERED table at the tail of a MIXED item.

    v0.3.3: when label or covered_by would overflow `width` cols on a single
    row, the row falls back to a two-line stacked form:
        3.2   <label>
              <covered_by>
    so the table stays within the requested width.
    """
    out: list[str] = []
    icon = Disposition.COVERED.icon
    title_left = f"  ── ITEM {parent_id} · {len(subs)} 个 {icon} COVERED (压缩列表) "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    title_cols = _display_width(title_left)
    fill = glyphs.h_single * max(2, width - title_cols)
    out.append(title_left + fill)
    out.append("")
    out.append("   #     提取的 memory file                    已覆盖位置")
    sep = "   " + glyphs.h_single * 5 + " " + glyphs.h_single * 36 + "  " + glyphs.h_single * 26
    out.append(sep)
    for sub in subs:
        sid = sub.id or ""
        # extract first non-empty line of `extracted` as the file label
        label = ""
        for line in (sub.extracted or "").splitlines():
            line = line.strip()
            if line:
                label = line
                break
        if not label:
            label = "(no extracted info)"
        covered = sub.covered_by or "(no covered_by)"
        # Try the single-row aligned form first.
        single = f"   {sid:<5} {label:<37} {covered}"
        if _display_width(single) <= width and "\n" not in single:
            out.append(single)
            continue
        # Overflow → stack: id+label on row 1, covered_by indented on row 2.
        # Soft-wrap the label too if it overflows on its own.
        label_first_prefix = f"   {sid:<5} "
        label_cont_prefix = "         "
        out.extend(_wrap_line(label, width=width,
                              first_prefix=label_first_prefix,
                              cont_prefix=label_cont_prefix))
        # covered_by continuation row, also wrap-aware.
        cov_first = "         → "
        cov_cont = "           "
        out.extend(_wrap_line(covered, width=width,
                              first_prefix=cov_first,
                              cont_prefix=cov_cont))
    return out


def _render_na_list(
    parent_id: str,
    subs: list[SubItem],
    glyphs: _Glyphs,
    *,
    width: int,
) -> list[str]:
    out: list[str] = []
    icon = Disposition.NA.icon
    title_left = f"  ── ITEM {parent_id} · {len(subs)} 个 {icon} N/A (索引文件, 无传播) "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    title_cols = _display_width(title_left)
    fill = glyphs.h_single * max(2, width - title_cols)
    out.append(title_left + fill)
    out.append("")
    for sub in subs:
        sid = sub.id or ""
        label = ""
        for line in (sub.extracted or "").splitlines():
            line = line.strip()
            if line:
                label = line
                break
        if not label:
            label = "(no extracted info)"
        out.append(f"   {sid:<5} {label}")
    return out


# ------------------------------------------------------------------ propagation

def _render_propagation(
    branches: list[PropagationBranch],
    glyphs: _Glyphs,
    *,
    indent: str,
    owner_id: str = "",
    width: int = WRAP_WIDTH,
    wrap: bool = True,
) -> list[str]:
    """Render top-level branches under one item/sub-item. Each branch is a
    `└─ a:` / `└─ b:` block.

    `owner_id` is the id of the item / sub-item this propagation belongs to.
    When a branch carries `shared_with: [a, b, c, ...]`, the rendering depends
    on whether `owner_id` is the *first owner*:

      - first owner       → fully expand subtree, append "(共享触发的子链路, 见 sub X / Y / Z)"
      - subsequent owners → render branch as a leaf with "→ 同 sub <first_owner>"
        (modification + descendants are not repeated)

    The first owner is the smallest id in `shared_with` that matches an
    existing sibling. If owner_id is not in shared_with at all, we fall back
    to "first owner" semantics (full expansion + sibling list).
    """
    out: list[str] = []
    for branch in branches:
        out.extend(_render_branch(branch, glyphs, indent=indent, depth=0,
                                   owner_id=owner_id, width=width, wrap=wrap))
    return out


def _is_first_owner(branch: PropagationBranch, owner_id: str) -> bool:
    """True iff this branch should render in full at `owner_id`.

    Convention: "first owner" = the smallest id in shared_with by natural
    sort. If owner_id is not in shared_with at all, treat owner as first.
    Empty shared_with means no sharing → render in full unconditionally.
    """
    if not branch.shared_with:
        return True
    if owner_id and owner_id in branch.shared_with:
        return _natural_min(branch.shared_with) == owner_id
    # owner not listed → owner is the canonical owner
    return True


def _natural_min(ids: list[str]) -> str:
    def key(s: str):
        # split on . then numerify each part; fallback to lexicographic
        parts = s.split(".")
        return tuple(int(p) if p.isdigit() else p for p in parts)
    return min(ids, key=key)


def _render_branch(
    branch: PropagationBranch,
    glyphs: _Glyphs,
    *,
    indent: str,
    depth: int,
    owner_id: str = "",
    width: int = WRAP_WIDTH,
    wrap: bool = True,
) -> list[str]:
    """Render a single propagation branch + its node + its children."""
    out: list[str] = []
    pad = indent + (glyphs.indent * depth)
    label = branch.branch
    node = branch.node
    first_owner = _is_first_owner(branch, owner_id)

    if branch.shared_with and not first_owner:
        # subsequent owner: render as a leaf, point back to the canonical owner
        canonical = _natural_min(branch.shared_with)
        out.append(f"{pad}{glyphs.last} {label}: {_node_head(node)}   (同 sub {canonical} 共享传播)")
        return out

    head = f"{pad}{glyphs.last} {label}: {_node_head(node)}"
    if branch.shared_with and first_owner:
        # canonical owner: fully expand, list other siblings
        others = [x for x in branch.shared_with if x != owner_id]
        if others:
            sibs = " / ".join(f"sub {x}" for x in others)
            head += f"   (共享触发的子链路, 见 {sibs})"
    out.append(head)
    # Modification line. The user-supplied modification string is a single
    # logical block: only its FIRST line gets `├─ 修改: `; subsequent lines
    # (whether user-supplied via `\n` or auto-inserted via wrap) all get
    # `│        ` (8-space pad after the bar) to keep visual alignment.
    if node.modification:
        mod_first_prefix = f"{pad}{glyphs.indent}{glyphs.branch} 修改: "
        mod_cont_prefix = f"{pad}{glyphs.indent}{glyphs.v}        "
        mlines = node.modification.splitlines() or [""]
        for i, mline in enumerate(mlines):
            paragraph_first = mod_first_prefix if i == 0 else mod_cont_prefix
            if not wrap:
                out.append(f"{paragraph_first}{mline}")
                continue
            wrapped = _wrap_line(mline, width=width,
                                 first_prefix=paragraph_first,
                                 cont_prefix=mod_cont_prefix)
            out.extend(wrapped)
    # children: render under increasing depth (carry owner_id through so nested
    # `b → c` shared_with treatments stay consistent)
    for child in node.children:
        out.extend(_render_branch(child, glyphs, indent=indent, depth=depth + 1,
                                   owner_id=owner_id, width=width, wrap=wrap))
    if (not node.children and not node.modification) or node.terminal:
        out.append(f"{pad}{glyphs.indent}{glyphs.last} (终止)")
    elif not node.children and node.modification:
        # leaf with modification but no explicit children → mark terminal
        out.append(f"{pad}{glyphs.indent}{glyphs.last} (终止)")
    return out


def _node_head(node: PropagationNode) -> str:
    """Return the header text for a node: `<path>   (<label>)`."""
    bits: list[str] = []
    if node.path:
        bits.append(node.path)
    if node.layer:
        bits.append(f"({node.layer})")
    if node.label and node.label not in ("", node.layer):
        if not node.layer:
            bits.append(f"({node.label})")
        else:
            bits[-1] = f"({node.layer}, {node.label})"
    if not bits:
        return "(unspecified)"
    return "   ".join(bits)


# ------------------------------------------------------------------ summaries


def _count_dispositions(proposal: Proposal) -> dict[Disposition, int]:
    counts: dict[Disposition, int] = {}
    for item in proposal.items:
        if item.disposition == Disposition.MIXED:
            for sub in item.sub_items:
                if sub.disposition:
                    counts[sub.disposition] = counts.get(sub.disposition, 0) + 1
        elif item.disposition:
            counts[item.disposition] = counts.get(item.disposition, 0) + 1
    return counts


def _render_merged_propagation(
    proposal: Proposal, glyphs: _Glyphs, *, width: int = WRAP_WIDTH, wrap: bool = True
) -> list[str]:
    """Walk all APPLY items / sub-items, dedupe their propagation by node path,
    and render a single tree view.

    Dedup strategy: collect (parent_path, child_path, layer, label) tuples;
    aggregate modification text per (path, layer) pair.
    """
    apply_owners: list[Item | SubItem] = []
    for item in proposal.items:
        if item.disposition == Disposition.APPLY:
            apply_owners.append(item)
        elif item.disposition == Disposition.MIXED:
            for sub in item.sub_items:
                if sub.disposition == Disposition.APPLY:
                    apply_owners.append(sub)
    if not apply_owners:
        return []

    # path -> {layer, mods set, children: dict[path, ...]}
    @dataclass
    class _MergeNode:
        path: str
        layer: str = ""
        label: str = ""
        modifications: list[str] = None  # type: ignore[assignment]
        children: dict[str, "_MergeNode"] = None  # type: ignore[assignment]

        def __post_init__(self):
            if self.modifications is None:
                self.modifications = []
            if self.children is None:
                self.children = {}

    forest: dict[str, _MergeNode] = {}

    def merge_branch(branch: PropagationBranch, parent_dict: dict[str, _MergeNode]) -> None:
        node = branch.node
        key = node.path or node.label or "(unspecified)"
        existing = parent_dict.get(key)
        if existing is None:
            existing = _MergeNode(path=node.path, layer=node.layer, label=node.label)
            parent_dict[key] = existing
        if node.modification and node.modification not in existing.modifications:
            existing.modifications.append(node.modification)
        for child in node.children:
            merge_branch(child, existing.children)

    for owner in apply_owners:
        for branch in owner.propagation:
            merge_branch(branch, forest)

    if not forest:
        return []

    out: list[str] = []
    out.append("传播 (合并视图)")
    def emit(node: _MergeNode, depth: int, last: bool) -> None:
        pad = "  " + (glyphs.indent * depth)
        head = f"{pad}{glyphs.last} {node.path or node.label}"
        if node.layer:
            head += f"   ({node.layer})"
        out.append(head)
        mod_first_prefix = f"{pad}{glyphs.indent}{glyphs.branch} 修改: "
        mod_cont_prefix = f"{pad}{glyphs.indent}{glyphs.v}        "
        for mline in node.modifications:
            sub_lines = mline.splitlines() or [""]
            for i, sub in enumerate(sub_lines):
                paragraph_first = mod_first_prefix if i == 0 else mod_cont_prefix
                if wrap:
                    out.extend(_wrap_line(sub, width=width,
                                          first_prefix=paragraph_first,
                                          cont_prefix=mod_cont_prefix))
                else:
                    out.append(f"{paragraph_first}{sub}")
        children_list = list(node.children.values())
        for i, child in enumerate(children_list):
            emit(child, depth + 1, last=(i == len(children_list) - 1))
        if not children_list:
            out.append(f"{pad}{glyphs.indent}{glyphs.last} (终止)")

    roots = list(forest.values())
    for i, root in enumerate(roots):
        emit(root, 0, last=(i == len(roots) - 1))
    return out


def _render_approve_pipeline(glyphs: _Glyphs) -> list[str]:
    arrow = "─►" if glyphs is _BOX else "->"
    return [
        "```text",
        f"你 approve  {arrow}  forge build       Layer 2 → Layer 3 自动重生成",
        f"            {arrow}  forge doctor      bridge coverage check",
        f"            {arrow}  forge approve -m  \"<note>\"",
        f"            {arrow}  forge pr done     写 system/approve log/ + 移除 PR 目录",
        f"            {arrow}  forge inbox done  关闭 inbox 条目",
        "```",
    ]


def _render_summary_line(proposal: Proposal) -> str:
    """Build a one-sentence summary like the hand-authored §0.5 trailer."""
    counts = _count_dispositions(proposal)
    n_items = len(proposal.items)
    if not n_items:
        return ""
    bits = []
    for d in [Disposition.APPLY, Disposition.COVERED, Disposition.ARCHIVE,
              Disposition.DECIDE, Disposition.NA]:
        n = counts.get(d, 0)
        if n:
            bits.append(f"{n} {d.icon}")
    distribution = " + ".join(bits) if bits else "(空)"
    n_sub_total = sum(len(i.sub_items) for i in proposal.items)
    suffix = f" + {n_sub_total} sub-items" if n_sub_total else ""
    return (f"{n_items} monitored items{suffix} → 分流为 {distribution}.")


# ------------------------------------------------------------------ helpers

# Continuation-prefix patterns for `_field_block`:
#   - tree=True (multi-line `提取信息`): first line at col 14 next to label,
#     subsequent paragraph-firsts use `├─` (or `└─` for the last paragraph),
#     and wrap-continuations within a paragraph use `│ ` (preserves tree shape).
#   - tree=False: first line next to label, subsequent paragraph-firsts and
#     all wrap-continuations use plain `              ` 14-space indent.
_FIELD_VALUE_COL = 14   # `  LABEL    VALUE` — value starts at display col 14


def _field_block(
    label: str,
    value: str,
    *,
    tree: bool = False,
    width: int = WRAP_WIDTH,
    wrap: bool = True,
) -> list[str]:
    """Render a labelled multi-line field. The label sits at column 2 and
    content at column 14, computed by display width (CJK = 2 cols).

    When `tree=True` and value has multiple lines, continuation lines are
    rendered with `├─` / `└─` prefixes (last line uses `└─`). The first
    line is unprefixed (it sits next to the label).

    v0.3.3: each user-supplied paragraph is also soft-wrapped to `width`
    columns (display width). Wrap continuation prefix:
      - tree=True, paragraph started by `├─ ` → continuation uses `│  ` then
        14-space indent (so chars line up under the paragraph content).
      - tree=True, paragraph started by `└─ ` → continuation uses `   ` then
        14-space indent (no bar after last child).
      - tree=False → continuation uses 14-space indent (same as paragraph
        start), keeping the value column aligned.
    """
    lines = (value or "").splitlines() or [""]
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    # First paragraph: starts inline with the label.
    first_prefix = f"  {label}{' ' * pad}"
    # Wrap-continuation for the first paragraph (no tree connector, just
    # 14-space indent so it lines up under the value column).
    first_cont_prefix = " " * _FIELD_VALUE_COL
    out: list[str] = []
    if wrap:
        out.extend(_wrap_line(lines[0], width=width,
                              first_prefix=first_prefix,
                              cont_prefix=first_cont_prefix))
    else:
        out.append(first_prefix + lines[0])
    n = len(lines)
    for i, line in enumerate(lines[1:], start=1):
        if tree and n > 1:
            connector = "└─" if i == n - 1 else "├─"
            # strip any leading spaces that the source string used for visual
            # nesting — we want a clean tree prefix.
            stripped = line.lstrip(" ")
            extra = line[: len(line) - len(stripped)]
            paragraph_prefix = f"            {connector} {extra}"
            # wrap continuation: `│ ` (or `  ` for the last paragraph) then
            # 12-space indent so total reaches the same column as `extra` start.
            bar = "│ " if connector == "├─" else "  "
            cont_prefix = f"            {bar}{' ' * len(extra)}"
            content = stripped
        else:
            paragraph_prefix = "              "
            cont_prefix = "              "
            content = line
        if wrap:
            out.extend(_wrap_line(content, width=width,
                                  first_prefix=paragraph_prefix,
                                  cont_prefix=cont_prefix))
        else:
            out.append(paragraph_prefix + content)
    return out


def _disposition_title(owner) -> str:
    """Compose the 处理结果 title: `[icon] [ENUM_NAME] · [disposition_note]`.

    `disposition_note` is appended only if non-empty (and only if it isn't
    already a redundant ENUM_NAME echo).
    """
    if owner.disposition is None:
        return ""
    icon = owner.disposition.icon
    label = _DISP_LABEL[owner.disposition]
    note = (owner.disposition_note or "").strip()
    rule = (getattr(owner, "rule", "") or "").strip()
    bits = [f"{icon} {label}"]
    if note and note.upper() != label and note != "ARCHIVE-ONLY":
        bits.append(note)
    if rule:
        bits.append(f"提炼为 {rule}")
    return " · ".join(bits)


def _one_line_field(label: str, value: str) -> str:
    """Legacy single-line emit (kept for tests; new call sites should use
    `_one_line_field_lines` to allow soft-wrap)."""
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    return f"  {label}{' ' * pad}{value}"


def _one_line_field_lines(
    label: str, value: str, *, width: int = WRAP_WIDTH, wrap: bool = True
) -> list[str]:
    """One-line field with soft-wrap. Continuation lines are 14-space-indented
    so they line up under the value column."""
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    first_prefix = f"  {label}{' ' * pad}"
    cont_prefix = " " * _FIELD_VALUE_COL
    if not wrap:
        return [first_prefix + value]
    return _wrap_line(value, width=width, first_prefix=first_prefix, cont_prefix=cont_prefix)


def _display_width(s: str) -> int:
    """Approximate terminal column width: CJK / fullwidth = 2, else 1."""
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            w += 2
        else:
            w += 1
    return w


def _rule(ch: str, width: int) -> str:
    return ch * width


# --------------------- v0.3.3: soft-wrap helper ---------------------

def _wrap_line(
    content: str,
    *,
    width: int,
    first_prefix: str,
    cont_prefix: str,
) -> list[str]:
    """Soft-wrap `content` so that `prefix + segment` fits within `width`
    display columns. First segment uses `first_prefix`, subsequent segments
    use `cont_prefix`. Break preference:

      1. After a CJK / ASCII break punctuation (e.g. `,。;:.!?` and matching
         CJK forms). The punctuation stays on the previous line.
      2. At an ASCII whitespace.
      3. Hard cut at the column limit (last resort, for unbroken runs of
         long ASCII or non-punctuated CJK runs).

    Empty content returns a single `first_prefix.rstrip()` line; pure-empty
    paragraphs become `[first_prefix.rstrip()]` to preserve blank-paragraph
    semantics from the v0.3.1 P10 tree rendering.
    """
    if content == "":
        # Preserve the empty-paragraph affordance (rstrip trailing spaces of
        # the prefix to avoid trailing whitespace in output).
        return [first_prefix.rstrip(" ") if first_prefix.strip() == "" else first_prefix]

    out: list[str] = []
    remaining = content
    prefix = first_prefix
    while True:
        prefix_cols = _display_width(prefix)
        budget = max(8, width - prefix_cols)
        # If remaining fits, emit and done.
        if _display_width(remaining) <= budget:
            out.append(prefix + remaining)
            return out
        # Find best break point ≤ budget cols.
        cut = _find_break(remaining, budget)
        if cut <= 0:
            # Could not find a break point at all (extremely long single token).
            # Hard-cut to budget.
            cut = _hard_cut(remaining, budget)
            if cut <= 0:
                # Pathological: emit full line and bail.
                out.append(prefix + remaining)
                return out
        head = remaining[:cut].rstrip(" ")
        tail = remaining[cut:].lstrip(" ")
        out.append(prefix + head)
        if not tail:
            return out
        remaining = tail
        prefix = cont_prefix


def _find_break(s: str, budget: int) -> int:
    """Return the index in `s` (Python char index) at which to cut so that
    `s[:idx]` fits within `budget` display columns AND ends at a natural
    break boundary. Returns 0 if no good break exists.

    Strategy: scan forward column-by-column; remember the *last* break
    candidate we passed within budget. A break candidate is the position
    *after* a CJK/ASCII break punctuation, or the position *of* an ASCII
    space. When we exceed budget, return the latest candidate.
    """
    cols = 0
    last_punct_break = 0   # index after the last in-budget punctuation
    last_space_break = 0   # index of the last in-budget space
    for i, ch in enumerate(s):
        ch_cols = 2 if _is_wide(ch) else 1
        # Going to exceed? stop scanning.
        if cols + ch_cols > budget:
            # Prefer punctuation break over space break.
            if last_punct_break > 0:
                return last_punct_break
            if last_space_break > 0:
                return last_space_break
            return 0
        cols += ch_cols
        # Update break candidates AFTER counting this char.
        if ch in _CJK_BREAK_AFTER:
            last_punct_break = i + 1
        elif ch == " ":
            # Break AT the space (consumer rstrips/lstrips around).
            last_space_break = i
    # All of s fits.
    return len(s)


def _hard_cut(s: str, budget: int) -> int:
    """Return the largest index such that `s[:idx]` fits in `budget` cols."""
    cols = 0
    for i, ch in enumerate(s):
        ch_cols = 2 if _is_wide(ch) else 1
        if cols + ch_cols > budget:
            return i
        cols += ch_cols
    return len(s)


def _is_wide(ch: str) -> bool:
    import unicodedata
    return unicodedata.east_asian_width(ch) in ("F", "W")


# ------------------------------------------------------------------ inline write

# Match the BEGIN/END auto-rendered block in a proposal body (DOTALL).
_INLINE_BLOCK_RE = re.compile(
    re.escape(RENDER_BEGIN) + r".*?" + re.escape(RENDER_END),
    re.DOTALL,
)


def render_inline(
    proposal_path: Path,
    *,
    plain: bool = False,
    width: int = WRAP_WIDTH,
    wrap: bool = True,
) -> tuple[str, bool]:
    """Render a proposal and write the result into the proposal.md body
    between the `<!-- BEGIN AUTO-RENDERED -->` / `<!-- END AUTO-RENDERED -->`
    markers. Returns ``(rendered_text, wrote)``.

    If the body has no markers, this function appends them at the end of the
    body (so a freshly-scaffolded proposal stays inline-renderable, and a
    legacy proposal that opted into v0.3 schema after the fact is upgraded
    on first render).

    Frontmatter is preserved verbatim; only the body region between markers
    is overwritten.
    """
    text = proposal_path.read_text(encoding="utf-8")
    proposal = load_proposal(text)
    rendered = render(proposal, plain=plain, width=width, wrap=wrap).rstrip()

    # Build the new body block (markers always wrap a fenced text block so the
    # rendered tree is monospaced and reviewers see exact spacing in Obsidian).
    block = (
        f"{RENDER_BEGIN}\n\n"
        f"```text\n"
        f"{rendered}\n"
        f"```\n\n"
        f"{RENDER_END}"
    )

    body = proposal.body or ""
    if _INLINE_BLOCK_RE.search(body):
        new_body = _INLINE_BLOCK_RE.sub(block, body, count=1)
    else:
        # No markers — append to the body so subsequent renders are in-place.
        sep = "\n\n" if body.strip() else ""
        new_body = (body.rstrip() + sep + block + "\n") if body else ("\n" + block + "\n")

    if new_body == body:
        return rendered, False

    proposal.body = new_body
    proposal_path.write_text(dump_proposal(proposal), encoding="utf-8")
    return rendered, True
