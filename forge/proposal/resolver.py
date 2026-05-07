"""v0.7 propagation-resolver: derive propagation tree from `modified_files`.

The PR-proposal §0.5 view requires a propagation tree per item. v0.6 had the
authoring agent hand-draw this tree (each branch → node → children →
terminal). But the rules are mechanical:

    KB topic file        → reverse-lookup section.upstream → section
                           → runtime view (every config that lists section)
    asset file           → reverse-lookup section.upstream → section
                           → runtime view
    KB index / log       → terminal (KB-internal, doesn't enter sections/runtime)
    raw clipping         → terminal
    sections file itself → directly to runtime (config-driven)
    other / unmatched    → terminal (with a warn)

The resolver runs against:
  - sections directory (`context build/sections/`) — each `.md` file may carry
    `upstream: [...]` in YAML frontmatter.
  - configs directory (`context build/config/`) — each `.md` file lists
    `target` + `sections: [...]`.

Author opt-in: populate ``Item.modified_files`` (list of file paths the change
touches). Optional inputs:
  - ``modifications`` mapping ``path → modification text`` — used as the
    leaf-node modification line in the resolved tree.
  - ``propagation_hints`` mapping ``path → "terminal" | "light" | "full"`` —
    overrides the default reverse-lookup. ``terminal``/``light`` produce a
    single terminal node; ``light`` adds a label noting it's a light update.

Resolved trees are written back into ``Item.propagation`` (overwriting only
when ``propagation`` was empty).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import yaml

from forge.proposal.schema import (
    Item,
    Proposal,
    PropagationBranch,
    PropagationNode,
    SubItem,
)


# ----------------------------------------------------------------------------
# Inputs: section / config indices
# ----------------------------------------------------------------------------


@dataclass
class SectionEntry:
    """One section file's reverse-lookup metadata."""

    name: str            # section name (from frontmatter `name` or filename stem)
    path: str            # path under workspace root (forward slashes)
    upstream: list[str] = field(default_factory=list)  # raw upstream patterns


@dataclass
class ConfigEntry:
    """One config file's target binding + section list."""

    name: str
    target: str
    sections: list[str] = field(default_factory=list)
    path: str = ""


@dataclass
class WorkspaceIndex:
    """Reverse-lookup index loaded once per workspace.

    `sections_by_name` — section name → SectionEntry
    `sections` — list of all SectionEntry (preserve order for deterministic output)
    `configs` — list of ConfigEntry
    """

    sections: list[SectionEntry] = field(default_factory=list)
    sections_by_name: dict[str, SectionEntry] = field(default_factory=dict)
    configs: list[ConfigEntry] = field(default_factory=list)
    sections_dir: Path | None = None
    configs_dir: Path | None = None
    workspace_root: Path | None = None


# ----------------------------------------------------------------------------
# Loaders
# ----------------------------------------------------------------------------


def _read_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    lines = text.split("\n")
    if len(lines) < 2:
        return {}
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_text = "\n".join(lines[1:i])
            try:
                fm = yaml.safe_load(fm_text) or {}
            except yaml.YAMLError:
                return {}
            if not isinstance(fm, dict):
                return {}
            return fm
    return {}


def _rel_posix(p: Path, root: Path | None) -> str:
    if root is None:
        return p.as_posix()
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def load_sections(sections_dir: Path, workspace_root: Path | None = None) -> list[SectionEntry]:
    """Scan a sections directory for ``.md`` files and parse upstream metadata.

    Order is alphabetical by filename to keep output deterministic.
    """
    out: list[SectionEntry] = []
    if not sections_dir.is_dir():
        return out
    for md in sorted(sections_dir.glob("*.md")):
        try:
            fm = _read_frontmatter(md.read_text(encoding="utf-8"))
        except OSError:
            continue
        name = str(fm.get("name") or md.stem)
        upstream_raw = fm.get("upstream") or []
        if isinstance(upstream_raw, str):
            upstream_raw = [upstream_raw]
        if not isinstance(upstream_raw, list):
            upstream_raw = []
        upstream = [str(u).strip() for u in upstream_raw if str(u).strip()]
        out.append(SectionEntry(
            name=name,
            path=_rel_posix(md, workspace_root),
            upstream=upstream,
        ))
    return out


