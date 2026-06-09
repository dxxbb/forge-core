"""Diff two audit graphs (a base git ref vs the working tree).

This powers the portal's change-review mode: it answers "if I approve this
change, what do my agents actually start reading differently?" by comparing the
full source -> section -> runtime graph at ``base_ref`` against the working tree
and annotating every node/edge with added / modified / removed / unchanged.

Node ids are root-independent (section name, config name, source-pointer hash),
so the two graphs line up across the base worktree and the live tree.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import hashlib
from pathlib import Path
from typing import Any

import yaml

from forge.audit.graph import build_audit_graph
from forge.compiler.section import _split_frontmatter

_CONTENT_FIELD = {"sources": "content_excerpt", "sections": "content", "runtimes": "content"}

_REVIEW_DIRS = (
    "assist config/",
    "capture/",
    "context build/config/",
    "context build/sections/",
    "public knowledge base/",
    "system/inbox/",
    "system/pr/",
    "system/approve log/",
    "system/reject log/",
    "user space/",
    "workbench/",
    "workspace/",
)
_TEXT_SUFFIXES = {".md", ".json", ".yaml", ".yml", ".toml", ".txt"}


def build_audit_diff(root: Path, base_ref: str = "HEAD") -> dict[str, Any]:
    """Build the working-tree audit graph annotated with a diff vs ``base_ref``."""
    root = Path(root).resolve()
    cur = build_audit_graph(root).to_dict()
    base = _base_graph(root, base_ref)
    if base is None:
        for kind in _CONTENT_FIELD:
            for node in cur[kind]:
                node["change"] = "unchanged"
        for edge in cur["edges"]:
            edge["change"] = "unchanged"
        cur["diff"] = {
            "base_ref": base_ref,
            "available": False,
            "added": 0,
            "modified": 0,
            "removed": 0,
        }
        return cur
    _add_unlinked_worktree_changes(root, base_ref, cur, base)
    _annotate(cur, base, base_ref)
    return cur


def _annotate(cur: dict, base: dict, base_ref: str) -> None:
    summary = {"base_ref": base_ref, "available": True, "added": 0, "modified": 0, "removed": 0}
    for kind, field in _CONTENT_FIELD.items():
        base_by_id = {n["id"]: n for n in base[kind]}
        cur_ids = set()
        for node in cur[kind]:
            cur_ids.add(node["id"])
            prior = base_by_id.get(node["id"])
            if prior is None:
                node["change"] = "added"
                summary["added"] += 1
            elif (node.get(field) or "") != (prior.get(field) or ""):
                node["change"] = "modified"
                node["prev_content"] = prior.get(field) or ""
                summary["modified"] += 1
            else:
                node["change"] = "unchanged"
        for bid, prior in base_by_id.items():
            if bid not in cur_ids:
                prior["change"] = "removed"
                prior["prev_content"] = prior.get(field) or ""
                cur[kind].append(prior)
                summary["removed"] += 1

    base_edge_ids = {e["id"] for e in base["edges"]}
    cur_edge_ids = {e["id"] for e in cur["edges"]}
    for edge in cur["edges"]:
        edge["change"] = "added" if edge["id"] not in base_edge_ids else "unchanged"
    for edge in base["edges"]:
        if edge["id"] not in cur_edge_ids:
            edge["change"] = "removed"
            cur["edges"].append(edge)
    cur["diff"] = summary


def _base_graph(root: Path, base_ref: str) -> dict | None:
    """Materialize ``base_ref`` into a throwaway worktree and build its graph.

    Returns ``None`` when the workspace is not a git repo or the ref / worktree
    cannot be created — the caller then falls back to a no-diff view.
    """
    if not _in_git(root):
        return None
    tmp = Path(tempfile.mkdtemp(prefix="forge-audit-base-"))
    wt = tmp / "wt"
    try:
        added = subprocess.run(
            ["git", "-C", str(root), "worktree", "add", "--detach", str(wt), base_ref],
            capture_output=True,
            text=True,
        )
        if added.returncode != 0:
            return None
        return build_audit_graph(wt).to_dict()
    except Exception:
        return None
    finally:
        subprocess.run(
            ["git", "-C", str(root), "worktree", "remove", "--force", str(wt)],
            capture_output=True,
            text=True,
        )
        shutil.rmtree(tmp, ignore_errors=True)


def _in_git(root: Path) -> bool:
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def _add_unlinked_worktree_changes(root: Path, base_ref: str, cur: dict, base: dict) -> None:
    """Add changed review-relevant files that are not already graph sources.

    The normal audit graph starts from section upstream pointers. That is correct
    for provenance, but review mode must also expose proposed KB/capture/source
    edits before they are bridged into a section. These nodes are explicitly
    marked as unlinked so the reviewer can see "this file changed, but it has no
    source -> section -> runtime path yet".
    """
    existing = _source_paths(cur) | _source_paths(base)
    for rel in _changed_review_files(root, base_ref):
        if rel in existing:
            continue
        cur_text = _read_worktree_text(root, rel)
        base_text = _read_git_text(root, base_ref, rel)
        if cur_text is not None:
            cur["sources"].append(_unlinked_source_node(root, rel, cur_text, exists=True))
        if base_text is not None:
            base["sources"].append(_unlinked_source_node(root, rel, base_text, exists=True))
    _add_kb_source_edges(root, cur)
    _add_kb_source_edges(root, base, base_ref=base_ref)


def _source_paths(graph: dict) -> set[str]:
    paths: set[str] = set()
    for node in graph.get("sources", []):
        pointer = node.get("pointer")
        if pointer:
            paths.add(str(pointer).replace("\\", "/"))
        pos = node.get("position") or {}
        if pos.get("path"):
            paths.add(str(pos["path"]).replace("\\", "/"))
    return paths


def _changed_review_files(root: Path, base_ref: str) -> list[str]:
    tracked = subprocess.run(
        ["git", "-C", str(root), "diff", "--name-only", base_ref, "--"],
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    names: list[str] = []
    if tracked.returncode == 0:
        names.extend(p.strip() for p in tracked.stdout.splitlines() if p.strip())
    if untracked.returncode == 0:
        names.extend(p.strip() for p in untracked.stdout.splitlines() if p.strip())
    return sorted({p for p in names if _is_review_file(p)})


def _is_review_file(rel: str) -> bool:
    normalized = rel.replace("\\", "/")
    if normalized.startswith(".forge/") or "/.forge/" in normalized:
        return False
    if not any(normalized.startswith(prefix) for prefix in _REVIEW_DIRS):
        return False
    return Path(normalized).suffix in _TEXT_SUFFIXES


def _read_worktree_text(root: Path, rel: str) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_git_text(root: Path, base_ref: str, rel: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(root), "show", f"{base_ref}:{rel}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _unlinked_source_node(root: Path, rel: str, content: str, *, exists: bool) -> dict[str, Any]:
    path = rel.replace("\\", "/")
    return {
        "id": "source:unlinked:" + hashlib.sha1(path.encode("utf-8")).hexdigest()[:16],
        "label": Path(path).name or path,
        "kind": "unlinked-change",
        "pointer": path,
        "position": {
            "path": path,
            "start_line": 1,
            "end_line": len(content.splitlines()),
            "exists": exists,
        },
        "status": "unlinked",
        "content_excerpt": content,
        "layer": _layer_for_path(path),
    }


def _add_kb_source_edges(root: Path, graph: dict, base_ref: str | None = None) -> None:
    """Connect review-only capture/clipping inputs to KB files that cite them.

    This is deliberately scoped to source-to-source review lineage. It does not
    upgrade the main source -> section provenance contract; it only lets the
    portal show "this clipping/capture was integrated into this KB page" when a
    changed KB file declares that path in frontmatter.
    """
    by_pointer = _source_nodes_by_pointer(graph)
    existing_edge_ids = {edge.get("id") for edge in graph.get("edges", [])}
    for kb_node in graph.get("sources", []):
        kb_pointer = str(kb_node.get("pointer") or "").replace("\\", "/")
        if not kb_pointer.startswith("public knowledge base/"):
            continue
        content = kb_node.get("content_excerpt") or ""
        for source_pointer in _frontmatter_source_paths(content):
            source_node = by_pointer.get(source_pointer)
            if source_node is None:
                text = (
                    _read_git_text(root, base_ref, source_pointer)
                    if base_ref
                    else _read_worktree_text(root, source_pointer)
                )
                if text is None:
                    continue
                source_node = _unlinked_source_node(root, source_pointer, text, exists=True)
                graph["sources"].append(source_node)
                by_pointer[source_pointer] = source_node
            if not source_node:
                continue
            edge_id = _edge_id(source_node["id"], kb_node["id"], "input-source")
            if edge_id in existing_edge_ids:
                continue
            graph["edges"].append(
                {
                    "id": edge_id,
                    "from_id": source_node["id"],
                    "to_id": kb_node["id"],
                    "relation": "input_to_source",
                    "status": "declared",
                    "evidence": f"KB frontmatter sources includes {source_pointer}",
                    "confidence": "source-declared",
                    "runtime_range": None,
                }
            )
            existing_edge_ids.add(edge_id)


def _source_nodes_by_pointer(graph: dict) -> dict[str, dict[str, Any]]:
    return {
        str(node.get("pointer")).replace("\\", "/"): node
        for node in graph.get("sources", [])
        if node.get("pointer")
    }


def _frontmatter_source_paths(text: str) -> list[str]:
    frontmatter, _ = _split_frontmatter(text)
    if not frontmatter:
        return []
    try:
        parsed = yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return []
    if not isinstance(parsed, dict):
        return []
    raw = parsed.get("sources") or parsed.get("source") or parsed.get("upstream")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw_items = [raw]
    elif isinstance(raw, list):
        raw_items = raw
    else:
        return []
    paths: list[str] = []
    for item in raw_items:
        if isinstance(item, dict):
            candidate = item.get("path") or item.get("source") or item.get("url")
        else:
            candidate = item
        normalized = str(candidate or "").strip().replace("\\", "/")
        if not normalized:
            continue
        normalized = normalized.split(" (", 1)[0].split(" @", 1)[0].strip()
        if normalized.startswith("capture/"):
            paths.append(normalized)
    return list(dict.fromkeys(paths))


def _layer_for_path(path: str) -> str:
    if "/" not in path:
        return "core"
    return path.split("/", 1)[0]


def _edge_id(from_id: str, to_id: str, relation: str) -> str:
    raw = f"{from_id}->{to_id}:{relation}"
    return "edge:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
