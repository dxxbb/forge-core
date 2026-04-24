from pathlib import Path

import pytest

from forge.compiler.loader import load_sections, load_config, load_all_configs
from forge.compiler.renderer import render


def test_load_sections(workspace: Path) -> None:
    secs = load_sections(workspace)
    assert set(secs) == {"alpha", "beta"}


def test_load_config(workspace: Path) -> None:
    cfg = load_config(workspace, "main")
    assert cfg.target == "claude-code"
    assert cfg.sections == ["alpha", "beta"]


def test_load_all_configs(workspace: Path) -> None:
    cfgs = load_all_configs(workspace)
    assert set(cfgs) == {"main"}


def test_render_claude_code(workspace: Path) -> None:
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    out = render(secs, cfg)
    assert "# main" in out
    assert "Alpha body content" in out
    assert "Beta body content" in out
    # section headings auto-generated (name with first letter capitalized)
    assert "## Alpha" in out
    assert "## Beta" in out


def test_render_agents_md(workspace: Path) -> None:
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    cfg.target = "agents-md"
    out = render(secs, cfg)
    assert "Compiled by forge-core" in out
    assert "## Alpha" in out  # agents-md capitalizes
    assert "## Beta" in out


def test_render_missing_section_raises(workspace: Path) -> None:
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    cfg.sections = ["alpha", "nonexistent"]
    with pytest.raises(KeyError):
        render(secs, cfg)


def test_render_unknown_target_raises(workspace: Path) -> None:
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    cfg.target = "does-not-exist"
    with pytest.raises(KeyError):
        render(secs, cfg)


def test_render_deterministic(workspace: Path) -> None:
    """Same inputs → same output bytes."""
    secs = load_sections(workspace)
    cfg = load_config(workspace, "main")
    out1 = render(secs, cfg)
    out2 = render(secs, cfg)
    assert out1 == out2


def test_config_requires_target(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "sp" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "c.md").write_text(
        "---\nname: c\nsections: []\n---\n", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_config(tmp_path, "c")