def load_configs(configs_dir: Path, workspace_root: Path | None = None) -> list[ConfigEntry]:
    """Scan a configs directory for ``.md`` files and parse target/sections."""
    out: list[ConfigEntry] = []
    if not configs_dir.is_dir():
        return out
    for md in sorted(configs_dir.glob("*.md")):
        try:
            fm = _read_frontmatter(md.read_text(encoding="utf-8"))
        except OSError:
            continue
        name = str(fm.get("name") or md.stem)
        target = str(fm.get("target") or "")
        sections_raw = fm.get("sections") or []
        if not isinstance(sections_raw, list):
            sections_raw = []
        sections = [str(s).strip() for s in sections_raw if str(s).strip()]
        if not target:
            continue
        out.append(ConfigEntry(
            name=name,
            target=target,
            sections=sections,
            path=_rel_posix(md, workspace_root),
        ))
    return out


def load_workspace_index(
    workspace_root: Path,
    sections_dir: Path | None = None,
    configs_dir: Path | None = None,
) -> WorkspaceIndex:
    """Convenience: load sections + configs from a personalOS-style workspace.

    Default layout: `<root>/context build/sections/` and `<root>/context build/config/`.
    Pass explicit ``sections_dir`` / ``configs_dir`` to override.
    """
    if sections_dir is None:
        sections_dir = workspace_root / "context build" / "sections"
    if configs_dir is None:
        configs_dir = workspace_root / "context build" / "config"
    sections = load_sections(sections_dir, workspace_root)
    configs = load_configs(configs_dir, workspace_root)
    return WorkspaceIndex(
        sections=sections,
        sections_by_name={s.name: s for s in sections},
        configs=configs,
        sections_dir=sections_dir,
        configs_dir=configs_dir,
        workspace_root=workspace_root,
    )


# ----------------------------------------------------------------------------
# Path classification
# ----------------------------------------------------------------------------


def _normalize(p: str) -> str:
    """Normalize a path for matching: strip leading `./`, ensure forward slashes."""
    s = (p or "").strip()
    if s.startswith("./"):
        s = s[2:]
    return s.replace("\\", "/")


def _path_matches_upstream(path: str, upstream_pattern: str) -> bool:
    """Decide whether `path` falls under `upstream_pattern`.

    Rules:
      - Trailing `/` (or pure-directory pattern) → directory prefix match.
        e.g. `public knowledge base/topic/` matches everything under topic/.
      - Otherwise: exact match.

    Patterns may also be glob-flavoured (`*`, `**`); we keep matching simple by
    treating those as directory prefix once a `/` precedes the wildcard. The
    common authoring forms in personalOS are:
        public knowledge base/topic/
        assist config/work preference/working-style.md
        capture/web clipping/
    """
    p = _normalize(path)
    pat = _normalize(upstream_pattern)
    if not pat:
        return False

    # exact file match
    if p == pat:
        return True

    # directory pattern (trailing slash or no extension)
    if pat.endswith("/"):
        return p.startswith(pat)

    # If pattern doesn't end in slash but is clearly a directory (no `.` in
    # the basename after the last slash), accept directory-prefix match.
    last_seg = pat.rsplit("/", 1)[-1]
    if "." not in last_seg:
        return p == pat or p.startswith(pat + "/")

    return False


@dataclass
class PathClassification:
    """Result of classifying a single modified-file path.

    `kind` is one of:
      - "section_upstream" — file is upstream of one or more sections; the
        resolver should emit a section → runtime sub-tree.
      - "section"          — file IS a section file under sections_dir; emit
        runtime sub-tree directly (no parent section node).
      - "config"           — file IS a config file; runtime nodes only.
      - "terminal"         — KB index / log / capture / unmatched; emit a
        single terminal node.
      - "light"            — explicit `light` hint; same as terminal but
        labelled "light update, no downstream".
    """

    kind: str
    matched_sections: list[SectionEntry] = field(default_factory=list)
    note: str = ""


