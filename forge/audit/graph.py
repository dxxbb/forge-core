"""Build an audit graph for section-to-runtime context compilation.

The graph is intentionally conservative:

- section -> runtime ranges are compiler-derived and may be marked exact
- source -> section relations are only as strong as section frontmatter records
- missing or ambiguous evidence is represented as uncertain, not inferred away
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from forge.compiler.config import Config
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
class AuditEdge:
    id: str
    from_id: str
    to_id: str
    relation: str
    status: str
    evidence: str
    confidence: str
    runtime_range: FilePosition | None = None


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

    return AuditGraph(
        schema_version="forge.audit.v1",
        workspace_root=str(root),
        layout=layout.name,
        sources=sorted(source_nodes_by_pointer.values(), key=lambda n: n.pointer),
        sections=sorted(section_nodes, key=lambda n: n.name),
        runtimes=runtime_nodes,
        edges=edges,
        unexplained=unexplained,
    )


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
    if resolved:
        content_excerpt = None
        end_line = None
        if resolved.is_file():
            source_text = resolved.read_text(encoding="utf-8")
            content_excerpt = _excerpt(source_text)
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


def _excerpt(text: str, max_chars: int = 8000) -> str:
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
