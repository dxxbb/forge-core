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
            out.extend(_field_block("提取信息", item.extracted, tree=True))
        if item.disposition:
            out.append(_one_line_field("处理结果", _disposition_title(item)))
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
        out.extend(_field_block("提取信息", item.extracted, tree=True))
    if item.disposition:
        out.append(_one_line_field("处理结果", _disposition_title(item)))
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
    title_left = f"  ── ITEM {parent_id} / sub {sub.id} · {icon} {label}{rule_extra} "
    if glyphs is _PLAIN:
        title_left = title_left.replace("──", "--")
    fill = glyphs.h_single * max(2, width - len(title_left))
    out.append(title_left + fill)
    out.append("")
    if sub.extracted:
        out.extend(_field_block("提取信息", sub.extracted, tree=True))

    if sub.disposition:
        out.append(_one_line_field("处理结果", _disposition_title(sub)))
    if sub.rationale:
        out.extend(_field_block("理由", sub.rationale))

    if sub.disposition == Disposition.COVERED and sub.covered_by:
        out.append(_one_line_field("已覆盖于", sub.covered_by))
    if sub.disposition == Disposition.NA and sub.reason:
        out.append(_one_line_field("原因", sub.reason))

    if sub.propagation:
        out.append("")
        out.append("  传播链路")
        out.extend(_render_propagation(sub.propagation, glyphs, indent="  ",
                                          owner_id=sub.id))

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
    owner_id: str = "",
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
                                   owner_id=owner_id))
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
    # Modification line:
    if node.modification:
        for i, mline in enumerate(node.modification.splitlines()):
            connector = glyphs.branch if i == 0 else glyphs.v
            out.append(f"{pad}{glyphs.indent}{connector} 修改: {mline}" if i == 0
                       else f"{pad}{glyphs.indent}{glyphs.v}        {mline}")
    # children: render under increasing depth (carry owner_id through so nested
    # `b → c` shared_with treatments stay consistent)
    for child in node.children:
        out.extend(_render_branch(child, glyphs, indent=indent, depth=depth + 1,
                                   owner_id=owner_id))
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

def _field_block(label: str, value: str, *, tree: bool = False) -> list[str]:
    """Render a labelled multi-line field. The label sits at column 2 and
    content at column 14, computed by display width (CJK = 2 cols).

    When `tree=True` and value has multiple lines, continuation lines are
    rendered with `├─` / `└─` prefixes (last line uses `└─`). The first
    line is unprefixed (it sits next to the label).
    """
    lines = (value or "").splitlines() or [""]
    label_cols = _display_width(label)
    pad = max(1, 12 - label_cols)
    out = [f"  {label}{' ' * pad}{lines[0]}"]
    n = len(lines)
    for i, line in enumerate(lines[1:], start=1):
        if tree and n > 1:
            connector = "└─" if i == n - 1 else "├─"
            # strip any leading spaces that the source string used for visual
            # nesting — we want a clean tree prefix.
            stripped = line.lstrip(" ")
            extra = line[: len(line) - len(stripped)]
            out.append(f"            {connector} {extra}{stripped}")
        else:
            out.append(f"              {line}")
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


# ------------------------------------------------------------------ inline write

# Match the BEGIN/END auto-rendered block in a proposal body (DOTALL).
_INLINE_BLOCK_RE = re.compile(
    re.escape(RENDER_BEGIN) + r".*?" + re.escape(RENDER_END),
    re.DOTALL,
)


def render_inline(proposal_path: Path, *, plain: bool = False, width: int = 73) -> tuple[str, bool]:
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
    rendered = render(proposal, plain=plain, width=width).rstrip()

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
