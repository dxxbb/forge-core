"""Scaffolding for `forge proposal new`.

Reads pending inbox files, derives the PR slug + capture sources, and writes
a proposal.md stub with v0.3 schema frontmatter pre-populated:

    - inbox_sources: from --inbox arg (or all pending inbox if --inbox not set)
    - capture_sources: derived from each inbox's `source:` frontmatter list
    - items[]: one item per inbox file, monitor_info pre-filled from
                  the inbox `## Source summary` line + extracted from capture
                  frontmatter; disposition left blank (agent fills in).

Body is a thin placeholder that points the user/agent to `forge pr render`.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from forge.proposal.schema import (
    Disposition,
    Item,
    Proposal,
    PropagationBranch,
    PropagationNode,
    SubItem,
    dump_proposal,
)


_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def _safe_slug(value: str) -> str:
    s = re.sub(_SLUG_RE, "-", (value or "").lower()).strip("-_.")
    s = re.sub(r"-{2,}", "-", s)
    return s or "proposal"


def _read_yaml_frontmatter(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    fm = yaml.safe_load(text[3:end].strip()) or {}
    if not isinstance(fm, dict):
        return {}, text
    body = text[end + 4:].lstrip("\n")
    return fm, body


def _capture_files_from_inbox_source(workspace: Path, source: str) -> list[Path]:
    """Resolve an inbox `source` entry to capture file path(s).

    The inbox writes `source: - capture/import/<batch>/` (a directory). We
    enumerate `*.md` files in that batch directory, excluding any nested
    subdirs (which would shadow stale snapshots).
    """
    p = (workspace / source.rstrip("/")).resolve()
    if p.is_dir():
        return sorted([f for f in p.glob("*.md") if f.is_file()])
    if p.is_file():
        return [p]
    return []


def _extracted_from_capture(workspace: Path, capture_path: Path) -> str:
    """Build a multi-line `extracted` skeleton from a capture file's frontmatter."""
    if not capture_path.exists():
        return f"{capture_path.relative_to(workspace).as_posix() if capture_path.is_absolute() else capture_path}\n  - (capture file not readable)"
    fm, _body = _read_yaml_frontmatter(capture_path)
    rel = capture_path.relative_to(workspace).as_posix() if capture_path.is_absolute() else str(capture_path)
    lines = [rel]
    if "source" in fm:
        lines.append(f"  - source: {fm['source']}")
    if "captured_at" in fm:
        lines.append(f"  - captured_at: {fm['captured_at']}")
    if "source_size" in fm:
        lines.append(f"  - source_size: {fm['source_size']}")
    if "source_files" in fm:
        lines.append(f"  - source_files: {fm['source_files']}")
    if "source_digest" in fm:
        digest = str(fm['source_digest'])
        lines.append(f"  - source_digest: {digest[:12]}…")
    lines.append("  - <TODO: agent extracts key facts / quotes here>")
    return "\n".join(lines)


def _monitor_info_from_inbox(inbox_path: Path) -> str:
    """Pull the first bullet under `## Source summary` from an inbox file
    as a one-line monitor_info. Falls back to inbox filename slug."""
    text = inbox_path.read_text(encoding="utf-8")
    m = re.search(r"##\s+Source summary\s*\n+\s*-\s*(.+?)(?:\n|$)", text)
    if m:
        return m.group(1).strip()
    return inbox_path.stem


def derive_pr_id(now: datetime, title: str) -> str:
    return f"{now.strftime('%Y%m%d-%H%M%S')}-{_safe_slug(title)}"


