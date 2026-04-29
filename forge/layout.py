"""Workspace layout detection.

forge historically used:

    sp/section
    sp/config
    output

The v0428 personalOS design uses:

    context build/sections
    context build/config
    context build/runtime

Keep both layouts working. The compiler/gate code should ask this module where
sections, configs, and runtime artifacts live instead of hard-coding paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspaceLayout:
    name: str
    section_dir: Path
    config_dir: Path
    runtime_dir: Path
    source_paths: tuple[str, ...]
    tracked_paths: tuple[str, ...]
    source_label: str
    runtime_nested_by_target: bool = False

    @property
    def source_root(self) -> Path:
        return self.section_dir.parent


def detect(root: Path) -> WorkspaceLayout:
    """Return the active layout for ``root``.

    Prefer the v0428 layout when either context-build input directory exists.
    Fall back to the legacy sp/output layout.
    """
    root = Path(root)
    context_root = root / "context build"
    if (context_root / "sections").exists() or (context_root / "config").exists():
        return WorkspaceLayout(
            name="v0428",
            section_dir=context_root / "sections",
            config_dir=context_root / "config",
            runtime_dir=context_root / "runtime",
            source_paths=("context build/sections", "context build/config"),
            tracked_paths=("context build",),
            source_label="context build/",
            runtime_nested_by_target=True,
        )
    return WorkspaceLayout(
        name="legacy",
        section_dir=root / "sp" / "section",
        config_dir=root / "sp" / "config",
        runtime_dir=root / "output",
        source_paths=("sp",),
        tracked_paths=("sp", "output"),
        source_label="sp/",
        runtime_nested_by_target=False,
    )


def empty_tree(root: Path, layout_name: str = "legacy") -> None:
    """Create the minimum empty input tree for a layout."""
    if layout_name == "v0428":
        (root / "context build" / "sections").mkdir(parents=True, exist_ok=True)
        (root / "context build" / "config").mkdir(parents=True, exist_ok=True)
    else:
        (root / "sp" / "section").mkdir(parents=True, exist_ok=True)
        (root / "sp" / "config").mkdir(parents=True, exist_ok=True)
