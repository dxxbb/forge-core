"""contrib adapter 的单测。

contrib adapter 不自动注册，要自己 register_adapter。这里验证：
- 能注册
- 能走 render 产出合理的内容
- 尊重 wrapper section 约定
"""

from __future__ import annotations

from pathlib import Path

from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render
from forge.contrib.cursor import CursorAdapter
from forge.contrib.codex import CodexCLIAdapter
from forge.contrib.rulesync_bridge import RulesyncBridgeAdapter
from forge.targets import register_adapter, available_adapters


def _setup(tmp_path: Path, target: str) -> None:
    sec = tmp_path / "sp" / "section"
    cfg = tmp_path / "sp" / "config"
    sec.mkdir(parents=True, exist_ok=True)
    cfg.mkdir(parents=True, exist_ok=True)
    (sec / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\n介绍文字。\n", encoding="utf-8"
    )
    (sec / "about-me.md").write_text(
        "---\nname: about-me\ntype: identity\n---\n\n我是 dxy。\n", encoding="utf-8"
    )
    (sec / "preferences.md").write_text(
        "---\nname: preferences\ntype: preference\n---\n\n- 简洁\n- 中文\n",
        encoding="utf-8",
    )
    (cfg / "c.md").write_text(
        f"---\nname: c\ntarget: {target}\n"
        f"sections:\n  - _preface\n  - about-me\n  - preferences\n---\n",
        encoding="utf-8",
    )


def test_cursor_adapter(tmp_path: Path) -> None:
    register_adapter(CursorAdapter())
    assert "cursor" in available_adapters()

    _setup(tmp_path, "cursor")
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "c")
    out = render(secs, cfg)

    # 产物开头是配置名
    assert out.startswith("# c")
    # wrapper body 原样出现，没有 "## _preface" 标题
    assert "介绍文字。" in out
    assert "## _preface" not in out
    # 主体 section 有标题
    assert "## About me" in out
    assert "## Preferences" in out
    # 内容在
    assert "我是 dxy。" in out
    assert "- 简洁" in out


def test_codex_adapter(tmp_path: Path) -> None:
    register_adapter(CodexCLIAdapter())
    assert "codex-cli" in available_adapters()

    _setup(tmp_path, "codex-cli")
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "c")
    out = render(secs, cfg)

    # 用 blockquote 做 provenance 头
    assert "> 由 forge 编译" in out
    # Title-case section headings
    assert "## About-Me" in out or "## About Me" in out
    # 内容在
    assert "我是 dxy。" in out


def test_rulesync_bridge(tmp_path: Path) -> None:
    register_adapter(RulesyncBridgeAdapter())
    assert "rulesync-bridge" in available_adapters()

    _setup(tmp_path, "rulesync-bridge")
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "c")
    out = render(secs, cfg)

    # 带桥接说明注释
    assert "forge → rulesync bridge" in out
    # 多段 section 用 --- 分隔
    assert "\n---\n" in out
    # section 名作为 H1（rulesync 风格）
    assert "# about-me" in out
    assert "# preferences" in out


def test_adapters_respect_wrapper_type(tmp_path: Path) -> None:
    """所有 contrib adapter 都应尊重 type: wrapper（body 原样输出，不加 heading）。"""
    register_adapter(CursorAdapter())
    register_adapter(CodexCLIAdapter())

    for target in ("cursor", "codex-cli"):
        _setup(tmp_path, target)
        secs = load_sections(tmp_path)
        cfg = load_config(tmp_path, "c")
        out = render(secs, cfg)
        # 介绍文字出现
        assert "介绍文字。" in out
        # 但没有 ## _preface 或 ## Preface 这种标题
        heading_lines = [l for l in out.splitlines() if l.startswith("#")]
        assert not any("preface" in h.lower() for h in heading_lines)

        # 清理 tmp 以便下次 iter 用同名 section
        for f in (tmp_path / "sp" / "section").glob("*.md"):
            f.unlink()
        for f in (tmp_path / "sp" / "config").glob("*.md"):
            f.unlink()
