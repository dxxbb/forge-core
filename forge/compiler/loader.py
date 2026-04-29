"""Loader: read sections and configs from a workspace directory layout.

Supported layouts:

    legacy:
        <root>/sp/section/*.md
        <root>/sp/config/*.md

    v0428:
        <root>/context build/sections/*.md
        <root>/context build/config/*.md
"""

from __future__ import annotations

from pathlib import Path

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.layout import detect


def load_sections(root: Path) -> dict[str, Section]:
    """Load all sections, keyed by section name."""
    section_dir = detect(Path(root)).section_dir
    if not section_dir.exists():
        return {}
    out: dict[str, Section] = {}
    for path in sorted(section_dir.glob("*.md")):
        s = Section.from_file(path)
        if s.name in out:
            raise ValueError(
                f"duplicate section name `{s.name}` at {path} "
                f"(already loaded from {out[s.name].path})"
            )
        out[s.name] = s
    return out


def load_config(root: Path, name: str) -> Config:
    """Load a single config by name."""
    config_path = detect(Path(root)).config_dir / f"{name}.md"
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")
    return Config.from_file(config_path)


def load_all_configs(root: Path) -> dict[str, Config]:
    """Load every config in the active workspace layout."""
    config_dir = detect(Path(root)).config_dir
    if not config_dir.exists():
        return {}
    out: dict[str, Config] = {}
    for path in sorted(config_dir.glob("*.md")):
        c = Config.from_file(path)
        if c.name in out:
            raise ValueError(
                f"duplicate config name `{c.name}` at {path} "
                f"(already loaded from {out[c.name].path})"
            )
        out[c.name] = c
    return out
