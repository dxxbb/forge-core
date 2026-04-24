# Adapters pillar 设计

适配器（Adapter）是 forge 五大 pillar 里**最容易外部贡献**的一层。
加一个新 target runtime 就是写一个 20 行左右的类：

```python
class CursorAdapter(TargetAdapter):
    name = "cursor"
    default_filename = ".cursorrules"

    def render(self, sections: list[Section], config: Config) -> str:
        ...
```

然后 `register_adapter(CursorAdapter())`，任何 `target: cursor` 的
config 就会走它——不用 fork core，不用改 compiler 一行。

---

## 契约

```python
class TargetAdapter(ABC):
    name: str                           # 在 config 里 target: <name> 引用
    default_filename: str               # 默认输出文件名（比如 CLAUDE.md）

    @abstractmethod
    def render(self, sections: list[Section], config: Config) -> str:
        """把有序 section 列表编译成目标格式的文本内容。"""

    def filename(self, config: Config) -> str:
        return self.default_filename
```

Adapter 需要自己处理的几件事：

| 行为 | 说明 |
|---|---|
| `config.output_frontmatter` | 如果 config 有 `output_frontmatter: {...}`，在产物顶部 emit YAML frontmatter。可以复用 `forge.targets.claude_code._emit_output_frontmatter`。 |
| `config.demote_section_headings` | 如果 true，section body 里的 leading H1/H2 要 strip，其余 heading 降一级。复用 `forge.targets.claude_code._demote_headings`。 |
| `section.type == "wrapper"` | 原样输出 body，**不** emit `## <name>` 标题，**不** 参与 heading demote。 |
| provenance header | 建议复用 `forge.compiler.provenance.build_block()` 生成机读元数据，用 `render_markdown_header()` 渲染成注释。header 不含当前时间，保证相同输入重复 build 输出同 bytes。 |

除此之外 adapter 做什么格式随意——可以是 markdown、YAML、JSON、INI、甚至二进制。契约就是 `str → str`。

---

## 内置 adapter（v0.1 进 core）

| Adapter | 文件 | 目标 |
|---|---|---|
| `claude-code` | `forge/targets/claude_code.py` | Claude Code 读的 `CLAUDE.md` |
| `agents-md` | `forge/targets/agents_md.py` | 跨工具 `AGENTS.md` 约定（Codex / OpenCode 等） |

这两个作为 "标准实现" 保证进 core，测试覆盖。

---

## contrib adapter（v0.1 ship，但不自动注册）

放在 `forge/contrib/`，示范用，不进默认注册表。要用就自己 `register_adapter()`。

| Adapter | 文件 | 适合什么场景 |
|---|---|---|
| `cursor` | `forge/contrib/cursor.py` | 产出 `.cursorrules`（Cursor 规则） |
| `codex-cli` | `forge/contrib/codex.py` | Codex CLI 读的 AGENTS.md 变体（对排版敏感度更高） |
| `rulesync-bridge` | `forge/contrib/rulesync_bridge.py` | 产出可以喂给 `rulesync` 的文件（再由 rulesync 投到 20+ 工具） |

三个都是**参考实现**，欢迎 fork。rulesync 那个还是 stub 级别（只做 concat，没做 rulesync 的 root/detail/ignore frontmatter），v0.4 再做真 integration。

### 用 contrib adapter 的例子

```python
from forge.contrib.cursor import CursorAdapter
from forge.targets import register_adapter
register_adapter(CursorAdapter())
```

之后 config 文件：

```yaml
---
name: my-cursor-config
target: cursor
sections: [about-me, preferences]
---
```

跑 `forge build` 就会在 `.forge/output/.cursorrules` 产出。

---

## 不在 v0.1 ship 的 adapter

| 方向 | 为什么不做 | 什么时候做 |
|---|---|---|
| **Mem0 / Letta / Zep sidecar** | 外部 memory provider 集成需要真 API key、异步、状态管理——超出 stateless `str → str` 契约 | v0.4，症状驱动：只在你的 SP 长度超过 agent context 限制时才引入 memory backend |
| **Aider 适配器** | Aider 用多文件 `.aider.conf.yml` + `AIDER.md` 的组合，不是单文件产物 | 谁真需要可以贡献，契约扩展到支持 "一个 adapter 产多个文件" |
| **MCP server adapter** | MCP 不是静态文件格式，是运行时协议；不属于"编译产物"这个概念模型 | 不计划做；MCP 用它自己的工具链 |
| **Notion / Linear / Confluence** | 这些是分发而不是 runtime 读取，属于"把 agent context 发给团队"的场景 | 可以用 rulesync bridge 再加一层转发，不需要单独 adapter |

---

## 设计原则

1. **Adapter 是 stateless 纯函数。** 同样的 (sections, config) 输入必须产出同样的 bytes。不做 IO、不做 API 调用、不做时间戳。时间戳只进 manifest / changelog，不进 compiled output。
2. **Adapter 不校验 section 内容。** 校验走 `forge/gate/doctor.py`，那是 schema 层的事。
3. **Adapter 不应该知道 watcher / inbox / bench。** 它就是 "翻译器"，只读上游的 section + config。
4. **Core 保持小。** `forge/targets/` 只放两个"标准实现"，其他都进 `forge/contrib/`。别人贡献的 adapter 也放 contrib，成熟后才考虑升核。

---

## v0.2+ 的 adapter 能力

以下是 adapter 契约可能扩展的方向，但 **v0.1 不做**：

- `filename()` 根据 config 动态返回多个文件名（当前签名是 `Config -> str`，要改成 `Config -> list[tuple[str, str]]` 才能 one-to-many）
- Adapter 级别的配置（比如 "Cursor 规则文件按 glob 分组"）
- Adapter 之间的组合（先 cursor adapter 再 AGENTS.md adapter）
- Binary adapter（产出 `.pdf` / `.docx` 等非文本产物）

这些都是有意义的扩展，但等有真实用户需求再加。v0.1 的最小契约能覆盖 80% 的 runtime 需求。
