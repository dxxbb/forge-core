"""Section: an atomic piece of long-term content.

One markdown file, one concern. Has YAML frontmatter + markdown body.

Frontmatter fields:
  name (required)       — unique identifier, used by configs to reference this section
  type (optional)       — free-form classification (identity / preference / skill / ...)
  updated_at (optional) — ISO 8601 date
  source (optional)     — provenance pointer (file path, url, conversation id, ...)

Any other fields are preserved in `meta`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Section:
    name: str
    body: str
    type: str | None = None
    updated_at: str | None = None
    source: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> Section:
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        fm = yaml.safe_load(frontmatter) if frontmatter else {}
        if not isinstance(fm, dict):
            raise ValueError(f"{path}: frontmatter must be a YAML mapping")
        name = fm.pop("name", None) or path.stem
        stype = fm.pop("type", None)
        updated = fm.pop("updated_at", None)
        if updated is not None and not isinstance(updated, str):
            # YAML parses bare dates into datetime.date; keep ISO string for stability.
            updated = updated.isoformat() if hasattr(updated, "isoformat") else str(updated)
        src = fm.pop("source", None)
        return cls(
            name=name,
            body=body.strip(),
            type=stype,
            updated_at=updated,
            source=src,
            meta=fm,
            path=path,
        )

    @property
    def byte_size(self) -> int:
        return len(self.body.encode("utf-8"))

    @property
    def line_count(self) -> int:
        return self.body.count("\n") + (1 if self.body else 0)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a markdown file into (frontmatter_yaml, body).

    Supports the standard `---\n...\n---\n` delimiter. If no frontmatter, returns ("", text).
    """
    if not text.startswith("---"):
        return "", text
    lines = text.split("\n")
    if len(lines) < 2:
        return "", text
    # Find closing ---
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm = "\n".join(lines[1:i])
            body = "\n".join(lines[i + 1 :])
            return fm, body
    return "", text