def classify_path(path: str, index: WorkspaceIndex, hint: str = "") -> PathClassification:
    """Decide what kind of propagation a modified-file path should produce.

    Hint values: "" (default — auto), "terminal", "light", "full" (= auto).
    """
    p = _normalize(path)
    h = (hint or "").strip().lower()

    if h == "terminal":
        return PathClassification(kind="terminal", note="hint=terminal")
    if h == "light":
        return PathClassification(kind="light", note="hint=light")

    # Sections file itself? The path should be inside the sections_dir
    # (relative-posix form).
    if index.sections_dir is not None:
        sec_prefix = _rel_posix(index.sections_dir, index.workspace_root)
        if sec_prefix and (p == sec_prefix or p.startswith(sec_prefix.rstrip("/") + "/")):
            return PathClassification(kind="section")

    # Config file itself?
    if index.configs_dir is not None:
        cfg_prefix = _rel_posix(index.configs_dir, index.workspace_root)
        if cfg_prefix and (p == cfg_prefix or p.startswith(cfg_prefix.rstrip("/") + "/")):
            return PathClassification(kind="config")

    # Reverse-lookup section.upstream
    matches: list[SectionEntry] = []
    for sec in index.sections:
        for pat in sec.upstream:
            if _path_matches_upstream(p, pat):
                matches.append(sec)
                break
    if matches:
        return PathClassification(kind="section_upstream", matched_sections=matches)

    return PathClassification(
        kind="terminal",
        note="not in any section.upstream — treated as terminal",
    )


# ----------------------------------------------------------------------------
# Tree builders
# ----------------------------------------------------------------------------


# Synthetic modification text used for auto-resolved internal nodes (section /
# runtime). The validator demands a `modification` line on non-terminal APPLY
# nodes; rather than leaving these blank we annotate them so the §0.5 view
# explicitly says "auto-recompiled" and reviewers can tell mechanical edges
# from author-written ones.
_AUTO_MOD_SECTION = "auto-recompiled (section.upstream changed)"
_AUTO_MOD_RUNTIME_FMT = "auto-recompiled by `forge build` (target: {target})"


def _runtime_terminal_branches(
    section_name: str, index: WorkspaceIndex, parent_label: str = ""
) -> list[PropagationBranch]:
    """For a section, emit one terminal branch per runtime config that lists it."""
    branches: list[PropagationBranch] = []
    for cfg in index.configs:
        if section_name in cfg.sections:
            label = f"runtime · {cfg.target}"
            node = PropagationNode(
                path=cfg.path,
                label=label,
                modification=_AUTO_MOD_RUNTIME_FMT.format(target=cfg.target),
                terminal=True,
            )
            branches.append(PropagationBranch(branch="rt", node=node))
    return branches


def _section_node_with_runtime(
    section: SectionEntry, index: WorkspaceIndex, modification: str = ""
) -> PropagationNode:
    """Build a section node populated with runtime children."""
    runtime = _runtime_terminal_branches(section.name, index)
    if not runtime:
        # No runtime targets reference this section — treat section as
        # terminal so the tree still renders without a dangling middle node.
        return PropagationNode(
            path=section.path,
            label="section (no downstream runtime)",
            modification=modification or _AUTO_MOD_SECTION,
            terminal=True,
        )
    return PropagationNode(
        path=section.path,
        label="section",
        modification=modification or _AUTO_MOD_SECTION,
        children=runtime,
    )


