"""Gemini Code adapter：产出 GEMINI.md。

产物结构：

    <可选 output_frontmatter YAML>

    # <config.name>

    <!-- forge provenance 注释块 -->

    ## <section-1 name>
    <section-1 body>

    ## <section-2 name>
    <section-2 body>

    ...

每段 section 以 `## <name>` 作为 heading emit。如果开启 demote_section_headings，
section body 自带的 leading heading 会被 strip，其他 heading 全部降一级。
"""

from __future__ import annotations

from forge.targets.base import TargetAdapter
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets.claude_code import ClaudeCodeAdapter


class GeminiCodeAdapter(ClaudeCodeAdapter):
    name = "gemini-code"
    default_filename = "GEMINI.md"
