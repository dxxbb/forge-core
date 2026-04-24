# forge-core

> 上周你告诉 agent "用 Python，不要 TypeScript"。它听懂了，之后一直 Python。
>
> 今天你问同一类问题，它给你 TypeScript。你打开 `CLAUDE.md`，发现 preference 那段少了一行——就是"不要 TypeScript"那句。
>
> 谁改的？什么时候改的？为什么改？你从没 commit 过这个文件，`git blame` 查不到。
>
> 这不是 "agent 缺 memory" 的问题。你给了它 memory。问题是 **这份 memory 没人管**。

你管代码用 git——改、diff、review、commit、必要时 rollback。你管 agent 的配置文件（`CLAUDE.md` / `AGENTS.md`）用什么？多数人的答案是"我手改，改完祈祷没出事"。相当于生产环境裸改代码还不 commit。

**`forge-core`** 是给这一层补上那套流程的小工具。不替代 git——补 git 覆盖不到的那半段：**从你长期积累的内容编译成 agent 真正读的那份上下文** 这中间的 review 和回滚。

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ .forge/output│
│ （源文件：   │    │ （配方：      │    │ CLAUDE.md    │
│  每个 md     │    │  挑哪几段、   │    │ AGENTS.md    │
│  一个主题，  │    │  投给哪个     │    │ …            │
│  由你手改）  │    │  工具）       │    │ （别手改）   │
└──────────────┘    └──────────────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ forge diff    │ ← 发布之前看一眼
                    │ forge approve │ ← 通过 + 记日志 + 重编译
                    │ forge reject  │ ← 回滚
                    └──────────────┘
```

当前状态：**v0.1.0 alpha**。单工作区、本地跑、两个输出适配器。路线见 [Roadmap](#roadmap)。

---

## 给持怀疑态度的人

这一层其实已经有不少工具在做：

- **`rulesync`**（[~1k stars](https://github.com/dyoshikawa/rulesync)）—— 把你的 agent 规则在 20+ 个工具之间同步。**改了就直接推，没人审核**。
- **`claude-memory-compiler`**（[~800 stars](https://github.com/coleam00/claude-memory-compiler)）—— 自动抓会话 → LLM 整理成 memory。**LLM 直接写进你的 memory 文件，没有 review step**。
- **`DSPy`**（[33.6k stars](https://github.com/stanfordnlp/dspy)）/ **`BAML`** —— 编译 prompt / schema 逻辑。**是完全不同的一层**，管的是"agent 怎么思考"，不是"agent 读哪份上下文"。
- **Google ADK Context Compaction** —— 会话内的压缩。**在途优化，不管跨会话的源头内容**。

`forge-core` 做的是这里面没人做的那一件事：**在长期内容和 agent 实际读的产物之间，放一道你能看见的审核关口。** 它不是"又一个 memory 工具"，不是"又一个 sync 工具"。它就是**关口**。

规模上说句实话：`forge-core` 是 0 star 的 alpha，DSPy 已经是 33.6k stars 的成熟项目。我不是在和 DSPy 比——我们做的根本不是同一件事。我想要和 `rulesync` / `claude-memory-compiler` 做对比：它们非常好，它们在做我不做的事，我只是想把它们"改了就推"的那一步改成"改了能看一眼再推"。

---

### "我用 `make` + `git` 不就行了？"

大致可以。如果你已经自己用 `make` + `git` 搭起来了，继续用没问题。

`forge-core` 相对你手搓的那套，多出来的几件事：

1. **语义 diff，不是文本 diff。** `forge diff` 同时告诉你：源文件改了什么，以及**每一个编译目标**（CLAUDE.md、AGENTS.md、…）会变成什么样。`git diff` 只看文本，每个目标你都要自己重跑 build 再对比一遍。
2. **源文件整棵树有一个完整性哈希。** 一次 approve = `sp/` 整棵树的 SHA256。`forge status` 能立刻看出有没有漂移。
3. **结构 bench 内置。** 改完 section 之后立刻看到哪一段涨了、哪一段缩了、总体涨多少字节。不用自己写脚本。
4. **是一套别人也能看懂的约定。** 任何人打开 `sp/section/` + `sp/config/` + `.forge/changelog.md` 都能读懂。手搓的 `make` 脚本只有作者自己看得懂。

**v0.1 要讲清楚几件它不装的事：**

- 不比你手写的 `make` 规则聪明，编译过程刻意做得很笨。
- v0.1 里的 bench **只做结构对比**：字节数、行数、每段 section 大小。它**不**告诉你 "agent 是不是变聪明了"。后者要跑真 agent 才能测，那是 v0.3 的事。LLM 打分式的评估现在请用 `promptfoo` 之类的，我不替代它们。
- 不是运行时 memory 系统。不监听会话、不自动抓取、不替你做决定。section 是你自己改，`forge-core` 只让"改"这件事变安全，让编译可复现。

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

核心循环就这一个：每次改 `sp/`，同时把"源文件变化"和"编译后每个目标会变成什么样"摆在你面前，都发生在"通过"之前。如果编译后的样子不对，`forge reject` 就回到上次通过的状态。

每个命令的真实输出走读：[`docs/demo-walkthrough.md`](docs/demo-walkthrough.md)。

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

然后改一下 section，再跑 `forge diff`。

---

## 五个核心概念（都很小）

- **Section** —— 一个 markdown 文件、一个主题。带 YAML frontmatter + 正文。设计上是 MVC 的 Model（**内容**）。
- **Config** —— 一份配方："给哪个工具，按什么顺序挑哪几段"。设计上是 MVC 的 Controller（**控制**，不装内容）。
- **Output** —— 某个工具真正读的那份编译产物（`CLAUDE.md` 等）。MVC 的 View（**产物**，从不手改）。
- **Gate** —— `.forge/` 下的状态目录：上次通过的快照、变更日志、manifest。每次源文件改动必须走 `forge approve` 才会重新编译。
- **Bench** —— 编译产物的前后结构对比。三个命令：`snapshot`、`list`、`compare`。

完整设计见 [`docs/design.md`](docs/design.md)。

---

## CLI

```
forge init                      # 基于当前 sp/ 初始化 .forge/
forge status                    # 看上次通过的哈希，以及当前有没有漂移
forge doctor                    # 对 schema、provenance、适配器做体检
forge build                     # 把 sp/ 编译到 .forge/output/（不走审核，给 CI 用）
forge diff                      # 源文件 diff + 编译后预览
forge approve -m "说明"         # 把当前 sp/ 作为新基线，重编译，写日志
forge reject                    # 丢弃 sp/ 的当前改动，回到上次通过的状态

