"""Configurable path → EventType dispatch.

v0.1 hardcoded rules in events.py. v0.2 loads from
`.forge/governance/classify.yaml` with fallback to built-in defaults
matching the current personalOS directory layout.

classify.yaml schema::

    rules:
      - pattern: "user space/daily/"
        event_type: content_change
      - pattern: "workspace/project/"
        event_type: project_update
    ignore:
      - ".obsidian/"
      - ".claude/"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from typing import Callable

import yaml

from forge.governance.events import EventType, ClassifyFn


@dataclass
class ClassifyRule:
    pattern: str
    event_type: EventType


@dataclass
class ClassifyConfig:
    rules: list[ClassifyRule] = field(default_factory=list)
    ignore: list[str] = field(default_factory=list)


_BUILTIN_RULES: list[tuple[str, EventType]] = [
    ("user space/daily/", EventType.content_change),
    ("user space/writing/", EventType.content_change),
    ("user space/profile/", EventType.content_change),
    ("user space/goals/", EventType.content_change),
    ("user space/notes/", EventType.content_change),
    ("workspace/project/", EventType.project_update),
    ("workspace/topic/", EventType.content_change),
    ("workspace/writing/", EventType.content_change),
    ("workspace/whiteboard/", EventType.content_change),
    ("assist config/skill/", EventType.skill_change),
    ("assist config/collaboration preference/", EventType.preference_change),
    ("assist config/work preference/", EventType.preference_change),
    ("public knowledge base/", EventType.ingest),
    ("capture/web clipping/", EventType.ingest),
    ("context build/sections/", EventType.context_source_change),
]

_BUILTIN_IGNORE: list[str] = [
    ".obsidian/",
    ".claude/",
    ".forge/",
    "system/",
    ".git/",
]


def _config_path(root: Path) -> Path:
    return root / ".forge" / "governance" / "classify.yaml"


def load_config(root: Path) -> ClassifyConfig:
    """Load classify.yaml if present, else return built-in defaults."""
    p = _config_path(root)
    if p.exists():
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            return _builtin_config()
        return _parse_config(data)
    return _builtin_config()


def _builtin_config() -> ClassifyConfig:
    rules = [ClassifyRule(pat, ev) for pat, ev in _BUILTIN_RULES]
    return ClassifyConfig(rules=rules, ignore=list(_BUILTIN_IGNORE))


def _parse_config(data: dict) -> ClassifyConfig:
    rules: list[ClassifyRule] = []
    for entry in data.get("rules") or []:
        pat = entry.get("pattern", "")
        raw_ev = entry.get("event_type", "unclassified")
        try:
            ev = EventType(raw_ev)
        except ValueError:
            ev = EventType.unclassified
        rules.append(ClassifyRule(pat, ev))
    ignore = data.get("ignore") or list(_BUILTIN_IGNORE)
    return ClassifyConfig(rules=rules, ignore=ignore)


def build_classify_fn(config: ClassifyConfig) -> ClassifyFn:
    """Build a ClassifyFn from a ClassifyConfig."""

    def classify(path: str) -> EventType:
        for prefix in config.ignore:
            if path.startswith(prefix):
                return EventType.ignored
        for rule in config.rules:
            if path.startswith(rule.pattern):
                return rule.event_type
        return EventType.unclassified

    return classify


def load_classify_fn(root: Path) -> ClassifyFn:
    """Load config and return a ready-to-use ClassifyFn."""
    return build_classify_fn(load_config(root))


def is_ignored(path: str, config: ClassifyConfig) -> bool:
    for prefix in config.ignore:
        if path.startswith(prefix):
            return True
    return False
