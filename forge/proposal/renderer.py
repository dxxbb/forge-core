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

from dataclasses import dataclass
from typing import Iterable

from forge.proposal.schema import (
    DecideOption,
    Disposition,
    Item,
    PropagationBranch,
    PropagationNode,
    Proposal,
    SubItem,
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


# ------------------------------------------------------------------ render

def render(proposal: Proposal, *, plain: bool = False, width: int = 73) -> str:
    """Render the §0.5 view of a Proposal. Returns the full text."""
    glyphs = _PLAIN if plain else _BOX
    out: list[str] = []

    out.append("§0.5 · 监控 item 视图 (per-item · disposition + 传播树)")
    out.append("")
    out.append(
        "**Icon**: ✅ APPLY · ⏭ COVERED · 📦 ARCHIVE · ❓ DECIDE · ➖ N/A · 🔀 MIXED"
    )

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
        out.extend(_render_item(item, glyphs, width=width))
        out.append("")

    # Summary: merged propagation
    merged = _render_merged_propagation(proposal, glyphs)
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
        out.append(f"**一句话总结**: {summary_line}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


# ------------------------------------------------------------------ items


def _render_item(item: Item, glyphs: _Glyphs, *, width: int) -> list[str]:
    out: list[str] = []
    title = f"══ ITEM {item.id} " if glyphs is _BOX else f"== ITEM {item.id} "
    fill = glyphs.h_double * max(2, width - len(title))
    out.append(title + fill)
    monitor_label = "   监控:  "
    out.append(monitor_label + (item.monitor_info or "").splitlines()[0]
               if item.monitor_info else (monitor_label + "(no monitor info)"))
    for line in (item.monitor_info or "").splitlines()[1:]:
        out.append("           " + line)
    out.append(glyphs.h_double * width)
    out.append("")

    if item.disposition == Disposition.MIXED:
        # parent extracted (overview), then disposition note, then sub-items
        if item.extracted:
            out.extend(_field_block("提取信息", item.extracted))
        if item.disposition:
            note = item.disposition_note or _DISP_LABEL[item.disposition]
            out.append(_one_line_field("处理结果", f"{item.disposition.icon} {note}"))
        if item.rationale:
            out.extend(_field_block("理由", item.rationale))
        out.append("")
        # render each sub-item
        # group COVERED & NA sub-items at the tail in compressed list form
        prominent = [s for s in item.sub_items
                     if s.disposition not in (Disposition.COVERED, Disposition.NA)]
        covered = [s for s in item.sub_items if s.disposition == Disposition.COVERED]
        na = [s for s in item.sub_items if s.disposition == Disposition.NA]

        for sub in prominent:
            out.extend(_render_sub_item(sub, item.id, glyphs, width=width))
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
        out.extend(_field_block("提取信息", item.extracted))
    if item.disposition:
        note = item.disposition_note or _DISP_LABEL[item.disposition]
        out.append(_one_line_field("处理结果", f"{item.disposition.icon} {note}"))
    if item.rationale:
        out.extend(_field_block("理由", item.rationale))
    if item.disposition == Disposition.COVERED and item.covered_by:
        out.append(_one_line_field("已覆盖于", item.covered_by))
    if item.disposition == Disposition.NA and item.reason:
        out.append(_one_line_field("原因", item.reason))
    if item.propagation:
        out.append("")
        out.append("  传播链路")
        out.extend(_render_propagation(item.propagation, glyphs, indent="  "))
    if item.disposition == Disposition.DECIDE and item.options:
        out.append("")
        out.append("  传播链路 (多选项, 等用户选)")
        for opt in item.options:
            out.append("")
            out.append(f"  选项 {opt.id} · {opt.description}")
            if opt.propagation:
                out.extend(_render_propagation(opt.propagation, glyphs, indent="  "))
            else:
                out.append(f"  {glyphs.last} (无传播)")
        if item.recommendation:
            out.append("")
            out.append(f"  推荐    {item.recommendation}")
    if item.risk:
        out.append("")
        out.extend(_field_block("风险", item.risk))
    return out


def _render_sub_item(sub: SubItem, parent_id: str, glyphs: _Glyphs, *, width: int) -> list[str]:
    out: list[str] = []
    icon = sub.disposition.icon if sub.disposition else "?"
    label = _DISP_LABEL[sub.disposition] if sub.disposition else "?"
    rule_extra = f" · {sub.rule}" if sub.rule else ""
    note_extra = f" · 提炼为 {sub.rule}" if sub.rule else ""
    title_left = f"  ── ITEM {parent_id} / sub {sub.id} · {icon} {label}{rule_extra} "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    fill = glyphs.h_single * max(2, width - len(title_left))
    out.append(title_left + fill)
    out.append("")
    if sub.extracted:
        out.extend(_field_block("提取信息", sub.extracted))

    if sub.disposition:
        out.append(_one_line_field("处理结果", f"{icon} {label}{note_extra}"))
    if sub.rationale:
        out.extend(_field_block("理由", sub.rationale))

    if sub.disposition == Disposition.COVERED and sub.covered_by:
        out.append(_one_line_field("已覆盖于", sub.covered_by))
    if sub.disposition == Disposition.NA and sub.reason:
        out.append(_one_line_field("原因", sub.reason))

    if sub.propagation:
        out.append("")
        out.append("  传播链路")
        out.extend(_render_propagation(sub.propagation, glyphs, indent="  "))

    if sub.disposition == Disposition.DECIDE and sub.options:
        out.append("")
        out.append("  传播链路 (多选项, 等用户选)")
        for opt in sub.options:
            out.append("")
            out.append(f"  选项 {opt.id} · {opt.description}")
            if opt.propagation:
                out.extend(_render_propagation(opt.propagation, glyphs, indent="  "))
            else:
                out.append(f"  {glyphs.last} (无传播)")
        if sub.recommendation:
            out.append("")
            out.append(f"  推荐    {sub.recommendation}")
    if sub.risk:
        out.append("")
        out.extend(_field_block("风险", sub.risk))
    return out


def _render_covered_table(
    parent_id: str,
    subs: list[SubItem],
    glyphs: _Glyphs,
    *,
    width: int,
) -> list[str]:
    out: list[str] = []
    icon = Disposition.COVERED.icon
    title_left = f"  ── ITEM {parent_id} · {len(subs)} 个 {icon} COVERED (压缩列表) "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    fill = glyphs.h_single * max(2, width - len(title_left))
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
        out.append(f"   {sid:<5} {label:<37} {covered}")
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
    fill = glyphs.h_single * max(2, width - len(title_left))
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
) -> list[str]:
    """Render top-level branches under one item/sub-item. Each branch is a
    `└─ a:` / `└─ b:` block.
    """
    out: list[str] = []
    for branch in branches:
        out.extend(_render_branch(branch, glyphs, indent=indent, depth=0))
    return out


def _render_branch(
    branch: PropagationBranch,
    glyphs: _Glyphs,
    *,
    indent: str,
    depth: int,
) -> list[str]:
    """Render a single propagation branch + its node + its children."""
    out: list[str] = []
    pad = indent + (glyphs.indent * depth)
    label = branch.branch
    node = branch.node
    head = f"{pad}{glyphs.last} {label}: {_node_head(node)}"
    if branch.shared_with:
        head += f"   ({label} 与 {', '.join(f'sub {x}' for x in branch.shared_with)} 共享触发)"
    out.append(head)
    # Modification line:
    if node.modification:
        for i, mline in enumerate(node.modification.splitlines()):
            connector = glyphs.branch if i == 0 else glyphs.v
            out.append(f"{pad}{glyphs.indent}{connector} 修改: {mline}" if i == 0
                       else f"{pad}{glyphs.indent}{glyphs.v}        {mline}")
    # children: render under increasing depth
    for child in node.children:
        out.extend(_render_branch(child, glyphs, indent=indent, depth=depth + 1))
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


def _render_merged_propagation(proposal: Proposal, glyphs: _Glyphs) -> list[str]:
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
        for mline in node.modifications:
            out.append(f"{pad}{glyphs.indent}{glyphs.branch} 修改: {mline}")
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

def _field_block(label: str, value: str) -> list[str]:
    """Render a labelled multi-line field. The label sits at column 2 and
    content at column 14, computed by display width (CJK = 2 cols).
    """
    lines = (value or "").splitlines() or [""]
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    out = [f"  {label}{' ' * pad}{lines[0]}"]
    for line in lines[1:]:
        out.append(f"              {line}")
    return out


def _one_line_field(label: str, value: str) -> str:
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    return f"  {label}{' ' * pad}{value}"


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
