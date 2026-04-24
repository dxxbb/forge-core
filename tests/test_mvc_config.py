"""Config 是 MVC 里的 Controller，不接内容（preamble/postamble/body）。

内容要走 section（用 `type: wrapper` 标注前言 / 结语这类"不是主体 section"的文字）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from forge.compiler.loader import load_sections, load_config
from forge.compiler.renderer import render


def test_config_rejects_deprecated_preamble(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "sp" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "c.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections: [x]\n"
        'preamble: "some text"\n---\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError) as exc:
        load_config(tmp_path, "c")
    assert "no longer supported" in str(exc.value)
    assert "_preface" in str(exc.value)  # 错误信息给出迁移路径


def test_config_rejects_deprecated_postamble(tmp_path: Path) -> None:
    cfg_dir = tmp_path / "sp" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "c.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections: [x]\n"
        'postamble: "some text"\n---\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(tmp_path, "c")


def test_wrapper_section_renders_without_heading(tmp_path: Path) -> None:
    """type: wrapper 的 section 原样输出 body，不 emit `## <name>` 标题。"""
    sec_dir = tmp_path / "sp" / "section"
    cfg_dir = tmp_path / "sp" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    (sec_dir / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\n这是前言文字。\n",
        encoding="utf-8",
    )
    (sec_dir / "main.md").write_text(
        "---\nname: main\n---\n\n主体内容。\n", encoding="utf-8"
    )
    (cfg_dir / "c.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections:\n  - _preface\n  - main\n---\n",
        encoding="utf-8",
    )
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "c")
    out = render(secs, cfg)

    # wrapper body 出现在产物里
    assert "这是前言文字。" in out
    # 但没有 `## _preface` 这种丑 heading
    heading_lines = [line for line in out.splitlines() if line.startswith("#")]
    assert "## _preface" not in heading_lines
    assert "## _Preface" not in heading_lines
    # 主体 section 正常 emit heading
    assert "## Main" in heading_lines


def test_wrapper_body_not_demoted(tmp_path: Path) -> None:
    """wrapper body 即使在 demote 模式下也保持原样——它不是主体 section。"""
    sec_dir = tmp_path / "sp" / "section"
    cfg_dir = tmp_path / "sp" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)
    (sec_dir / "_note.md").write_text(
        "---\nname: _note\ntype: wrapper\n---\n\n"
        "## 提示\n\n这段文字应保持 H2 不被降级。\n",
        encoding="utf-8",
    )
    (sec_dir / "main.md").write_text(
        "---\nname: main\n---\n\n## 主体小标题\n\n内容\n", encoding="utf-8"
    )
    (cfg_dir / "c.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections: [_note, main]\n"
        "demote_section_headings: true\n---\n",
        encoding="utf-8",
    )
    secs = load_sections(tmp_path)
    cfg = load_config(tmp_path, "c")
    out = render(secs, cfg)

    heading_lines = [line for line in out.splitlines() if line.startswith("#")]
    # wrapper 里的 ## 保持不动
    assert "## 提示" in heading_lines
    # 主体 section 的 H2 被 demote 成 H3（或被 strip——看 demote 实现）
    assert "## 主体小标题" not in heading_lines


def test_mvc_config_only_has_controller_fields() -> None:
    """Config 的字段都应是控制类，不包含任何"内容"字段。"""
    from forge.compiler.config import Config
    from dataclasses import fields

    field_names = {f.name for f in fields(Config)}
    # Controller 字段
    assert "sections" in field_names
    assert "required_sections" in field_names
    assert "target" in field_names
    assert "demote_section_headings" in field_names
    assert "output_frontmatter" in field_names
    # 不应再有的内容字段
    assert "preamble" not in field_names
    assert "postamble" not in field_names
    assert "body" not in field_names