def scaffold_proposal(
    workspace: Path,
    inbox_files: list[Path],
    *,
    title: str = "context-import",
    now: datetime | None = None,
) -> Path:
    """Create system/pr/<id>/proposal.md from inbox files.

    Returns the proposal.md path. Idempotent only on directory uniqueness:
    timestamps include seconds, so concurrent calls within the same second
    will collide — caller should retry with a new now.
    """
    if not inbox_files:
        raise ValueError("scaffold_proposal: no inbox files given")
    now = now or datetime.now().astimezone()
    pr_id = derive_pr_id(now, title)
    pr_dir = workspace / "system" / "pr" / pr_id
    if pr_dir.exists():
        # rare collision; suffix
        i = 1
        while True:
            candidate = workspace / "system" / "pr" / f"{pr_id}-{i}"
            if not candidate.exists():
                pr_dir = candidate
                break
            i += 1
    pr_dir.mkdir(parents=True, exist_ok=False)

    # Inbox sources (workspace-relative, posix)
    inbox_sources: list[str] = []
    for ip in inbox_files:
        inbox_sources.append(ip.relative_to(workspace).as_posix())

    # Capture sources: collect every capture file referenced by every inbox
    capture_sources: list[str] = []
    capture_paths_per_inbox: list[list[Path]] = []
    for ip in inbox_files:
        fm, _body = _read_yaml_frontmatter(ip)
        sources = fm.get("source", []) or []
        if isinstance(sources, str):
            sources = [sources]
        captured: list[Path] = []
        for s in sources:
            captured.extend(_capture_files_from_inbox_source(workspace, str(s)))
        for c in captured:
            rel = c.relative_to(workspace).as_posix()
            if rel not in capture_sources:
                capture_sources.append(rel)
        capture_paths_per_inbox.append(captured)

    # Build items: one Item per inbox source. Disposition left blank (agent fills).
    items: list[Item] = []
    for idx, ip in enumerate(inbox_files):
        captures = capture_paths_per_inbox[idx]
        if not captures:
            extracted = "(no capture files found in inbox source)"
        else:
            extracted = "\n\n".join(_extracted_from_capture(workspace, c) for c in captures)
        items.append(Item(
            id=str(idx + 1),
            monitor_info=_monitor_info_from_inbox(ip),
            extracted=extracted,
            disposition=None,                  # agent fills: APPLY|COVERED|ARCHIVE|DECIDE|NA|MIXED
            disposition_note="<APPLY|COVERED|ARCHIVE|DECIDE|NA|MIXED>",
            rationale="<TODO: explain why this disposition>",
            propagation=[
                PropagationBranch(
                    branch="a",
                    node=PropagationNode(
                        path=ip.relative_to(workspace).as_posix(),
                        label="监控源",
                        children=[
                            PropagationBranch(
                                branch="a1",
                                node=PropagationNode(
                                    path=(captures[0].relative_to(workspace).as_posix()
                                          if captures else "<capture>"),
                                    label="capture",
                                    terminal=True,
                                ),
                            ),
                        ],
                    ),
                ),
            ],
        ))

    proposal = Proposal(
        kind="pr",
        type="context-import",
        status="pending",
        created_at=now.isoformat(timespec="seconds"),
        revised_at=now.isoformat(timespec="seconds"),
        inbox_sources=inbox_sources,
        capture_sources=capture_sources,
        items=items,
        body=_default_body(),
    )

    out_path = pr_dir / "proposal.md"
    out_path.write_text(dump_proposal(proposal), encoding="utf-8")
    return out_path


def _default_body() -> str:
    return (
        "\n# Proposal\n\n"
        "<!-- §0.5 will be auto-rendered from frontmatter via `forge pr render <pr-id>`. -->\n\n"
        "## Usage\n\n"
        "1. Fill out each item's `disposition`, `extracted`, `rationale`, and `propagation`\n"
        "   in the YAML frontmatter above.\n"
        "2. For MIXED items, expand `sub_items[]` with one entry per sub-source.\n"
        "3. Run `forge proposal validate <pr-id>` to check schema completeness.\n"
        "4. Run `forge pr render <pr-id>` to preview the §0.5 view.\n"
        "5. Once satisfied, present the rendered view to the user for approve/reject.\n\n"
        "Schema reference: `forge.proposal.schema` (Disposition enum + Item/SubItem dataclasses).\n"
    )


def resolve_inbox_arg(workspace: Path, inbox_arg: str | None) -> list[Path]:
    """If `inbox_arg` is None, return every pending inbox file. If it's a path,
    resolve to one file (relative or absolute). If it's a bare filename or id,
    look it up under system/inbox/.
    """
    inbox_dir = workspace / "system" / "inbox"
    if inbox_arg is None:
        if not inbox_dir.is_dir():
            return []
        return sorted([p for p in inbox_dir.glob("*.md") if p.is_file()])

    candidate = Path(inbox_arg).expanduser()
    if candidate.is_absolute() and candidate.is_file():
        return [candidate]
    rel = workspace / inbox_arg
    if rel.is_file():
        return [rel]
    direct = inbox_dir / inbox_arg
    if direct.is_file():
        return [direct]
    if not direct.suffix:
        with_md = inbox_dir / f"{inbox_arg}.md"
        if with_md.is_file():
            return [with_md]
    # try id-prefix match
    if inbox_dir.is_dir():
        matches = sorted(inbox_dir.glob(f"{inbox_arg}*"))
        if len(matches) == 1:
            return [matches[0]]
        if len(matches) > 1:
            raise ValueError(f"ambiguous inbox prefix `{inbox_arg}`: {[m.name for m in matches]}")
    raise FileNotFoundError(f"inbox not found: {inbox_arg}")
