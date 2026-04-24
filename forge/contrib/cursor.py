"""Cursor 规则文件适配器：产出 `.cursorrules`。

Cursor 的规则格式比 CLAUDE.md 简单——就是一个纯 markdown 文件，
没 frontmatter、没强制约束。我们把每个 section 当一条规则段落，
加个 H2 标题分段。
"""

from __future__ import annotations

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets.base import TargetAdapter


class CursorAdapter(TargetAdapter):
    name = "cursor"
    default_filename = ".cursorrules"

    def render(self, sections: list[Section], config: Config) -> str:
        parts: list[str] = []
        parts.append(f"# {config.name}")
        parts.append("")
        parts.append(
            f"<!-- 由 forge-core 编译自 sp/section/ + sp/config/{config.name}.md —— 请勿手改 -->"
        )
        parts.append("")
        for sec in sections:
            if sec.type == "wrapper":
                parts.append(sec.body.strip())
                parts.append("")
                continue
            pretty = sec.name.replace("-", " ").replace("_", " ")
            pretty = pretty[0].upper() + pretty[1:] if pretty else pretty
            parts.append(f"## {pretty}")
            parts.append("")
            parts.append(sec.body.strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"
