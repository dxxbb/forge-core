"""Config: a recipe for compiling sections into one output file.

A config is a markdown file with YAML frontmatter:

    ---
    name: personal-assistant
    target: claude-code
    sections:
      - about-me
      - preferences
      - skill
    preamble: |
      Optional header text that will be inserted before the first section.
    postamble: |
      Optional footer text.
    ---

    Optional free markdown body is appended after all sections.

Fields:
  name      — config identifier (typically matches filename stem)
  target    — adapter name (claude-code / agents-md / ...)
  sections  — ordered list of section names to include
  preamble  — string, rendered before sections
  postamble — string, rendered after sections
  wrappers  — optional per-section heading/wrapping rules (future)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from forge.compiler.section import _split_frontmatter


@dataclass
class Config:
    name: str
    target: str
    sections: list[str]
    preamble: str = ""
    postamble: str = ""
    body: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> Config:
        text = path.read_text(encoding="utf-8")
        frontmatter, body = _split_frontmatter(text)
        fm = yaml.safe_load(frontmatter) if frontmatter else {}
        if not isinstance(fm, dict):
            raise ValueError(f"{path}: frontmatter must be a YAML mapping")
        name = fm.pop("name", None) or path.stem
        target = fm.pop("target", None)
        if not target:
            raise ValueError(f"{path}: config is missing required field `target`")
        sections = fm.pop("sections", None) or []
        if not isinstance(sections, list):
            raise ValueError(f"{path}: `sections` must be a list")
        preamble = fm.pop("preamble", "") or ""
        postamble = fm.pop("postamble", "") or ""
        return cls(
            name=name,
            target=target,
            sections=[str(s) for s in sections],
            preamble=preamble,
            postamble=postamble,
            body=body.strip(),
            meta=fm,
            path=path,
        )
