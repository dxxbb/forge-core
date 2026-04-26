"""Track WHY the working tree changed: ingest event, hand edit, watcher, etc.

The diff between approved/sp and current/sp shows WHAT bytes moved. This module
records the SOURCE of the move — was it `forge ingest --from <path>`? Was it
hand-edited in $EDITOR? Did a v0.2 watcher promote a webhook event?

Lifecycle:
    forge ingest, watcher run, etc. → record_event(...)  → .forge/pending.json
    forge approve / forge reject     → clear()           → unlinks the file

`forge review` reads the file (if present) to populate the Origin panel.
If absent, the change is treated as "hand edit since last approve."
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from forge.gate.state import GateState


@dataclass
class OriginEvent:
    """One thing that touched sp/ since last approve."""

    kind: str  # "ingest" | "hand-edit" | "watcher" | "reject-restore"
    at: str  # ISO timestamp
    summary: str  # one-line human-readable description
    details: dict[str, Any] = field(default_factory=dict)
    sections_touched: list[str] = field(default_factory=list)


def record_event(
    root: Path,
    kind: str,
    summary: str,
    details: dict[str, Any] | None = None,
    sections_touched: list[str] | None = None,
) -> OriginEvent:
    """Append one event to the pending-change log."""
    state = GateState(root)
    state.forge_dir.mkdir(exist_ok=True)
    event = OriginEvent(
        kind=kind,
        at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        summary=summary,
        details=details or {},
        sections_touched=sections_touched or [],
    )
    pending = read_pending(root)
    pending.append(event)
    _pending_path(state).write_text(
        json.dumps([asdict(e) for e in pending], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return event


def read_pending(root: Path) -> list[OriginEvent]:
    """Read the current pending-change log. Empty list if no file."""
    state = GateState(root)
    path = _pending_path(state)
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [OriginEvent(**item) for item in raw]


def clear(root: Path) -> None:
    """Delete the pending log. Called by forge approve / forge reject."""
    state = GateState(root)
    path = _pending_path(state)
    if path.exists():
        path.unlink()


def _pending_path(state: GateState) -> Path:
    return state.forge_dir / "pending.json"
