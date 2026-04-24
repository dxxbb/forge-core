"""Compute source-level and output-level diffs between approved and current state."""

from __future__ import annotations

import difflib
from pathlib import Path


def source_diff(approved_sp: Path, current_sp: Path) -> list[str]:
    """Return a unified diff of every file under sp/ (approved vs current).

    Empty list = no changes.
    """
    lines: list[str] = []
    approved_files = _collect(approved_sp)
    current_files = _collect(current_sp)
    all_keys = sorted(set(approved_files) | set(current_files))
    for key in all_keys:
        a = approved_files.get(key, "")
        b = current_files.get(key, "")
        if a == b:
            continue
        rel = key
        diff = difflib.unified_diff(
            a.splitlines(keepends=False),
            b.splitlines(keepends=False),
            fromfile=f"approved/{rel}",
            tofile=f"current/{rel}",
            lineterm="",
        )
        diff_lines = list(diff)
        if diff_lines:
            lines.extend(diff_lines)
            lines.append("")
    return lines


def output_diff(before: str, after: str, label: str = "output") -> list[str]:
    """Unified diff between two rendered output texts."""
    if before == after:
        return []
    return list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"approved/{label}",
            tofile=f"proposed/{label}",
            lineterm="",
        )
    )


def _collect(sp_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not sp_dir.exists():
        return out
    for path in sorted(sp_dir.rglob("*.md")):
        rel = path.relative_to(sp_dir).as_posix()
        out[rel] = path.read_text(encoding="utf-8")
    return out
