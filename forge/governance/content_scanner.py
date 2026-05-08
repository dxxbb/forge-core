"""Internal content scanner: detect uncommitted changes in the personalOS working tree.

Runs `git status --short` on the workspace itself and classifies each changed
path through the classify config. Reports meaningful internal changes that
monitor should surface.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from forge.governance.classify import ClassifyConfig, is_ignored, load_config, build_classify_fn
from forge.governance.events import EventType


@dataclass
class ContentChange:
    path: str
    status: str  # M, A, D, ??, R, etc.
    event_type: EventType


def scan_working_tree(root: Path, config: ClassifyConfig | None = None) -> list[ContentChange]:
    """Scan git working tree for uncommitted changes, classify each."""
    config = config or load_config(root)
    classify = build_classify_fn(config)

    try:
        result = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false",
             "status", "--short", "-u"],
            text=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return []

    if result.returncode != 0:
        return []

    changes: list[ContentChange] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        status = line[:2].strip()
        path = line[3:].strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip('"')

        ev = classify(path)
        if ev == EventType.ignored or ev == EventType.unclassified:
            continue
        changes.append(ContentChange(path=path, status=status, event_type=ev))

    return changes


_STATUS_LABEL = {
    "M": "modified",
    "A": "added",
    "D": "deleted",
    "??": "new",
    "R": "renamed",
}

_EVENT_LABEL = {
    EventType.content_change: "内容变更",
    EventType.project_update: "项目变更",
    EventType.skill_change: "技能变更",
    EventType.preference_change: "偏好变更",
    EventType.ingest: "知识变更",
    EventType.context_source_change: "context source 变更",
    EventType.cc_memory: "CC memory 变更",
    EventType.conversation: "会话变更",
}


def format_monitor_lines(
    root: Path,
    config: ClassifyConfig | None = None,
) -> tuple[list[str], list[str]]:
    """Return (issue_lines, action_lines) for monitor integration."""
    changes = scan_working_tree(root, config)
    if not changes:
        return [], []

    by_type: dict[EventType, list[ContentChange]] = {}
    for c in changes:
        by_type.setdefault(c.event_type, []).append(c)

    issues: list[str] = []
    actions: list[str] = []

    total = len(changes)
    type_summary = ", ".join(
        f"{_EVENT_LABEL.get(ev, ev.value)} {len(cs)}"
        for ev, cs in sorted(by_type.items(), key=lambda x: -len(x[1]))
    )
    issues.append(f"internal content changes: {total} ({type_summary})")

    for ev, cs in sorted(by_type.items(), key=lambda x: -len(x[1])):
        for c in cs[:3]:
            sl = _STATUS_LABEL.get(c.status, c.status)
            actions.append(
                f"internal change: {c.path} ({sl}, {_EVENT_LABEL.get(ev, ev.value)})"
            )
        if len(cs) > 3:
            actions.append(f"  ... and {len(cs) - 3} more {_EVENT_LABEL.get(ev, ev.value)}")

    return issues, actions
