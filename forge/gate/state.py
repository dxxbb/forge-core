"""Gate state: workspace directory layout + manifest.

Layout (v0.2 git-based):
    <root>/
        sp/                    canonical source (user-edited)
        output/                compiled views (visible, git-tracked)
        .forge/                runtime state (gitignored)
            manifest.json      target bindings + metadata
            pending.json       origin tracking (working-tree state)
            bench/             bench snapshots

History lives in git. The approved baseline is HEAD.

Older v0.1 workspaces had `.forge/approved/sp/` (parallel snapshot) and
`<root>/CHANGELOG.md` (parallel append-only file). `forge migrate` (in cli.py)
imports those into git history and removes them.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from forge.gate import _git
from forge.layout import detect


@dataclass
class GateState:
    root: Path

    @property
    def forge_dir(self) -> Path:
        return self.root / ".forge"

    @property
    def output_dir(self) -> Path:
        return detect(self.root).runtime_dir

    @property
    def manifest_path(self) -> Path:
        return self.forge_dir / "manifest.json"

    @property
    def current_sp(self) -> Path:
        return self.root / "sp"

    @property
    def layout(self):
        return detect(self.root)

    @property
    def _legacy_output_dir(self) -> Path:
        """v0.1.0 path. Kept for migration only."""
        return self.forge_dir / "output"

    @property
    def _legacy_changelog_path(self) -> Path:
        """v0.1.0 path. Kept for migration only."""
        return self.forge_dir / "changelog.md"

    @property
    def _legacy_approved_sp(self) -> Path:
        """v0.1.0 path. Kept for migration only."""
        return self.forge_dir / "approved" / "sp"

    @property
    def root_changelog_path(self) -> Path:
        """v0.1.1 path (between layout-flatten and git-based). Kept for migration."""
        return self.root / "CHANGELOG.md"

    def initialized(self) -> bool:
        """A workspace is initialized when a supported source tree exists and root is git."""
        layout = self.layout
        has_source = layout.section_dir.exists() or layout.config_dir.exists()
        return has_source and _git.is_git_repo(self.root)

    def read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, data: dict) -> None:
        self.forge_dir.mkdir(exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def migrate_layout(self) -> list[str]:
        """v0.1.0 → v0.1.1: move .forge/output/ and .forge/changelog.md to root.

        v0.1.1 → v0.2 (drop .forge/approved/, drop CHANGELOG.md as a file, use
        git history) is handled by `forge migrate` in cli.py — it requires a
        commit so it can't run silently.

        Returns lines describing what moved. Empty if nothing to do.
        """
        moved: list[str] = []
        if self._legacy_output_dir.exists() and not self.output_dir.exists():
            shutil.move(str(self._legacy_output_dir), str(self.output_dir))
            moved.append("moved .forge/output/ → output/")
        if self._legacy_changelog_path.exists() and not self.root_changelog_path.exists():
            shutil.move(
                str(self._legacy_changelog_path), str(self.root_changelog_path)
            )
            moved.append("moved .forge/changelog.md → CHANGELOG.md")
        return moved

    def needs_v02_migration(self) -> bool:
        """Does this workspace still have v0.1-era artifacts that v0.2 expects gone?"""
        return self._legacy_approved_sp.exists() or self.root_changelog_path.exists()


def hash_sp(sp_dir: Path) -> str:
    """v0.1 hash function. Kept for diagnostic / migration provenance only —
    v0.2's authoritative hash is `git rev-parse HEAD`."""
    h = hashlib.sha256()
    if not sp_dir.exists():
        return h.hexdigest()
    files = sorted(sp_dir.rglob("*.md"))
    for f in files:
        rel = f.relative_to(sp_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()