forge bench snapshot <名字>     # 给当前编译产物 + 元数据拍一个快照
forge bench list
forge bench compare <a> <b>     # 两个快照的结构对比
```

---

## 硬核验证（不是"我写完了感觉不错"）

大多数"个人 AI"工具到"写完了感觉不错"就停了。`forge-core` 给两层具体证据：

**结构层**（每次改动都跑，可以自己复现）：

| 检查项                                              | 结果        |
|-----------------------------------------------------|-------------|
| section 加载（文件名带空格也没事）                 | 6 / 6       |
| 带 `required_sections` 约束的 config                | 2 / 2       |
| `forge doctor`                                      | 0 错        |
| 编译确定性（两次跑出同样的字节）                    | 通过        |
| **和 dxy_OS 自己 SP 编译出的 CLAUDE.md 逐行对比的保留率** | **91.5%** |
| 每段 section 的内容都出现在编译产物里              | 6 / 6       |
| 审核循环（diff → approve → rollback）               | 通过        |
| Bench 循环（snapshot → compare）                    | 通过        |
| 单元测试                                            | 60 / 60     |

**行为层**（真跑了一轮 A/B 评估，v0.1 版）：

在一份真实 personal-OS 工作区（`dxy_OS`）上，拿 4 个行为任务，让两个版本的 CLAUDE.md 分别作为上下文、交给子 agent 回答，一共 8 份回答；再用 4 个盲评的 LLM 判官对比每组，位置做了随机化。最终比分：**2 比 2 打平**。没发现行为上的回退。完整方法、位置偏见问题、原始判决都在 [`docs/eval-report.md`](docs/eval-report.md)。

注意：这**不是**说 "forge 编的上下文客观上更好"——v0.1 样本量不够做这种断言。它说的是 **"换成 forge 之后，agent 用这份上下文的水平，至少不比原来手搓的 pipeline 差"**。对"要不要迁过来"这个决定，这才是真正要证明的那个点。

---

## 示例

- [`examples/basic/`](examples/basic) —— 最小的 5-section 工作区 + 两个 config。
- [`examples/dxyos-validation/`](examples/dxyos-validation) —— 对一份真实 personal-OS 工作区（`dxy_OS`）做端到端验证，"硬核验证" 表里的检查会全部跑一遍。

## 加一个新目标（比如 Cursor）

适配器就是扩展点。加一个新运行环境大约 20 行：

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

任何 `target: cursor` 的 config 都会走你这个适配器。不用 fork、不用动 core。

---

## Roadmap

- **v0.1（当前）** —— 编译器核心、审核关口 CLI、结构 bench、两个目标适配器（`claude-code`、`agents-md`）、provenance + schema + doctor、端到端示例（basic + dxyOS 的语义等价性 + 行为 A/B）。
- **v0.2** —— 完整审核流：watcher、inbox、按事件类型分派、rollback、改动请求的来回。
- **v0.3** —— 真正的 LLM 行为评估：让 agent 跑一组固定问题，对比前后质量。
- **v0.4** —— 外部 memory 服务（Mem0 / Letta / Zep）作为**可选 sidecar** 的适配器，不进 core。

---

## 开发

```bash
pip install -e '.[dev]'
pytest
```

60 个单测 + 端到端验证。跑一遍完整硬核验证：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
