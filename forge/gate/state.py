"""Gate state: .forge/ directory layout + manifest."""

from __future__ import annotations

import hashlib
import json
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
        return self.forge_dir / "output"

    @property
    def changelog_path(self) -> Path:
        return self.forge_dir / "changelog.md"

    @property
    def manifest_path(self) -> Path:
        return self.forge_dir / "manifest.json"

    @property
    def current_sp(self) -> Path:
        return self.root / "sp"

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
