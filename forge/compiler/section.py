"""Section: an atomic piece of long-term content.

One markdown file, one concern. Has YAML frontmatter + markdown body.

Frontmatter fields (all optional except name):
  name          — unique identifier, referenced by configs. Defaults to filename stem.
  type          — free-form classification (identity / preference / skill / ...)
  kind          — canonical / derived. `derived` sections are compiled from `upstream` sources.
  updated_at    — ISO 8601 date
  source        — single-pointer provenance (file path, url, conversation id)
  upstream      — list of pointers this section was derived from (strings)
  generated_by  — who/what produced this section (tool name, pipeline id, human)

Any other frontmatter fields are preserved in `meta`.
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
    kind: str | None = None
    updated_at: str | None = None
    source: str | None = None
    upstream: list[str] = field(default_factory=list)
    generated_by: str | None = None
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
        kind = fm.pop("kind", None)
        updated = fm.pop("updated_at", None)
        if updated is not None and not isinstance(updated, str):
            # YAML parses bare dates into datetime.date; keep ISO string for stability.
            updated = updated.isoformat() if hasattr(updated, "isoformat") else str(updated)
        src = fm.pop("source", None)
        upstream_raw = fm.pop("upstream", None) or []
        if not isinstance(upstream_raw, list):
            raise ValueError(f"{path}: `upstream` must be a list, got {type(upstream_raw).__name__}")
        upstream = [str(u) for u in upstream_raw]
        generated_by = fm.pop("generated_by", None)
        # also consume last_rebuild_at if present (dxyOS-style) — keep as updated_at fallback
        if updated is None:
            lr = fm.pop("last_rebuild_at", None)
            if lr is not None:
                updated = lr if isinstance(lr, str) else (
                    lr.isoformat() if hasattr(lr, "isoformat") else str(lr)
                )
        return cls(
            name=name,
            body=body.strip(),
            type=stype,
            kind=kind,
            updated_at=updated,
            source=src,
            upstream=upstream,
            generated_by=generated_by,
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
