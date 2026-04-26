"""Compute source-level (via git) and output-level (via difflib) diffs."""

from __future__ import annotations

import difflib
from pathlib import Path

from forge.gate import _git


def source_diff_via_git(root: Path) -> list[str]:
    """Return git diff HEAD -- sp/ as a list of lines.

    Note: git's output uses `a/sp/section/foo.md` and `b/sp/section/foo.md`
    prefixes by default. We rewrite those to `approved/section/foo.md` and
    `current/section/foo.md` to match the v0.1 user-facing format.
    """
    raw = _git.diff_paths(root, ["sp"])
    if not raw:
        return []
    out_lines: list[str] = []
    for line in raw.splitlines():
        if line.startswith("--- a/sp/"):
            line = "--- approved/" + line[len("--- a/sp/"):]
        elif line.startswith("+++ b/sp/"):
            line = "+++ current/" + line[len("+++ b/sp/"):]
        elif line.startswith("diff --git "):
            # skip git's diff header — readers don't need it
            continue
        elif line.startswith("index "):
            continue
        out_lines.append(line)
    return out_lines


def output_diff(before: str, after: str, label: str = "output") -> list[str]:
    """Unified diff between two rendered output texts (in-memory, no git)."""
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


# Legacy entry point kept for callers that haven't migrated yet.
def source_diff(approved_sp: Path, current_sp: Path) -> list[str]:
    """Deprecated: v0.1 source diff that walked two sp/ trees on disk.

    v0.2 callers should use source_diff_via_git(root). Kept so old tests can
    still import it; uses difflib over the two given trees as fallback.
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
        diff = difflib.unified_diff(
            a.splitlines(keepends=False),
            b.splitlines(keepends=False),
            fromfile=f"approved/{key}",
            tofile=f"current/{key}",
            lineterm="",
        )
        diff_lines = list(diff)
        if diff_lines:
            lines.extend(diff_lines)
            lines.append("")
    return lines


def _collect(sp_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not sp_dir.exists():
        return out
    for path in sorted(sp_dir.rglob("*.md")):
        rel = path.relative_to(sp_dir).as_posix()
        out[rel] = path.read_text(encoding="utf-8")
    return out
