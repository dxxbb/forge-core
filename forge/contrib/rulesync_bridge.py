"""rulesync 桥接适配器：把 section 编译成 `.rulesync/rules/<name>.md`。

这不是真的 rulesync 客户端——只是产出 rulesync 期待的源文件结构，
让你可以用 `forge approve` 当审核关口，然后 `npx rulesync generate`
再投出到 Cursor / Claude Code / Copilot / Gemini 等 20+ 工具。

这样 forge-core 和 rulesync 组合起来就是：
    你改 sp/section/  → forge diff/approve（review 关口）
                    → .rulesync/rules/*.md（作为 rulesync 源）
                    → rulesync generate
                    → 所有工具各自的配置文件

实际使用中：forge-core 的 output 目录里会有 `.rulesync/rules/*.md`，
把它 symlink 或 copy 到项目根的 `.rulesync/` 目录下，然后跑 rulesync。

v0.1 stub：只做一个 section 一个 md 文件的简单映射。rulesync 有更复杂
的 frontmatter（root/detail/ignore/…），留给 v0.4 做真集成。
"""

from __future__ import annotations

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets.base import TargetAdapter


class RulesyncBridgeAdapter(TargetAdapter):
    """注意：这个 adapter 产出的是**单个**文件（和其他 adapter 一样），
    实际使用要么在 config 里声明多份 config 一段一文件，要么改写 adapter
    让它产出目录结构——后者超出 v0.1 的 adapter 契约。

    所以 v0.1 这个 adapter 当作"给 rulesync 准备一个 concatenated 输入"
    的最简版本。把每段 section 用 `---` 分隔符拼在一起，符合 rulesync
    多规则文件的输入预期。
    """

    name = "rulesync-bridge"
    default_filename = "rulesync-input.md"

    def render(self, sections: list[Section], config: Config) -> str:
        parts: list[str] = []
        parts.append(
            f"<!-- forge-core → rulesync bridge: config={config.name}. "
            "把这个文件搬到 .rulesync/rules/ 下，rulesync generate 投到各工具。 -->"
        )
        parts.append("")
        for i, sec in enumerate(sections):
            if sec.type == "wrapper":
                parts.append(sec.body.strip())
                parts.append("")
                continue
            if i > 0:
                parts.append("---")
                parts.append("")
            parts.append(f"# {sec.name}")
            parts.append("")
            parts.append(sec.body.strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"