def _build_branch_for_path(
    path: str,
    index: WorkspaceIndex,
    *,
    branch_label: str,
    modification: str,
    hint: str,
    warnings: list[str],
) -> list[PropagationBranch]:
    """Build the propagation branch(es) for a single modified-file path.

    Returns a list (length 1 in nearly every case; >1 when a single path
    fans out to multiple unrelated sections — each gets its own branch).
    """
    cls = classify_path(path, index, hint=hint)

    if cls.kind == "terminal":
        if cls.note:
            warnings.append(f"{path}: {cls.note}")
        node = PropagationNode(
            path=path,
            modification=modification,
            terminal=True,
        )
        return [PropagationBranch(branch=branch_label, node=node)]

    if cls.kind == "light":
        node = PropagationNode(
            path=path,
            label="light update, no downstream",
            modification=modification,
            terminal=True,
        )
        return [PropagationBranch(branch=branch_label, node=node)]

    if cls.kind == "section":
        # The path IS a section file. Look up which section by path match.
        section = next(
            (s for s in index.sections if s.path == _normalize(path)),
            None,
        )
        if section is None:
            # File is in sections_dir but isn't loaded (e.g. parse error) —
            # fall back to terminal.
            warnings.append(f"{path}: under sections dir but not parseable; terminal")
            return [PropagationBranch(
                branch=branch_label,
                node=PropagationNode(path=path, modification=modification, terminal=True),
            )]
        runtime = _runtime_terminal_branches(section.name, index)
        if not runtime:
            return [PropagationBranch(
                branch=branch_label,
                node=PropagationNode(
                    path=path,
                    label="section (no downstream runtime)",
                    modification=modification,
                    terminal=True,
                ),
            )]
        return [PropagationBranch(
            branch=branch_label,
            node=PropagationNode(
                path=path,
                label="section",
                modification=modification or _AUTO_MOD_SECTION,
                children=runtime,
            ),
        )]

    if cls.kind == "config":
        return [PropagationBranch(
            branch=branch_label,
            node=PropagationNode(
                path=path,
                label="config (recompiles affected runtime)",
                modification=modification,
                terminal=True,
            ),
        )]

    # section_upstream: emit asset → section → runtime per matched section.
    if cls.kind == "section_upstream":
        # Single asset path may map to multiple sections — fan out.
        section_branches: list[PropagationBranch] = []
        for sec in cls.matched_sections:
            section_branches.append(PropagationBranch(
                branch="sec",
                node=_section_node_with_runtime(sec, index),
            ))
        asset_node = PropagationNode(
            path=path,
            label="asset",
            modification=modification,
            children=section_branches,
        )
        return [PropagationBranch(branch=branch_label, node=asset_node)]

    # Unknown kind (defensive)
    warnings.append(f"{path}: unknown classification kind `{cls.kind}`; terminal")
    return [PropagationBranch(
        branch=branch_label,
        node=PropagationNode(path=path, modification=modification, terminal=True),
    )]


# ----------------------------------------------------------------------------
# Top-level resolve
# ----------------------------------------------------------------------------


_BRANCH_LABELS = "abcdefghijklmnopqrstuvwxyz"


