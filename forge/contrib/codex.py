"""Codex CLI 适配器：产出 `AGENTS.md`（Codex 专用变体）。

Codex CLI 读 AGENTS.md 的约定和通用 agents-md 基本一致，但实测下来
Codex 对排版敏感度更高：

- 喜欢每段 section 开头有一行 "## <Name>"
- 对 HTML 注释（`<!-- ... -->`）处理不如 `>` blockquote 稳定

所以这个适配器跟 agents-md 主要区别是：provenance 头用 blockquote，
section 标题统一大写首字母，结尾有一个空行缓冲。
"""

from __future__ import annotations

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets.base import TargetAdapter


class CodexCLIAdapter(TargetAdapter):
    name = "codex-cli"
    default_filename = "AGENTS.md"

    def render(self, sections: list[Section], config: Config) -> str:
        parts: list[str] = []
        parts.append(f"# {config.name}")
        parts.append("")
        parts.append(
            f"> 由 forge 编译自 `sp/section/` + `sp/config/{config.name}.md`。"
        )
        parts.append("> 请勿手改此文件——修改源文件后跑 `forge approve`。")
        parts.append("")
        for sec in sections:
            if sec.type == "wrapper":
                parts.append(sec.body.strip())
                parts.append("")
                continue
            pretty = sec.name.replace("-", " ").replace("_", " ").title()
            parts.append(f"## {pretty}")
            parts.append("")
            parts.append(sec.body.strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"
