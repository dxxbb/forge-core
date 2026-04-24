"""Loader: read sections and configs from a workspace directory layout.

Expected layout:

    <root>/sp/
        section/
            <name>.md
            ...
        config/
            <name>.md
            ...
"""

from __future__ import annotations

from pathlib import Path

from forge.compiler.section import Section
from forge.compiler.config import Config


def load_sections(root: Path) -> dict[str, Section]:
    """Load all sections from <root>/sp/section/*.md, keyed by section name."""
    section_dir = Path(root) / "sp" / "section"
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
    """Load a single config by name from <root>/sp/config/<name>.md."""
    config_path = Path(root) / "sp" / "config" / f"{name}.md"
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")
    return Config.from_file(config_path)


def load_all_configs(root: Path) -> dict[str, Config]:
    """Load every config under <root>/sp/config/*.md."""
    config_dir = Path(root) / "sp" / "config"
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
