# forge-core

`rulesync`（[1k 星](https://github.com/dyoshikawa/rulesync)）做规则同步，`claude-memory-compiler`（[800 星](https://github.com/coleam00/claude-memory-compiler)）做会话抓取——都是单向管道，改动直接写进长期内容。DSPy / BAML 管 prompt 编译，不管长期内容。

中间缺一道关口：改完源文件，看一眼编译产物会变什么，通过了再推给 agent。

`forge-core` 就做这道关口。不做 memory、不做同步、不做 prompt 编译。

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ .forge/output│
│ （源文件，   │    │ （配方：      │    │ CLAUDE.md    │
│  你改）      │    │  挑哪几段、   │    │ AGENTS.md    │
│              │    │  投给谁）     │    │ （不手改）   │
└──────────────┘    └──────────────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ forge diff    │ 发布之前看一眼
                    │ forge approve │ 通过 + 记日志
                    │ forge reject  │ 回滚
                    └──────────────┘
```

当前：**v0.1.0 alpha**，单工作区、本地跑、两个输出适配器。

---

## 一个具体场景

上周你告诉 agent "用 Python，不要 TypeScript"。今天你问同样的问题，它给你 TypeScript。打开 `CLAUDE.md`，preference 那段少了一行——就是"不要 TypeScript"那句。

你没 commit 过这个文件，git blame 查不到是谁改的。agent 不是没 memory，是它的 memory 没人管。

你管代码用 git，改、diff、review、commit，必要时 rollback。管 agent 配置用什么？多数人是手改，改完希望没出事。

`forge-core` 给这一层补上那套流程。不替代 git，补 git 覆盖不到的那半段：从长期内容编译成 agent 真正读的上下文，这中间的 review 和回滚。

---

## "`make` + `git` 不就行？"

差不多。如果你已经自己搭过了，继续用没问题。

我相比手搓多的几件事：

1. `forge diff` 一次给你语义 diff——源文件变了什么，**以及**每个编译目标（CLAUDE.md / AGENTS.md / …）会变成什么。`git diff` 只看文本，每个目标你都要自己重跑 build 再看一次。
2. `sp/` 整棵源文件树有个完整性哈希。`forge status` 立即看出漂移。
3. 自带一个结构 bench（下面讲它能干嘛不能干嘛）。
4. 整套约定别人也能看懂。打开 `sp/section/` + `sp/config/` + `.forge/changelog.md` 就懂。手搓脚本只有作者自己看得懂。

然后要说清楚几件我**没做**的事：

- 编译过程刻意很笨，不比你手写的 `make` 规则聪明。
- v0.1 的 bench 只做结构对比——字节、行数、每段 section 大小。不告诉你 "agent 变聪明了吗"。那要真跑 agent，是 v0.3。现在就想要 LLM 打分，请用 `promptfoo`，我不替代它们。
- 不监听会话、不自动抓、不替你做决定。section 你自己改。

规模上：`forge-core` 是 0 星 alpha；DSPy 是 33.6k 星的成熟项目。我不是在和 DSPy 比，我们根本不在同一件事上。我想正面对比的是 `rulesync` 和 `claude-memory-compiler`——它们是真实对手，我补的就是它们那一步"改了就推"和"LLM 直接写"之间缺的审核。

---

## 30 秒 demo

```bash
$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - 外部事实从当下来源取，不凭记忆。
 - 没被要求不要加 emoji。
+
+- 改公共配置前先走 PR。

======== output diff ========
--- personal ---
@@ -19,6 +19,8 @@
 - 没被要求不要加 emoji。

+- 改公共配置前先走 PR。
+

$ forge approve -m "加一条改公共配置要走 PR 的规则"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .forge/output/CLAUDE.md
  wrote .forge/output/AGENTS.md
```

每个命令的真实输出走读见 [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md)。

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

我是后端工程师。回答请简洁，不要加 emoji。
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

然后改一下 section，再 `forge diff`。

---

## 五个概念

- **Section**（Model，内容）——一个 markdown 文件一个主题。YAML frontmatter + 正文。
- **Config**（Controller，控制）——"给谁、挑哪几段、什么顺序"。不装内容。v0.1 里如果写 preamble / postamble / body 会直接报错。
- **Output**（View，产物）——某个工具真读的那份文件（`CLAUDE.md` 等）。不手改。
- **Gate**——`.forge/` 下的状态：上次通过的快照、changelog、manifest。每次 `sp/` 改动走 `forge approve` 才会重新编译。
- **Bench**——编译产物的前后结构对比。`snapshot` / `list` / `compare`。

完整设计：[`docs/design.md`](docs/design.md)。

---

## CLI

```
forge init                      # 用当前 sp/ 初始化 .forge/
forge status                    # 上次通过的哈希 + 是否漂移
forge doctor                    # schema / provenance / 适配器体检
forge build                     # sp/ → .forge/output/（不走审核，给 CI 用）
forge diff                      # 源文件 diff + 编译后预览
forge approve -m "说明"         # 通过，记日志，重编译
forge reject                    # 丢弃当前改动，回到上次通过

forge bench snapshot <名字>     # 给当前编译产物拍快照
forge bench list
forge bench compare <a> <b>
```

---

## 硬核验证

**结构层**（每次改动都跑）：

| 检查项                                       | 结果       |
|---------------------------------------------|-----------|
| section 加载（文件名带空格也没事）          | 6 / 6     |
| 带 `required_sections` 约束的 config        | 2 / 2     |
| `forge doctor`                              | 0 错      |
| 编译确定性                                  | 通过      |
| 逐行保留率 vs dxy_OS 手搓 SP 编译的 CLAUDE.md | **91.5%** |
| 每段 section 的内容都出现在编译产物        | 6 / 6     |
| 审核循环                                    | 通过      |
| bench 循环                                  | 通过      |
| 单元测试                                    | 65 / 65   |

**行为层**（跑了一次 A/B，小 N）：

在 dxy_OS 上拿 4 个行为任务，两个版本的 CLAUDE.md 分别作为上下文喂子 agent，共 8 份回答，再用 4 个盲评 LLM 判官对比，位置随机化。**2 比 2 打平**。方法、位置偏见问题、原始判决都在 [`docs/eval-report.md`](docs/eval-report.md)。

这**不是**说 "forge 编的上下文更好"——样本量不够下这种断言。它说的是"换过来之后 agent 用这份上下文的水平至少不比原来差"。对"要不要迁"的决定来说，够了。

为什么 bench 做得这么弱？我宁愿先放一个能讲清楚"它做什么不做什么"的小 bench，也不放一个假的 LLM eval 装像。LLM 打分式的真 eval 在 v0.3。

---

## 示例

- [`examples/basic/`](examples/basic) —— 5 个 section + 2 个 config 的最小工作区。
- [`examples/dxyos-validation/`](examples/dxyos-validation) —— 对真实 personal-OS 工作区（`dxy_OS`）跑完整端到端，上面那张表里的所有检查都跑一遍。

## 加一个新目标（比如 Cursor）

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

之后任何 `target: cursor` 的 config 都会走它。不用 fork、不动 core。

---

## Roadmap

- **v0.1（当前）** —— 编译器核心、审核关口 CLI、结构 bench、两个适配器、provenance / schema / doctor、端到端示例（basic + dxyOS 语义等价性 + 行为 A/B）。
- **v0.2** —— 完整审核流：watcher、inbox、事件分派、rollback、改动请求的来回。
- **v0.3** —— 真正的 LLM 行为评估：agent 在固定问题集上跑，前后质量打分。
- **v0.4** —— 外部 memory 服务（Mem0 / Letta / Zep）作为可选 sidecar 的适配器，不进 core。

---

## 开发

```bash
pip install -e '.[dev]'
pytest
```

65 单测 + 端到端验证。跑完整硬核验证：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
