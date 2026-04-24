# forge-core

> 你有没有过这种时刻：让 Claude "整理一下" 你的 `CLAUDE.md`，它悄悄把一段重要规则删了，直到三次会话之后你才发现。
>
> 或者：你改了 preference，结果编译出来的 context 莫名胖了一倍，查不出为什么。
>
> 或者：你想把你的 `CLAUDE.md` 分享给队友，却说不清里面每一段是从哪里来的。

如果上面任何一条击中你，这个工具就是为你做的。

**`forge-core`** 是一个小工具，夹在你的长期个人内容和 agent 真正会读的上下文文件（`CLAUDE.md` / `AGENTS.md` / …）之间。它用 build system 对待代码的方式对待这层关系：**canonical source 你来改，compiled artifact 从不手动改，中间有一道 gate 在 ship 之前让你看清即将发生什么**。

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ .forge/output│
│ （你编辑的   │    │ （配方：      │    │ CLAUDE.md    │
│  markdown    │    │  哪些 section,│    │ AGENTS.md    │
│  每个文件    │    │  投给哪个     │    │ …            │
│  一个概念）  │    │  runtime）    │    │ （不要手改） │
└──────────────┘    └──────────────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ forge diff    │ ← 看编译后会变成什么
                    │ forge approve │ ← ship + 记 log + 重编译
                    │ forge reject  │ ← 回滚
                    └──────────────┘
```

状态：**v0.1.0 alpha**。单工作区、本地运行、两个 target adapter。见下面的 [Roadmap](#roadmap)。

---

## 给持怀疑态度的人："`make` + `git` 不就够了吗"

大致可以。如果你已经用 `make` + `git` 把 agent context 的编译链路搭起来了，你大概率不需要这个工具。

`forge-core` 相比一个手搓 `make` + `git` 方案多给你的东西：

1. **语义 diff，不只是文本 diff。** `forge diff` 同时展示 source 变动 AND 每个 compiled target 的变动预览。`git diff` 只看文本，你还得手动重跑 build 才能看每个 runtime 的产物变化，而且每个 target 都要跑一遍。
2. **一个完整的 integrity contract。** 一个 approved snapshot 是整个 `sp/` 目录的 hash；`forge status` 能立即告诉你有没有漂移。
3. **内置结构 bench。** 改了 section，立刻看到哪些 section 涨缩、是否新增删除、每个 output 的总 byte 变动。不用你自己写。
4. **一个可分享的约定。** 任何人看 `sp/section/` + `sp/config/` + `.forge/changelog.md` 就懂整个系统怎么运转。手搓 `make` 脚本只有作者本人看得懂。

**v0.1 明确不是在装的东西：**

- 不是比你的 `make` 更聪明的编译器。编译故意做得很笨。
- v0.1 的 bench 是**结构性的**——比 byte / line / per-section 差异。它**不**告诉你 "agent 变聪明了"。那是 v0.3 的事，要真跑 agent。如果你现在就要 LLM-graded eval，用 `promptfoo` 之类的，`forge-core` 不替代它们。
- 不是一个 runtime memory 系统。不监听会话，不自动捕获，不替你决定。你自己编辑 section，`forge-core` 只保证编辑安全、编译可复现。

如果 "笨编译器 + 语义 diff + 审计日志 + 指向真 eval 的 roadmap" 对你有用，继续读。

---

## 30 秒 demo

```bash
$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - 外部事实要 ground 在 live source。
 - 没被要求就不要加 emoji。
+
+- 改公共配置前，先开 PR。

======== output diff ========
--- personal ---
@@ -19,6 +19,8 @@
 - 没被要求就不要加 emoji。
 
+- 改公共配置前，先开 PR。
+

$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .forge/output/CLAUDE.md
  wrote .forge/output/AGENTS.md
```

核心 loop 就这样。每次 `sp/` 变动同时展示 source diff 和 **compiled output diff**，ship 之前让你看到。如果 compiled diff 不对，`forge reject` 回到上一次 approved 状态。

详细走读见 [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md)（init → edit → diff → approve → bench snapshot → compare 全部真实终端输出）。

---

## 2 分钟上手

```bash
pip install -e .

mkdir -p my-context/sp/section my-context/sp/config
cd my-context

cat > sp/section/about-me.md <<'EOF'
---
name: about-me
type: identity
---

我是一名后端工程师。希望回答简洁。不要加 emoji。
EOF

cat > sp/config/personal.md <<'EOF'
---
name: personal
target: claude-code
sections: [about-me]
---
EOF

forge init
cat .forge/output/CLAUDE.md
```

然后改一下 section，跑 `forge diff`。

---

## 核心概念（5 个小东西）

- **Section** — 一个 markdown 文件 = 一个概念。YAML frontmatter + body。
- **Config** — 配方："给 target X，按这个顺序包含这些 section"。
- **Output** — 一个 runtime 会读的编译产物（`CLAUDE.md` 等）。不手动改。确定性可复现。
- **Gate** — `.forge/` 里的状态：approved snapshot、changelog、manifest。source 每次变动必须经过 `forge approve` 才会重生成 output。
- **Bench** — 编译产物的前后结构对比。`snapshot` / `list` / `compare`。

完整 spec：[`docs/design.md`](docs/design.md)。

---

## CLI

```
forge init                      # 用当前 sp/ 初始化 .forge/
forge status                    # 显示 approved hash 和是否有漂移
forge doctor                    # schema + provenance 健康检查
forge build                     # 把 sp/ 编译到 .forge/output/（无 gate；用于 CI）
forge diff                      # source diff + 编译预览
forge approve -m "message"      # 升级当前 sp/ 为 approved, 重编译，记 log
forge reject                    # 丢弃 sp/ 当前改动，恢复到 approved

