"""Build an audit graph for section-to-runtime context compilation.

The graph is intentionally conservative:

- section -> runtime ranges are compiler-derived and may be marked exact
- source -> section relations are only as strong as section frontmatter records
- missing or ambiguous evidence is represented as uncertain, not inferred away
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

from forge.compiler.config import Config
from forge.patch import anchored_block
from forge.compiler.loader import load_all_configs, load_sections
from forge.compiler.renderer import _apply_section_view, render
from forge.compiler.section import Section
from forge.layout import detect
from forge.targets import get_adapter
from forge.targets.agents_md import _heading as agents_heading
from forge.targets.claude_code import _demote_headings, _section_heading


@dataclass
class FilePosition:
    path: str
    start_line: int | None = None
    end_line: int | None = None
    exists: bool = False


@dataclass
class SourceNode:
    id: str
    label: str
    kind: str
    pointer: str
    position: FilePosition | None
    status: str
    content_excerpt: str | None = None
    layer: str = "core"
    excerpt_truncated: bool = False
    zone: str = "state"  # rule | state (AC-PORTAL-1)
    certified: str | None = None
    uncertified_changes: int = 0


@dataclass
class SectionNode:
    id: str
    name: str
    type: str | None
    kind: str | None
    position: FilePosition | None
    content: str
    source_pointers: list[str] = field(default_factory=list)
    relation_state: str = "uncertain"
    relation_note: str = ""
    layer: str = "core"


@dataclass
class RuntimeNode:
    id: str
    config: str
    target: str
    path: str
    position: FilePosition
    content: str
    mirrors: list[FilePosition] = field(default_factory=list)


@dataclass
class ExtractionAudit:
    """How a source's text became a section's text, computed honestly.

    There is no derive record in the data, so this is a conservative textual
    comparison — verbatim / partial hits are evidence, everything else is
    explicitly labelled paraphrase, never inferred as exact.
    """

    kind: str  # verbatim | partial | sparse | paraphrase | unknown
    detail: str
    hit_lines: int = 0
    total_lines: int = 0
    truncated: bool = False


@dataclass
class AuditEdge:
    id: str
    from_id: str
    to_id: str
    relation: str
    status: str
    evidence: str
    confidence: str
    runtime_range: FilePosition | None = None
    extraction: ExtractionAudit | None = None


@dataclass
class ExternalNode:
    """An external input that was *imported* into a canonical source.

    e.g. a coding agent's memory/history (Codex, Claude) or a web clipping.
    These sit upstream of canonical sources: forge ingests them through the
    review-gated capture -> import pipeline, and the capture file records the
    origin in its ``source:`` frontmatter.
    """

    id: str
    label: str
    kind: str  # external
    file_count: int = 0
    status: str = "imported"  # imported | pending


@dataclass
class WorkbenchLink:
    """A workbench item field resolved to a graph node it references."""

    field: str
    node_id: str
    label: str


@dataclass
class WorkbenchEvidence:
    """The actual imported-corpus text an item's source_evidence points at.

    The reviewer judges the agent's interpretation against this excerpt, not
    against the agent's own restatement. ``found=False`` means the anchor could
    not be located — the excerpt then falls back to the file head and says so.
    """

    path: str
    anchor: str
    found: bool
    start_line: int | None
    excerpt: str
    note: str = ""


@dataclass
class WorkbenchSinkAudit:
    """Existence check + current-state excerpt for a claimed canonical sink.

    Lets the reviewer verify the agent's ``canonical_sink_status`` claim
    (missing / stale / partial) against the disk instead of trusting it.
    """

    path: str
    exists: bool
    excerpt: str = ""


@dataclass
class WorkbenchPatchAudit:
    """A diffable change proposal: target file, anchor block, replacement text.

    Built from the ``proposed_patch_*`` contract fields. ``current_text`` is the
    block the anchor locates today, so the portal can render before → after.
    Modes: replace (anchor found), append (no anchor), create (target missing),
    unlocated (anchor given but not found — shown one-sided, never guessed).
    """

    target: str
    anchor: str
    mode: str
    target_exists: bool
    anchor_found: bool
    start_line: int | None
    current_text: str
    proposed_text: str
    note: str = ""


@dataclass
class WorkbenchItemAudit:
    id: str
    title: str
    batch: str
    status: str
    initial_domain: str = ""
    fields: dict[str, str] = field(default_factory=dict)
    links: list[WorkbenchLink] = field(default_factory=list)
    evidence: list[WorkbenchEvidence] = field(default_factory=list)
    sinks: list[WorkbenchSinkAudit] = field(default_factory=list)
    patch: WorkbenchPatchAudit | None = None


@dataclass
class WorkbenchAudit:
    id: str
    path: str
    status: str
    current_batch: str | None
    final_pr_ready: bool
    inbox_sources: list[str] = field(default_factory=list)
    capture_sources: list[str] = field(default_factory=list)
    items: list[WorkbenchItemAudit] = field(default_factory=list)


@dataclass
class AuditGraph:
    schema_version: str
    workspace_root: str
    layout: str
    sources: list[SourceNode]
    sections: list[SectionNode]
    runtimes: list[RuntimeNode]
    edges: list[AuditEdge]
    unexplained: list[dict[str, Any]]
    gaps: list[dict[str, Any]] = field(default_factory=list)
    externals: list[ExternalNode] = field(default_factory=list)
    workbenches: list[WorkbenchAudit] = field(default_factory=list)
    ask_items: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_audit_graph(root: Path) -> AuditGraph:
    """Build a read-only audit graph for the workspace at ``root``."""
    root = Path(root).resolve()
    layout = detect(root)
    sections = load_sections(root)
    configs = load_all_configs(root)

    source_nodes_by_pointer: dict[str, SourceNode] = {}
    section_nodes: list[SectionNode] = []
    runtime_nodes: list[RuntimeNode] = []
    edges: list[AuditEdge] = []
    unexplained: list[dict[str, Any]] = []

    for section in sections.values():
        pointers = _section_pointers(section)
        relation_state, relation_note = _section_relation_state(section, pointers)
        snode = SectionNode(
            id=_section_id(section.name),
            name=section.name,
            type=section.type,
            kind=section.kind,
            position=_section_position(root, section),
            content=section.body,
            source_pointers=pointers,
            relation_state=relation_state,
            relation_note=relation_note,
            layer=_section_layer(root, section, pointers),
        )
        section_nodes.append(snode)
        if not pointers and section.type != "wrapper":
            unexplained.append(
                {
                    "type": "missing_source_relation",
                    "section": section.name,
                    "message": "section has no source/upstream pointer in frontmatter",
                }
            )
        for pointer in pointers:
            source = source_nodes_by_pointer.setdefault(
                pointer, _source_node(root, pointer)
            )
            if source.status == "missing":
                unexplained.append(
                    {
                        "type": "unresolved_source_pointer",
                        "section": section.name,
                        "source": pointer,
                        "message": "declared source pointer does not resolve on disk",
                    }
                )
            edges.append(
                AuditEdge(
                    id=_edge_id(source.id, snode.id, "source-section"),
                    from_id=source.id,
                    to_id=snode.id,
                    relation="source_to_section",
                    status=relation_state,
                    evidence=relation_note,
                    confidence="agent-declared" if relation_state != "uncertain" else "uncertain",
                    extraction=_classify_extraction(source, section.body),
                )
            )

    for config in configs.values():
        adapter = get_adapter(config.target)
        runtime_text = render(sections, config)
        runtime_path = layout.runtime_dir / (
            adapter.name if layout.runtime_nested_by_target else ""
        ) / adapter.filename(config)
        rnode = RuntimeNode(
            id=_runtime_id(config.name),
            config=config.name,
            target=config.target,
            path=_display_path(root, runtime_path),
            position=FilePosition(
                path=_display_path(root, runtime_path),
                start_line=1,
                end_line=_line_count(runtime_text),
                exists=runtime_path.exists(),
            ),
            content=runtime_text,
            mirrors=_runtime_mirrors(root, runtime_path, runtime_text),
        )
        runtime_nodes.append(rnode)

        mappings = _compile_mappings(sections, config, runtime_text)
        for section_name in config.sections:
            mapped = mappings.get(section_name)
            status = "exact" if mapped else "uncertain"
            evidence = (
                "compiler-rendered section block matched runtime text"
                if mapped
                else "could not locate compiler-rendered section block in runtime text"
            )
            if not mapped:
                unexplained.append(
                    {
                        "type": "missing_compile_mapping",
                        "config": config.name,
                        "section": section_name,
                        "message": evidence,
                    }
                )
            edges.append(
                AuditEdge(
                    id=_edge_id(_section_id(section_name), rnode.id, "section-runtime"),
                    from_id=_section_id(section_name),
                    to_id=rnode.id,
                    relation="section_to_runtime",
                    status=status,
                    evidence=evidence,
                    confidence="compiler-exact" if mapped else "uncertain",
                    runtime_range=FilePosition(
                        path=rnode.path,
                        start_line=mapped[0] if mapped else None,
                        end_line=mapped[1] if mapped else None,
                        exists=runtime_path.exists(),
                    ),
                )
            )

    # External inputs: things imported INTO canonical sources (agent memory /
    # history, web clippings). The capture file records its origin in
    # `source:`/`origin:` frontmatter; we surface those as upstream nodes.
    externals_by_label: dict[str, ExternalNode] = {}
    for source in source_nodes_by_pointer.values():
        if source.kind not in ("capture", "memory"):
            continue
        for origin in _import_origins(root, source):
            ext = externals_by_label.get(origin)
            if ext is None:
                ext = ExternalNode(
                    id="external:" + hashlib.sha1(origin.encode("utf-8")).hexdigest()[:16],
                    label=origin,
                    kind="external",
                )
                externals_by_label[origin] = ext
            ext.file_count += 1
            edges.append(
                AuditEdge(
                    id=_edge_id(ext.id, source.id, "import"),
                    from_id=ext.id,
                    to_id=source.id,
                    relation="external_to_source",
                    status="imported",
                    evidence=f"capture frontmatter records source: {origin}",
                    confidence="capture-declared",
                )
            )

    sorted_sources = sorted(source_nodes_by_pointer.values(), key=lambda n: n.pointer)
    sorted_sections = sorted(section_nodes, key=lambda n: n.name)
    _annotate_zones(root, sorted_sources)
    # Workbench parsing can append unexplained entries, so it runs before the
    # gap synthesis that turns unexplained + relation states into stable gaps.
    workbenches = _workbench_audits(root, sorted_sources, sorted_sections, runtime_nodes, unexplained)
    ask_items = _run_ask_items(root)
    return AuditGraph(
        schema_version="forge.audit.v1",
        workspace_root=str(root),
        layout=layout.name,
        sources=sorted_sources,
        sections=sorted_sections,
        runtimes=runtime_nodes,
        edges=edges,
        unexplained=unexplained,
        gaps=_gap_audits(sorted_sections, unexplained),
        externals=sorted(externals_by_label.values(), key=lambda n: n.label),
        workbenches=workbenches,
        ask_items=ask_items,
    )


def _annotate_zones(root: Path, sources: list[SourceNode]) -> None:
    """Zone + certification freshness per source (AC-PORTAL-1). Read-only."""
    from forge.zone import certified_info, load_zones, uncertified_diff

    zones = load_zones(root)
    if not zones.exists:
        return
    for source in sources:
        relpath = source.position.path if source.position else source.pointer
        source.zone = zones.zone_for(relpath)
        if source.zone == "rule" or not (root / relpath).is_file():
            continue
        info = certified_info(root, relpath)
        if info is None:
            continue
        source.certified = info.date
        try:
            source.uncertified_changes = len(uncertified_diff(root, relpath))
        except (OSError, UnicodeDecodeError):
            source.uncertified_changes = 0


def _run_ask_items(root: Path) -> list[dict[str, Any]]:
    """Pending ask items, embedded read-only (AC-PORTAL-2)."""
    from forge.run import list_ask_items

    try:
        items = list_ask_items(root)
    except Exception:  # noqa: BLE001 — the portal never breaks on run state
        return []
    return [
        {"id": i.id, "type": i.type, "title": i.title, "detail": i.detail}
        for i in items
    ]


# Extraction classification: a conservative, data-side answer to "how did the
# source's text become the section's text". Computed at build time so it is
# testable and consumable by agents, not synthesized per-hover in the UI.
def _classify_extraction(source: SourceNode, section_body: str) -> ExtractionAudit:
    from_text = source.content_excerpt or ""
    to_text = section_body or ""
    truncated = source.excerpt_truncated
    if not from_text.strip() or not to_text.strip():
        return ExtractionAudit(kind="unknown", detail="缺一侧文本，无法比对", truncated=truncated)
    nf = _collapse_ws(from_text)
    nt = _collapse_ws(to_text)
    lines = [ln.strip() for ln in to_text.split("\n")]
    lines = [ln for ln in lines if len(ln) > 4]
    if nt and nt in nf:
        return ExtractionAudit(
            kind="verbatim",
            detail="section 文本在 source 中逐字出现",
            hit_lines=len(lines),
            total_lines=len(lines),
            truncated=truncated,
        )
    hits = sum(1 for ln in lines if _collapse_ws(ln) in nf)
    if lines and hits / len(lines) >= 0.5:
        kind = "partial"
        detail = f"{hits}/{len(lines)} 行在 source 中可逐字定位"
    elif hits > 0:
        kind = "sparse"
        detail = f"仅 {hits} 行可逐字定位，其余为转写"
    else:
        kind = "paraphrase"
        detail = "section 文本未在 source 中逐字出现（声明级关系，无精确 derive record）"
    if truncated:
        detail += "；source 摘录已截断，逐字命中可能被低估"
    return ExtractionAudit(
        kind=kind, detail=detail, hit_lines=hits, total_lines=len(lines), truncated=truncated
    )


def _collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# Gap synthesis: the deduped, severity-ranked review queue. Lives in the data
# (stable ids) so gaps can be referenced from proposals / approve logs and
# consumed by agents, instead of being renumbered per page load in the portal.
_GAP_HIGH_TYPES = {
    "missing_source_relation",
    "unresolved_source_pointer",
    "missing_compile_mapping",
}
_GAP_SEVERITY_RANK = {"high": 0, "med": 1, "low": 2}


def _gap_audits(
    sections: list[SectionNode], unexplained: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    flagged = {u.get("section") for u in unexplained if u.get("section")}
    for u in unexplained:
        severity = "high" if u.get("type") in _GAP_HIGH_TYPES else "med"
        obj = u.get("section") or u.get("config") or u.get("source") or u.get("workbench") or "workspace"
        target_id = None
        if u.get("section"):
            target_id = _section_id(str(u["section"]))
        elif u.get("config"):
            target_id = _runtime_id(str(u["config"]))
        extra_key = f"{u.get('config') or ''}|{u.get('source') or ''}"
        gaps.append(
            _gap(str(u.get("type")), severity, str(obj), target_id, str(u.get("message") or ""), extra_key)
        )
    for section in sections:
        if section.name in flagged:
            continue
        if section.relation_state == "uncertain":
            gaps.append(
                _gap(
                    "uncertain_relation",
                    "med",
                    section.name,
                    section.id,
                    section.relation_note or "section source relation is uncertain",
                )
            )
        elif section.relation_state == "declared":
            gaps.append(
                _gap(
                    "declared_without_derive_record",
                    "low",
                    section.name,
                    section.id,
                    section.relation_note
                    or "declares upstream pointers, but no exact derive record exists",
                )
            )
    gaps.sort(key=lambda g: (_GAP_SEVERITY_RANK[g["severity"]], g["object"], g["id"]))
    return gaps


def _gap(
    gap_type: str,
    severity: str,
    obj: str,
    target_id: str | None,
    message: str,
    extra_key: str = "",
) -> dict[str, Any]:
    digest = hashlib.sha1(f"{gap_type}|{obj}|{extra_key}".encode("utf-8")).hexdigest()[:8]
    return {
        "id": f"GAP-{digest}",
        "type": gap_type,
        "severity": severity,
        "object": obj,
        "target_id": target_id,
        "message": message,
    }


_WORKBENCH_TABLE_ROW = re.compile(
    r"^\|\s*(?P<id>\d+)\s*\|\s*(?P<title>.*?)\s*\|\s*(?P<domain>.*?)\s*\|"
    r"\s*(?P<batch>.*?)\s*\|\s*(?P<status>.*?)\s*\|\s*$"
)
_WORKBENCH_ITEM_HEADING = re.compile(r"^###\s+Item\s+(?P<id>\d+):\s*(?P<title>.+?)\s*$")
_WORKBENCH_FIELD = re.compile(r"^-\s+`?(?P<key>[A-Za-z_][A-Za-z0-9_]*)`?:\s*(?P<value>.*)$")


def _workbench_audits(
    root: Path,
    sources: list[SourceNode],
    sections: list[SectionNode],
    runtimes: list[RuntimeNode],
    unexplained: list[dict[str, Any]],
) -> list[WorkbenchAudit]:
    pr_dir = root / "system" / "pr"
    if not pr_dir.is_dir():
        return []
    audits: list[WorkbenchAudit] = []
    candidates = _workbench_link_candidates(sources, sections, runtimes)
    for path in sorted(pr_dir.glob("*/workbench.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        fm = _frontmatter(text)
        if not _is_workbench_frontmatter(fm):
            continue
        table_items = _parse_workbench_table(text)
        field_items = _parse_workbench_item_fields(text)
        merged = _merge_workbench_items(table_items, field_items)
        for item in merged:
            item.links = _resolve_item_links(item, candidates)
            item.evidence = _item_evidence(root, item)
            item.sinks = _item_sinks(root, item)
            item.patch = _item_patch(root, item)
        wb_id = str(fm.get("workbench_id") or path.parent.name)
        if not merged:
            # A workbench that parses to zero items is a format drift, not an
            # empty review — surface it as a gap instead of a silent blank view.
            unexplained.append(
                {
                    "type": "workbench_parse_empty",
                    "workbench": wb_id,
                    "message": "workbench frontmatter parsed but no items were found; "
                    "check table/heading format in " + _display_path(root, path),
                }
            )
        audits.append(
            WorkbenchAudit(
                id=wb_id,
                path=_display_path(root, path),
                status=str(fm.get("status") or ""),
                current_batch=(
                    str(fm["current_batch"]) if fm.get("current_batch") is not None else None
                ),
                final_pr_ready=bool(fm.get("final_pr_ready")),
                inbox_sources=_string_list(fm.get("inbox_sources")),
                capture_sources=_string_list(fm.get("capture_sources")),
                items=merged,
            )
        )
    return audits


# Workbench items reference canonical sources / sections / runtimes in free
# text (apply_scope, propagation_chain, …). Resolving those mentions to graph
# node ids is what connects the ingest-review surface to the provenance graph.
_WORKBENCH_LINK_FIELDS = (
    "source_evidence",
    "existing_canonical_sink",
    "covered_by",
    "apply_scope",
    "proposed_change",
    "propagation_chain",
)


def _workbench_link_candidates(
    sources: list[SourceNode],
    sections: list[SectionNode],
    runtimes: list[RuntimeNode],
) -> list[tuple[str, str, list[tuple[str, bool]]]]:
    candidates: list[tuple[str, str, list[tuple[str, bool]]]] = []
    for source in sources:
        keys: list[tuple[str, bool]] = [(source.pointer.replace("\\", "/").lower(), True)]
        if source.position and source.position.path:
            path_key = source.position.path.replace("\\", "/").lower()
            if (path_key, True) not in keys:
                keys.append((path_key, True))
        candidates.append((source.id, source.label, keys))
    for section in sections:
        candidates.append((section.id, section.name, [(section.name.lower(), False)]))
    for runtime in runtimes:
        candidates.append(
            (
                runtime.id,
                runtime.config,
                [
                    (runtime.config.lower(), False),
                    (runtime.path.replace("\\", "/").lower(), True),
                ],
            )
        )
    return candidates


def _resolve_item_links(
    item: WorkbenchItemAudit,
    candidates: list[tuple[str, str, list[tuple[str, bool]]]],
) -> list[WorkbenchLink]:
    links: list[WorkbenchLink] = []
    seen: set[str] = set()
    for field_name in _WORKBENCH_LINK_FIELDS:
        text = (item.fields.get(field_name) or "").replace("\\", "/").lower()
        if not text:
            continue
        for node_id, label, keys in candidates:
            if node_id in seen:
                continue
            if any(_link_key_matches(text, key, is_path) for key, is_path in keys):
                links.append(WorkbenchLink(field=field_name, node_id=node_id, label=label))
                seen.add(node_id)
    return links


def _link_key_matches(text: str, key: str, is_path: bool) -> bool:
    if not key or len(key) < 3:
        return False
    if is_path:
        return key in text
    return re.search(r"(?<![a-z0-9])" + re.escape(key) + r"(?![a-z0-9])", text) is not None


_BACKTICK_TOKEN = re.compile(r"`([^`]+)`")
_EVIDENCE_WINDOW_LINES = 18
_SINK_EXCERPT_LINES = 14


def _field_tokens(root: Path, text: str) -> tuple[list[str], list[str]]:
    """Split a free-text field into (resolvable file paths, anchor strings)."""
    tokens = _BACKTICK_TOKEN.findall(text)
    if not tokens:
        tokens = [t.strip(" ,;:()[]") for t in text.split()]
    paths: list[str] = []
    anchors: list[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        looks_pathy = "/" in token or token.endswith(".md")
        resolved = _resolve_pointer(root, token) if looks_pathy else None
        if resolved is not None and resolved.is_file():
            if token not in paths:
                paths.append(token)
        elif token not in anchors:
            anchors.append(token)
    return paths, anchors


def _item_evidence(root: Path, item: WorkbenchItemAudit) -> list[WorkbenchEvidence]:
    raw = item.fields.get("source_evidence") or ""
    if not raw.strip():
        return []
    paths, anchors = _field_tokens(root, raw)
    out: list[WorkbenchEvidence] = []
    for pointer in paths[:2]:
        resolved = _resolve_pointer(root, pointer)
        try:
            text = resolved.read_text(encoding="utf-8")  # type: ignore[union-attr]
        except (OSError, UnicodeDecodeError):
            continue
        matched = False
        for anchor in anchors[:4]:
            idx = text.find(anchor)
            if idx < 0:
                continue
            matched = True
            out.append(_evidence_window(pointer, text, idx, anchor))
            if len(out) >= 3:
                return out
        if not matched:
            out.append(
                WorkbenchEvidence(
                    path=pointer,
                    anchor=anchors[0] if anchors else "",
                    found=not anchors,
                    start_line=1,
                    excerpt=_head_lines(text, 12),
                    note="未能在文件中定位锚点，显示文件开头" if anchors else "无锚点，显示文件开头",
                )
            )
        if len(out) >= 3:
            break
    return out


def _evidence_window(pointer: str, text: str, char_idx: int, anchor: str) -> WorkbenchEvidence:
    lines = text.splitlines()
    line_no = text.count("\n", 0, char_idx) + 1
    start = max(1, line_no - 2)
    end = min(len(lines), line_no + _EVIDENCE_WINDOW_LINES)
    return WorkbenchEvidence(
        path=pointer,
        anchor=anchor,
        found=True,
        start_line=start,
        excerpt="\n".join(lines[start - 1 : end]),
    )


def _item_sinks(root: Path, item: WorkbenchItemAudit) -> list[WorkbenchSinkAudit]:
    raw = item.fields.get("existing_canonical_sink") or ""
    if not raw.strip():
        return []
    tokens = _BACKTICK_TOKEN.findall(raw)
    if not tokens:
        tokens = [t.strip(" ,;:()[]") for t in raw.split()]
    out: list[WorkbenchSinkAudit] = []
    for token in tokens:
        token = token.strip()
        if "/" not in token and not token.endswith(".md"):
            continue
        resolved = _resolve_pointer(root, token)
        exists = bool(resolved is not None and resolved.is_file())
        excerpt = ""
        if exists:
            try:
                excerpt = _head_lines(resolved.read_text(encoding="utf-8"), _SINK_EXCERPT_LINES)  # type: ignore[union-attr]
            except (OSError, UnicodeDecodeError):
                excerpt = ""
        out.append(WorkbenchSinkAudit(path=token, exists=exists, excerpt=excerpt))
        if len(out) >= 3:
            break
    return out


def _head_lines(text: str, count: int) -> str:
    return "\n".join(text.splitlines()[:count])


_PATCH_BLOCK_MAX_LINES = 100


def _item_patch(root: Path, item: WorkbenchItemAudit) -> WorkbenchPatchAudit | None:
    target = (item.fields.get("proposed_patch_target") or "").strip().strip("`")
    proposed = item.fields.get("proposed_patch_text") or ""
    # Tolerate agents writing a YAML-style "|" marker on the key line.
    proposed = re.sub(r"^\|\s*\n?", "", proposed)
    if not target or not proposed.strip():
        return None
    anchor = (item.fields.get("proposed_patch_anchor") or "").strip().strip("`")
    resolved = _resolve_pointer(root, target)
    if resolved is None or not resolved.is_file():
        return WorkbenchPatchAudit(
            target=target, anchor=anchor, mode="create",
            target_exists=False, anchor_found=False, start_line=None,
            current_text="", proposed_text=proposed,
            note="目标文件不存在，按新建处理",
        )
    try:
        file_text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return WorkbenchPatchAudit(
            target=target, anchor=anchor, mode="unlocated",
            target_exists=True, anchor_found=False, start_line=None,
            current_text="", proposed_text=proposed,
            note="目标文件不可读，无法生成 before/after",
        )
    if not anchor:
        return WorkbenchPatchAudit(
            target=target, anchor="", mode="append",
            target_exists=True, anchor_found=False,
            start_line=_line_count(file_text) + 1,
            current_text="", proposed_text=proposed,
            note="未指定锚点，按文件末尾追加处理",
        )
    block = _anchored_block(file_text, anchor)
    if block is None:
        return WorkbenchPatchAudit(
            target=target, anchor=anchor, mode="unlocated",
            target_exists=True, anchor_found=False, start_line=None,
            current_text="", proposed_text=proposed,
            note="锚点未在目标文件中找到；只展示提议文本，不猜测落点",
        )
    start, end = block
    lines = file_text.splitlines()
    current = "\n".join(lines[start - 1 : min(end, start - 1 + _PATCH_BLOCK_MAX_LINES)])
    return WorkbenchPatchAudit(
        target=target, anchor=anchor, mode="replace",
        target_exists=True, anchor_found=True, start_line=start,
        current_text=current, proposed_text=proposed,
    )


# Anchored-block location is shared mechanics — see forge/patch.py.
_anchored_block = anchored_block


def _is_workbench_frontmatter(fm: dict[str, Any]) -> bool:
    kind = str(fm.get("kind") or "")
    return kind.endswith("workbench") or "workbench_id" in fm


def _parse_workbench_table(text: str) -> dict[str, WorkbenchItemAudit]:
    items: dict[str, WorkbenchItemAudit] = {}
    in_items = False
    for line in text.splitlines():
        if line.strip() == "## Step 1: Information Items":
            in_items = True
            continue
        if in_items and line.startswith("## "):
            break
        if not in_items or not line.startswith("|"):
            continue
        match = _WORKBENCH_TABLE_ROW.match(line)
        if not match:
            continue
        item_id = match.group("id").strip().zfill(2)
        items[item_id] = WorkbenchItemAudit(
            id=item_id,
            title=_clean_table_cell(match.group("title")),
            initial_domain=_clean_table_cell(match.group("domain")),
            batch=_clean_table_cell(match.group("batch")),
            status=_clean_table_cell(match.group("status")),
        )
    return items


def _parse_workbench_item_fields(text: str) -> dict[str, WorkbenchItemAudit]:
    items: dict[str, WorkbenchItemAudit] = {}
    current: WorkbenchItemAudit | None = None
    current_key: str | None = None
    for line in text.splitlines():
        heading = _WORKBENCH_ITEM_HEADING.match(line)
        if heading:
            item_id = heading.group("id").strip().zfill(2)
            current = WorkbenchItemAudit(
                id=item_id,
                title=heading.group("title").strip(),
                batch="",
                status="",
            )
            items[item_id] = current
            current_key = None
            continue
        if current is None:
            continue
        if line.startswith("### ") or line.startswith("## "):
            current = None
            current_key = None
            continue
        field_match = _WORKBENCH_FIELD.match(line)
        if field_match:
            current_key = field_match.group("key").strip()
            current.fields[current_key] = field_match.group("value").strip()
            continue
        if current_key and (line.startswith("  ") or line.startswith("\t")):
            continuation = line.strip()
            if continuation:
                prior = current.fields.get(current_key, "")
                current.fields[current_key] = (prior + "\n" + continuation).strip()
    return items


def _merge_workbench_items(
    table_items: dict[str, WorkbenchItemAudit],
    field_items: dict[str, WorkbenchItemAudit],
) -> list[WorkbenchItemAudit]:
    ids = sorted(
        set(table_items) | set(field_items),
        key=lambda x: (int(x) if x.isdigit() else 10**9, x),
    )
    merged: list[WorkbenchItemAudit] = []
    for item_id in ids:
        table = table_items.get(item_id)
        detail = field_items.get(item_id)
        merged.append(
            WorkbenchItemAudit(
                id=item_id,
                title=(detail.title if detail and detail.title else table.title if table else ""),
                batch=(table.batch if table else detail.batch if detail else ""),
                status=(table.status if table else detail.status if detail else ""),
                initial_domain=table.initial_domain if table else "",
                fields=detail.fields if detail else {},
            )
        )
    return merged


def _clean_table_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    return [str(value)]


def _compile_mappings(
    sections: dict[str, Section], config: Config, runtime_text: str
) -> dict[str, tuple[int, int]]:
    runtime_lines = runtime_text.splitlines()
    cursor = 0
    out: dict[str, tuple[int, int]] = {}
    for name in config.sections:
        section = sections[name]
        if name in config.section_views:
            section = _apply_section_view(section, config.section_views[name], config.name)
        block_lines = _rendered_section_block(section, config).splitlines()
        found = _find_lines(runtime_lines, block_lines, cursor)
        if found is None:
            continue
        start, end = found
        out[name] = (start + 1, end + 1)
        cursor = end + 1
    return out


def _rendered_section_block(section: Section, config: Config) -> str:
    body = section.body.strip()
    if section.type == "wrapper":
        return body
    if config.demote_section_headings:
        body = _demote_headings(body)
    if config.target == "agents-md":
        heading = agents_heading(section)
    else:
        heading = _section_heading(section)
    return f"{heading}\n\n{body}".rstrip()


def _find_lines(
    haystack: list[str], needle: list[str], start: int
) -> tuple[int, int] | None:
    if not needle:
        return None
    max_i = len(haystack) - len(needle)
    for i in range(start, max_i + 1):
        if haystack[i : i + len(needle)] == needle:
            return i, i + len(needle) - 1
    return None


def _section_pointers(section: Section) -> list[str]:
    pointers: list[str] = []
    if section.source:
        pointers.append(str(section.source))
    pointers.extend(str(p) for p in section.upstream)
    return list(dict.fromkeys(pointers))


def _section_relation_state(section: Section, pointers: list[str]) -> tuple[str, str]:
    if section.type == "wrapper":
        return "wrapper", "compiled wrapper block; no upstream source by design"
    if not pointers:
        return "uncertain", "no source/upstream pointer declared"
    if section.kind == "derived" or section.generated_by or "provenance" in section.meta:
        return "derived", "section frontmatter declares derivation evidence"
    return "declared", "section frontmatter declares upstream pointers, without exact derivation record"


def _source_node(root: Path, pointer: str) -> SourceNode:
    resolved = _resolve_pointer(root, pointer)
    status = "resolved" if resolved and resolved.exists() else "missing"
    position = None
    excerpt_truncated = False
    if resolved:
        content_excerpt = None
        end_line = None
        if resolved.is_file():
            source_text = resolved.read_text(encoding="utf-8")
            content_excerpt = _excerpt(source_text)
            excerpt_truncated = len(source_text) > _EXCERPT_MAX_CHARS
            end_line = _line_count(source_text)
        position = FilePosition(
            path=_display_path(root, resolved),
            start_line=1 if resolved.is_file() else None,
            end_line=end_line,
            exists=resolved.exists(),
        )
    else:
        content_excerpt = None
    return SourceNode(
        id="source:" + hashlib.sha1(pointer.encode("utf-8")).hexdigest()[:16],
        label=Path(pointer).name or pointer,
        kind=_source_kind(pointer),
        pointer=pointer,
        position=position,
        status=status,
        content_excerpt=content_excerpt,
        layer=_layer_for_pointer(root, pointer),
        excerpt_truncated=excerpt_truncated,
    )


def _runtime_mirrors(
    root: Path, canonical_path: Path, runtime_text: str
) -> list[FilePosition]:
    """Find checked-out markdown files that mirror this rendered runtime.

    Some delivery flows copy forge's compiled runtime into a product-specific
    runtime directory. The copy is not a new fact source, but it is an important
    owner-facing runtime surface and should be visible in the audit portal.
    """
    mirrors: list[FilePosition] = []
    canonical_resolved = canonical_path.resolve()
    for path in _iter_candidate_runtime_md(root):
        try:
            if path.resolve() == canonical_resolved:
                continue
            if path.read_text(encoding="utf-8") != runtime_text:
                continue
        except (OSError, UnicodeDecodeError):
            continue
        mirrors.append(
            FilePosition(
                path=_display_path(root, path),
                start_line=1,
                end_line=_line_count(runtime_text),
                exists=True,
            )
        )
    return sorted(mirrors, key=lambda p: p.path)


def _iter_candidate_runtime_md(root: Path):
    ignored_dirs = {".git", ".forge", "node_modules", ".venv", "__pycache__"}
    for path in root.rglob("*.md"):
        if any(part in ignored_dirs for part in path.relative_to(root).parts):
            continue
        yield path


def _import_origins(root: Path, source: SourceNode) -> list[str]:
    """External origin label(s) recorded in a capture/memory file's frontmatter.

    Captures written by the agent-memory / web-clipping monitors carry a
    ``source:`` (or ``origin:``) field naming where the corpus came from
    (e.g. ``Codex memory``). Falls back to a kind-derived label so an imported
    capture still shows an upstream node.
    """
    resolved = _resolve_pointer(root, source.pointer)
    if not resolved or not resolved.is_file():
        return []
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    fm = _frontmatter(text)
    raw = fm.get("source") or fm.get("origin") or fm.get("imported_from")
    if not raw:
        return [source.kind.capitalize() + " import"]
    if isinstance(raw, str):
        raw = [raw]
    return [str(x).strip() for x in raw if str(x).strip()]


def _frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    try:
        data = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _layer_for_pointer(root: Path, pointer: str) -> str:
    """Derive an architectural layer label from a source/upstream pointer.

    The layer is a generic, data-derived grouping — not a hardcoded taxonomy:
    in-workspace pointers group by their top-level directory (``base``,
    ``customers``, ``skills``, ``docs`` …); cross-repo pointers group by the
    originating project so an audit shows when canonical facts live in another
    repository. It degrades to ``external`` / ``core`` when nothing is known.
    """
    normalized = str(pointer).replace("\\", "/")
    path = Path(pointer).expanduser()
    if not path.is_absolute():
        return normalized.split("/", 1)[0] or "core"
    try:
        rel = path.resolve().relative_to(root)
        return rel.as_posix().split("/", 1)[0] or "core"
    except ValueError:
        parts = path.parts
        for marker in ("projects", "repos", "workspace"):
            if marker in parts:
                idx = parts.index(marker)
                if idx + 1 < len(parts):
                    return parts[idx + 1]
        return "external"


def _section_layer(root: Path, section: Section, pointers: list[str]) -> str:
    """Layer for a section: explicit frontmatter wins, else its primary source.

    A section inherits the layer of the canonical source it draws from, so the
    section lane lines up with the source lane architecturally. Wrapper or
    source-less sections fall back to ``core``.
    """
    declared = section.meta.get("layer") if isinstance(section.meta, dict) else None
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if pointers:
        return _layer_for_pointer(root, pointers[0])
    return "core"


def _source_kind(pointer: str) -> str:
    normalized = pointer.replace("\\", "/")
    if normalized.startswith("capture/") or "/capture/" in normalized:
        if "memory" in normalized:
            return "memory"
        return "capture"
    if "memory" in normalized or ".codex/memories" in normalized:
        return "memory"
    if (
        normalized.startswith("workbench/project/")
        or "/workbench/project/" in normalized
        or normalized.startswith("workspace/project/")
        or "/workspace/project/" in normalized
    ):
        return "project"
    if normalized.endswith(".md") or "/" in normalized:
        return "source"
    return "source"


def _resolve_pointer(root: Path, pointer: str) -> Path | None:
    path = Path(pointer).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def _section_position(root: Path, section: Section) -> FilePosition | None:
    if not section.path:
        return None
    return FilePosition(
        path=_display_path(root, section.path),
        start_line=1,
        end_line=_line_count(section.path.read_text(encoding="utf-8")),
        exists=section.path.exists(),
    )


def _line_count(text: str) -> int:
    return len(text.splitlines()) or 1


_EXCERPT_MAX_CHARS = 8000


def _excerpt(text: str, max_chars: int = _EXCERPT_MAX_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"


def _display_path(root: Path, path: Path) -> str:
    path = Path(path)
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _section_id(name: str) -> str:
    return "section:" + name


def _runtime_id(config_name: str) -> str:
    return "runtime:" + config_name


def _edge_id(from_id: str, to_id: str, relation: str) -> str:
    raw = f"{from_id}->{to_id}:{relation}"
    return "edge:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