def resolve_owner(
    owner: Item | SubItem,
    index: WorkspaceIndex,
) -> "ResolveResult":
    """Resolve `owner.modified_files` into `owner.propagation`.

    Returns a ResolveResult with status (`resolved` / `skipped_existing` /
    `skipped_no_files`) plus warnings.

    Mutates `owner.propagation` only when status is `resolved`.
    """
    warnings: list[str] = []

    if not owner.modified_files:
        return ResolveResult(status="skipped_no_files", warnings=warnings)

    if owner.propagation:
        return ResolveResult(
            status="skipped_existing",
            warnings=[
                "propagation already filled by author; resolver skipped",
            ],
        )

    # Group: all modified files go under top-level branches a, b, c... in the
    # order they appear. Same-section files share their section node so the
    # rendered tree dedupes (asset_a + asset_b → section X → runtime).
    section_groups: dict[str, list[tuple[str, str]]] = {}  # section_name → [(path, mod)]
    other_branches: list[PropagationBranch] = []

    label_idx = 0
    used_labels: set[str] = set()

    def next_label() -> str:
        nonlocal label_idx
        while label_idx < len(_BRANCH_LABELS):
            ch = _BRANCH_LABELS[label_idx]
            label_idx += 1
            if ch not in used_labels:
                used_labels.add(ch)
                return ch
        # fallback
        return f"x{label_idx}"

    # First pass: classify and group.
    section_order: list[str] = []
    section_meta: dict[str, SectionEntry] = {}
    for path in owner.modified_files:
        norm = _normalize(path)
        modification = owner.modifications.get(path) or owner.modifications.get(norm) or ""
        hint = owner.propagation_hints.get(path) or owner.propagation_hints.get(norm) or ""
        cls = classify_path(norm, index, hint=hint)
        if cls.kind == "section_upstream" and len(cls.matched_sections) == 1:
            sec = cls.matched_sections[0]
            if sec.name not in section_groups:
                section_groups[sec.name] = []
                section_order.append(sec.name)
                section_meta[sec.name] = sec
            section_groups[sec.name].append((path, modification))
        else:
            for br in _build_branch_for_path(
                path, index,
                branch_label=next_label(),
                modification=modification,
                hint=hint,
                warnings=warnings,
            ):
                other_branches.append(br)

    # Second pass: emit grouped section branches. When one section is targeted
    # by multiple files, render each file as its own asset branch but reuse a
    # SHARED `section` subtree (via _section_node_with_runtime invoked once,
    # then re-used by reference).
    grouped_branches: list[PropagationBranch] = []
    for sec_name in section_order:
        sec = section_meta[sec_name]
        files = section_groups[sec_name]
        # Build the section subtree once.
        runtime_children = _runtime_terminal_branches(sec.name, index)
        section_node = PropagationNode(
            path=sec.path,
            label="section" if runtime_children else "section (no downstream runtime)",
            modification=_AUTO_MOD_SECTION,
            children=runtime_children,
            terminal=not runtime_children,
        )
        if len(files) == 1:
            path, modification = files[0]
            asset_node = PropagationNode(
                path=path,
                label="asset",
                modification=modification,
                children=[PropagationBranch(branch="sec", node=section_node)],
            )
            grouped_branches.append(PropagationBranch(
                branch=next_label(), node=asset_node,
            ))
            continue
        # Multiple files share the section: emit a parent group node whose
        # children are each asset, all of which then re-target the same
        # section subtree. This matches the §0.5 convention: one logical
        # branch label, multiple `修改: ` entries listed under it before a
        # single shared section/runtime tail.
        group_label = next_label()
        # Use first file as the "head" of the group; subsequent files become
        # additional ├─ entries under the same shared section.
        children_branches: list[PropagationBranch] = []
        for j, (path, modification) in enumerate(files):
            asset_node = PropagationNode(
                path=path,
                label="asset",
                modification=modification,
                children=([PropagationBranch(branch="sec", node=section_node)]
                          if j == len(files) - 1 else []),
                terminal=False,
            )
            children_branches.append(PropagationBranch(
                branch=f"{group_label}{j+1}", node=asset_node,
            ))
        # Container node groups the assets under one labelled branch. We
        # synthesize a modification line on the container so the validator's
        # "non-terminal APPLY needs modification" rule is satisfied — the
        # individual file modifications stay on their respective asset
        # children.
        file_list = ", ".join(Path(f).name for f, _ in files)
        container = PropagationNode(
            path="",
            label=f"{len(files)} assets → {sec.name}",
            modification=f"批量改动: {file_list}",
            children=children_branches,
        )
        grouped_branches.append(PropagationBranch(
            branch=group_label, node=container,
        ))

    new_propagation = grouped_branches + other_branches
    owner.propagation = new_propagation
    return ResolveResult(status="resolved", warnings=warnings)


@dataclass
class ResolveResult:
    """Outcome of `resolve_owner` for a single Item/SubItem."""
    status: str           # "resolved" | "skipped_existing" | "skipped_no_files"
    warnings: list[str] = field(default_factory=list)


@dataclass
class ResolveReport:
    """Outcome of `resolve_proposal` across all items/sub-items."""
    resolved: int = 0
    skipped_existing: int = 0
    skipped_no_files: int = 0
    warnings: list[str] = field(default_factory=list)
    per_owner: list[tuple[str, ResolveResult]] = field(default_factory=list)


def resolve_proposal(
    proposal: Proposal,
    index: WorkspaceIndex,
) -> ResolveReport:
    """Walk every Item / SubItem and resolve its modified_files → propagation.

    Mutates the proposal in place. Returns a ResolveReport summarising what
    happened (counts + warnings).
    """
    report = ResolveReport()
    for item in proposal.items:
        # MIXED items defer to their sub_items (no item-level propagation in
        # MIXED is the v0.6 convention). We still run resolve at the item
        # level so non-MIXED items work normally.
        if item.sub_items:
            for sub in item.sub_items:
                res = resolve_owner(sub, index)
                report.per_owner.append((f"items[{item.id}].sub_items[{sub.id}]", res))
                _accumulate(report, res)
            continue
        res = resolve_owner(item, index)
        report.per_owner.append((f"items[{item.id}]", res))
        _accumulate(report, res)
    return report


def _accumulate(report: ResolveReport, res: ResolveResult) -> None:
    if res.status == "resolved":
        report.resolved += 1
    elif res.status == "skipped_existing":
        report.skipped_existing += 1
    else:
        report.skipped_no_files += 1
    for w in res.warnings:
        if w not in report.warnings:
            report.warnings.append(w)
