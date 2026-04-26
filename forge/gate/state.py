"""Gate state: workspace directory layout + manifest.

Layout (v0.1.1+):
    <root>/
        sp/                    # canonical source (user-edited)
        output/                # compiled views (visible, git-trackable)
        CHANGELOG.md           # audit trail (visible, git-trackable)
        .forge/                # runtime state (gitignored)
            approved/sp/       # last-approved snapshot
            manifest.json      # hash + targets bindings
            bench/             # bench snapshots

Older workspaces had output/ and changelog under .forge/. `migrate_layout`
moves them out on first encounter.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GateState:
    root: Path

    @property
    def forge_dir(self) -> Path:
        return self.root / ".forge"

    @property
    def approved_dir(self) -> Path:
        return self.forge_dir / "approved"

    @property
    def approved_sp(self) -> Path:
        return self.approved_dir / "sp"

    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    @property
    def changelog_path(self) -> Path:
        return self.root / "CHANGELOG.md"

    @property
    def manifest_path(self) -> Path:
        return self.forge_dir / "manifest.json"

    @property
    def current_sp(self) -> Path:
        return self.root / "sp"

    @property
    def _legacy_output_dir(self) -> Path:
        return self.forge_dir / "output"

    @property
    def _legacy_changelog_path(self) -> Path:
        return self.forge_dir / "changelog.md"

    def initialized(self) -> bool:
        return self.forge_dir.exists() and self.approved_sp.exists()

    def read_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {}
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def write_manifest(self, data: dict) -> None:
        self.manifest_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def migrate_layout(self) -> list[str]:
        """Idempotent: move old `.forge/output/` and `.forge/changelog.md` to root.

        Returns a list of human-readable lines describing what moved (empty
        if nothing needed migrating). Safe to call on every gate operation.
        """
        moved: list[str] = []
        if self._legacy_output_dir.exists() and not self.output_dir.exists():
            shutil.move(str(self._legacy_output_dir), str(self.output_dir))
            moved.append(f"moved .forge/output/ → output/")
        if self._legacy_changelog_path.exists() and not self.changelog_path.exists():
            shutil.move(str(self._legacy_changelog_path), str(self.changelog_path))
            moved.append(f"moved .forge/changelog.md → CHANGELOG.md")
        return moved


def hash_sp(sp_dir: Path) -> str:
    """Stable hash of all files under sp/ (sorted paths, SHA256)."""
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
