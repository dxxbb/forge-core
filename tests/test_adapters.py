"""Target adapter registry + extension path."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets import available_adapters, get_adapter, register_adapter
from forge.targets.base import TargetAdapter


def test_default_adapters_registered() -> None:
    names = set(available_adapters())
    assert "claude-code" in names
    assert "agents-md" in names


def test_get_adapter_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_adapter("nonexistent-12345")


def test_adapters_have_correct_filenames() -> None:
    assert get_adapter("claude-code").default_filename == "CLAUDE.md"
    assert get_adapter("agents-md").default_filename == "AGENTS.md"


def test_user_can_register_custom_adapter(workspace: Path) -> None:
    """An external user can add a new target runtime without touching forge-core."""

    class CursorAdapter(TargetAdapter):
        name = "cursor"
        default_filename = ".cursorrules"

        def render(self, sections: list[Section], config: Config) -> str:
            body = "\n\n".join(f"# {s.name}\n{s.body}" for s in sections)
            return f"# cursor rules for {config.name}\n\n{body}\n"

    register_adapter(CursorAdapter())
    assert "cursor" in available_adapters()

    # Use it end-to-end
    (workspace / "sp" / "config" / "cur.md").write_text(
        "---\nname: cur\ntarget: cursor\nsections:\n  - alpha\n---\n",
        encoding="utf-8",
    )
    secs = load_sections(workspace)
    cfg = load_config(workspace, "cur")
    out = render(secs, cfg)
    assert "cursor rules for cur" in out
    assert "Alpha body content" in out


def test_filename_method_defaults_to_class_attr() -> None:
    adapter = get_adapter("claude-code")
    # filename() is the configurable hook; defaults return the class-level default
    cfg = Config(name="c", target="claude-code", sections=[])
    assert adapter.filename(cfg) == "CLAUDE.md"
