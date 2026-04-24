"""Config: a recipe for compiling sections into one output file.

设计原则：Config 是 Controller，不是 Model。
    Config 说的是 "怎么编、挑哪几段、投给谁"。
    内容本身（包括 preamble、前言、footer）全部进 section。
    如果你想在产物开头加一段介绍文字，写一个 _preface.md section，
    把它放在 sections 列表第一个。

字段：
  name                      — config 名（一般和文件名一致）
  target                    — adapter 名（claude-code / agents-md / ...）
  sections                  — 按顺序挑哪几段 section，name 的列表
  required_sections         — schema 约束，`forge doctor` 会验证
  output_frontmatter        — 产物顶部 YAML frontmatter 的控制字典
  demote_section_headings   — section body 自带 heading 时的降级策略

例：
    ---
    name: personal
    target: claude-code
    sections:
      - _preface       # 如果要 preamble，写成一个 section 挂在前面
      - about-me
      - preferences
      - skills
    required_sections: [about-me]
    output_frontmatter:
      kind: derived
    demote_section_headings: true
    ---
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from forge.compiler.section import _split_frontmatter


@dataclass
class Config:
    """MVC 里的 Controller——只管编译策略，不携带内容。"""

    name: str
    target: str
    sections: list[str]
    required_sections: list[str] = field(default_factory=list)
    output_frontmatter: dict[str, Any] = field(default_factory=dict)
    demote_section_headings: bool = False
    meta: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> Config:
        text = path.read_text(encoding="utf-8")
        frontmatter, _ = _split_frontmatter(text)
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
        req = fm.pop("required_sections", None) or []
        if not isinstance(req, list):
            raise ValueError(f"{path}: `required_sections` must be a list")
        out_fm = fm.pop("output_frontmatter", None) or {}
        if not isinstance(out_fm, dict):
            raise ValueError(f"{path}: `output_frontmatter` must be a mapping")
        demote = bool(fm.pop("demote_section_headings", False))
        # 拒绝已废弃字段，避免静默丢内容
        for deprecated in ("preamble", "postamble", "body"):
            if deprecated in fm:
                raise ValueError(
                    f"{path}: `{deprecated}` is no longer supported in config "
                    f"(Config is MVC's Controller, content belongs in a section). "
                    f"Move this text into sp/section/_preface.md (or similar) and "
                    f"list it in `sections:`."
                )
        return cls(
            name=name,
            target=target,
            sections=[str(s) for s in sections],
            required_sections=[str(s) for s in req],
            output_frontmatter=out_fm,
            demote_section_headings=demote,
            meta=fm,
            path=path,
        )