forge bench snapshot <name>     # 捕获当前 output + 元数据
forge bench list
forge bench compare <a> <b>     # 两个 snapshot 的结构 diff
```

---

## 硬核验证（不是"能跑就行"）

大多数"个人 AI"工具止步于"我写完了，感觉挺好"。`forge-core` 给出两层具体证据：

**结构层**（每次改动、每次 commit 都跑）：

| 检查                                              | 结果                   |
|--------------------------------------------------|-----------------------|
| 加载 section（包括带空格的文件名）               | 5 / 5                 |
| 带 `required_sections` schema 的 config          | 2 / 2                 |
| `forge doctor`                                    | 0 errors              |
| 编译确定性（两次跑同 bytes）                     | pass                  |
| **vs dxy_OS 自己 SP-compiled CLAUDE.md 的逐行 recall** | **93.5%**        |
| 每个 section body 完整性                         | 5 / 5                 |
| Gate 循环（diff → approve → rollback）           | pass                  |
| Bench 循环（snapshot → compare）                 | pass                  |
| 单元测试                                         | 60 / 60               |

**行为层**（一次真正的 A/B eval，v0.1）：

4 个任务 × 2 个版本 = 8 次 subagent 生成 + 4 次 blind LLM 判官评分，跑在真实 personal-OS vault 上。位置随机化后，**2–2 打平**（master 旧 pipeline vs forge 新 pipeline）。没发现行为回退。完整方法论、位置偏见的诚实讨论、原始判决——见 [`docs/eval-report.md`](docs/eval-report.md)。

**这不是** 在说"forge 编译的 context 客观上更好"——v0.1 没有那个统计功效。这是在说 **"forge 编译的 context 被 agent 使用的效果至少不比手搓 pipeline 差"**。对迁移决策来说，这才是真正需要证明的点。

---

## 2026 生态里的定位

| 工具                     | 它解决什么                                          | forge-core 多做什么                                   |
|--------------------------|-----------------------------------------------------|------------------------------------------------------|
| `rulesync`, `ai-rules-sync` | 在 8+ runtime 间同步 agent rules                 | Review gate + canonical/compiled 分层 + bench        |
| `claude-memory-compiler` | 自动捕获会话 → LLM 整理成 memory                    | 人类 review 在 loop 里；不做隐式 LLM rewrite          |
| `agents-md-generator`    | 从代码库生成 AGENTS.md                              | Source 是长期个人内容，不是代码                      |
| `skills-to-agents`       | 把 SKILL.md 编译成 AGENTS.md                        | 完整多 section canonical source，不只 skill           |
| DSPy / BAML              | 编译 **prompt / schema**                            | 不同层——编译**内容**，不是 prompt                    |
| Google ADK (Context Compaction) | 会话内 context compaction                       | 跨会话 canonical source，不是飞行中压缩              |

没什么阻止你把 forge-core 和这些组合用：可以写 adapter 输出 Cursor rules，可以写 watcher 把 claude-memory-compiler 捕获的内容作为 inbox 输入。见 roadmap。

---

## 示例

- [`examples/basic/`](examples/basic) — 最小 4-section 工作区 + 两个 config。
- [`examples/dxyos-validation/`](examples/dxyos-validation) — 对真实 personal-OS vault（`dxy_OS`）的端到端验证，跑完上面所有"硬核验证"。

## 加一个自定义 target

Adapter 是扩展面。加一个新 runtime 大约 20 行代码：

```python
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets import register_adapter
from forge.targets.base import TargetAdapter

class CursorAdapter(TargetAdapter):
    name = "cursor"
    default_filename = ".cursorrules"

    def render(self, sections: list[Section], config: Config) -> str:
        body = "\n\n".join(f"# {s.name}\n{s.body}" for s in sections)
        return f"# cursor rules for {config.name}\n\n{body}\n"

register_adapter(CursorAdapter())
```

随后任何 `target: cursor` 的 config 都会走这个 adapter。不 fork、不改 core。

---

## Roadmap

- **v0.1（当前）** — compiler core、gate CLI、结构 bench、两个 adapter（`claude-code`、`agents-md`）、provenance + schema + doctor、端到端 fixture（basic + dxyOS 语义等价性）。
- **v0.2** — 完整 governance：watcher、inbox、event-type dispatch、rollback、request-changes 回合。
- **v0.3** — LLM-based eval：agent 在问题集上真跑，前后质量打分。
- **v0.4** — 外部 memory provider（Mem0 / Letta / Zep）作为**可选 sidecar**的 adapter，不入 core。

---

## 开发

```bash
pip install -e '.[dev]'
pytest
```

60 单测 + dxyOS 端到端验证：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT。见 [`LICENSE`](LICENSE)。

---

*英文版见 [`README.en.md`](README.en.md)。*
