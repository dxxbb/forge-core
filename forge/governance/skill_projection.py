"""Skill projection checks for personalOS v0428 workspaces.

The governed skill source layer lives under ``assist config/skill/``. The
runtime-visible projection is pointer-only in ``context build/sections/skill.md``.
This module checks only skills explicitly linked from the skill index; it does
not require every scratch file in the skill directory to be projected.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from forge.compiler.section import Section
from forge.layout import detect


_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+\.md)\)")


@dataclass(frozen=True)
class SkillProjectionGap:
    skill_path: str
    section_path: str
    missing_upstream: bool
    missing_pointer: bool

    @property
    def message(self) -> str:
        missing: list[str] = []
        if self.missing_upstream:
            missing.append("upstream")
        if self.missing_pointer:
            missing.append("body pointer")
        return (
            f"skill projection gap: {self.skill_path} missing from "
            f"{self.section_path} ({', '.join(missing)})"
        )


def find_skill_projection_gaps(root: Path) -> list[SkillProjectionGap]:
    """Return index-declared skills missing from the compiled skill section.

    This is intentionally personalOS-layout-specific and narrow:
    ``assist config/skill/index.md`` is the declaration source, and
    ``context build/sections/skill.md`` is the projection target.
    """
    root = Path(root)
    if detect(root).name != "v0428":
        return []

    index = root / "assist config" / "skill" / "index.md"
    section_path = root / "context build" / "sections" / "skill.md"
    if not index.is_file() or not section_path.is_file():
        return []

    declared = _declared_skill_paths(root, index)
    if not declared:
        return []

    try:
        section = Section.from_file(section_path)
    except Exception:
        return []
    section_text = section_path.read_text(encoding="utf-8")
    upstream = {u.strip() for u in section.upstream if u.strip()}
    section_rel = section_path.relative_to(root).as_posix()

    gaps: list[SkillProjectionGap] = []
    for rel in declared:
        missing_upstream = rel not in upstream
        missing_pointer = rel not in section_text
        if missing_upstream or missing_pointer:
            gaps.append(
                SkillProjectionGap(
                    skill_path=rel,
                    section_path=section_rel,
                    missing_upstream=missing_upstream,
                    missing_pointer=missing_pointer,
                )
            )
    return gaps


def format_doctor_lines(root: Path) -> list[str]:
    return [gap.message for gap in find_skill_projection_gaps(root)]


def format_monitor_lines(root: Path) -> tuple[list[str], list[str]]:
    gaps = find_skill_projection_gaps(root)
    if not gaps:
        return [], []
    issues = [f"skill projection gaps: {len(gaps)}"]
    actions = [gap.message for gap in gaps[:5]]
    if len(gaps) > 5:
        actions.append(f"  ... and {len(gaps) - 5} more skill projection gap(s)")
    return issues, actions


def _declared_skill_paths(root: Path, index: Path) -> list[str]:
    text = index.read_text(encoding="utf-8")
    out: list[str] = []
    seen: set[str] = set()
    for target in _MD_LINK_RE.findall(text):
        if "://" in target or target.startswith("#"):
            continue
        target_path = (index.parent / target).resolve()
        try:
            rel = target_path.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel.endswith("/index.md") or not (root / rel).is_file():
            continue
        if rel not in seen:
            seen.add(rel)
            out.append(rel)
    return out
