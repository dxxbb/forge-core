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
from pathlib import Path
from typing import Any

from forge.audit.graph import build_audit_graph

_CONTENT_FIELD = {"sources": "content_excerpt", "sections": "content", "runtimes": "content"}


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
