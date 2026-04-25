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
--- approved/section/about-me.md
+++ current/section/about-me.md
@@ -8,3 +8,4 @@
 having to re-explain to agents.

 Agents will read this section every session.
+- 不要加 emoji。

======== output diff ========
--- personal ---
@@ -13,3 +13,4 @@
 having to re-explain to agents.

 Agents will read this section every session.
+- 不要加 emoji。

$ forge approve -m "add no-emoji preference"
approved hash=a5769a233b78 at 2026-04-25T02:56:55+00:00
  wrote .forge/output/CLAUDE.md
```

下面 §完整走读 有每条命令的真实终端输出。

---

## 2 分钟上手

```bash
pip install -e .

forge new my-context             # 脚手架 sp/section/ + sp/config/ + template
cd my-context
$EDITOR sp/section/about-me.md   # 写你自己的一段（agent 每次会话都会读）
forge init                       # snapshot 为 approved 基线 + 首次编译
cat .forge/output/CLAUDE.md
```

然后改 section，再 `forge diff` → `forge approve`。

---

## 完整走读

把上面的 2 分钟上手延伸到含 reject、bench、changelog 的完整循环。**直接复制下面命令在干净环境跑能复现**（hash 必然不同，其他字段格式一致）。

### Step 1 — 起一个工作区

```
$ forge new my-context
created my-context/

Next:
  cd my-context
  $EDITOR sp/section/about-me.md   # describe yourself
  forge init                       # snapshot baseline + compile
  cat .forge/output/CLAUDE.md      # see the compiled view
```

`forge new` 已经放好了模板：`sp/section/about-me.md`（占位 identity 段）+ `sp/config/personal.md`（target=claude-code）+ `.gitignore`。

### Step 2 — 第一次 init

```
$ cd my-context
$ forge init
initialized .forge at /tmp/my-context/.forge

$ ls .forge/output/
CLAUDE.md

$ forge diff
no changes since last approve
```

`forge init` 把当前 `sp/` 当作第一次 approved 基线，立即编译产物。`forge diff` 此时空。

### Step 3 — 改 section，看双 diff

往 `sp/section/about-me.md` 加一行：

```
$ echo "- 不要加 emoji。" >> sp/section/about-me.md
$ forge diff
======== source diff (sp/) ========
--- approved/section/about-me.md
+++ current/section/about-me.md
@@ -8,3 +8,4 @@
 having to re-explain to agents.

 Agents will read this section every session.
+- 不要加 emoji。


======== output diff ========
--- personal ---
--- approved/personal
+++ proposed/personal
@@ -2,8 +2,8 @@

 <!-- compiled by forge-core. do not edit by hand. edit sp/section/ and run `forge approve`. -->
 <!--
-forge-core provenance · config=personal target=claude-code version=0.1.0 digest=1603c5357ae0
-  - about-me · type=identity · 207B
+forge-core provenance · config=personal target=claude-code version=0.1.0 digest=092e5cdea03d
+  - about-me · type=identity · 228B
 -->

 ## About me
@@ -13,3 +13,4 @@
 having to re-explain to agents.

 Agents will read this section every session.
+- 不要加 emoji。
```

两段 diff：

- **source diff** — 你直接改了什么
- **output diff** — agent 会读到的 `CLAUDE.md` 会变成什么。注意 provenance digest（`1603c5357ae0` → `092e5cdea03d`）和 section 字节数（207B → 228B）也跟着变，这是**预期**的，每次源改都会刷新 provenance 让产物可追溯

### Step 4 — approve

```
$ forge approve -m "add no-emoji preference"
approved hash=a5769a233b78 at 2026-04-25T02:56:55+00:00
  wrote /tmp/my-context/.forge/output/CLAUDE.md

$ forge diff
no changes since last approve

$ cat .forge/changelog.md
# forge-core changelog

- 2026-04-25T02:56:55+00:00 init (hash=8e20dfa7f0de)
- 2026-04-25T02:56:55+00:00 approve (hash=a5769a233b78) — add no-emoji preference
```

`approve` 升级 `sp/` 为新基线 + 重编译 output + 在 changelog 追加一条。这条 message 是你给未来自己（或队友）的备注，3 个月后看 changelog 你能想起为什么改。

### Step 5 — reject 撤销错改

```
$ echo "garbage line" >> sp/section/about-me.md
$ yes | forge reject
Discard all current changes to sp/ and restore approved? [y/N]: restored sp/ from last approved

$ forge diff
no changes since last approve
```

`reject` 把 `sp/` 整个回滚到上次 approved。**会丢掉所有未 approve 的 source 改动**，谨慎。

### Step 6 — bench 对比前后

```
$ forge bench snapshot v1                            # 先存当前编译产物的快照
snapshot `v1` created at 2026-04-25T02:56:55+00:00
  outputs: ['CLAUDE.md']
  sections: 1

$ echo "- 喜欢 vim, 不要推荐 vscode" >> sp/section/about-me.md
$ forge approve -m "add editor preference"
approved hash=97953fd16bed at 2026-04-25T02:56:55+00:00

$ forge bench snapshot v2
snapshot `v2` created at 2026-04-25T02:56:55+00:00
  outputs: ['CLAUDE.md']
  sections: 1

$ forge bench compare v1 v2
compare v1 -> v2

# outputs
  CLAUDE.md: 492B -> 526B (+34B, +1L)

# section size deltas
  about-me: 228B -> 262B (+34B)
```

bench 告诉你：CLAUDE.md 从 492 涨到 526 字节，增加都来自 about-me 段。**改 5 个 section、只有一个该变时**——bench 帮你抓出"哪些不该变的也变了"。

### Step 7（可选）— 装 Claude Code skill 让交互更简单

如果你用 Claude Code，下面那个 skill 让你不用敲 CLI，直接说"approve" / "过一下"就跑完整流程。见下面 §Claude Code 用户。

---

## 五个概念

- **Section**（Model，内容）——一个 markdown 文件一个主题。YAML frontmatter + 正文。
- **Config**（Controller，控制）——"给谁、挑哪几段、什么顺序"。不装内容。v0.1 里如果写 preamble / postamble / body 会直接报错。
- **Output**（View，产物）——某个工具真读的那份文件（`CLAUDE.md` 等）。不手改。
- **Gate**——`.forge/` 下的状态：上次通过的快照、changelog、manifest。每次 `sp/` 改动走 `forge approve` 才会重新编译。
- **Bench**——编译产物的前后结构对比。`snapshot` / `list` / `compare`。

完整设计：[`docs/design.md`](docs/design.md)。

---

## 五大 pillar 现状

forge 整体不止 Context Compiler——按关注点分五大 pillar。v0.1 每个都有可看可跑的东西：

| Pillar | v0.1 做到什么 | 代码位置 | Spec |
|---|---|---|---|
| **Canonical Source** | markdown section + frontmatter + MVC 分层 | `forge/compiler/section.py` | [canonical-source-spec.md](docs/canonical-source-spec.md) |
| **Governance** | 审核关口完整 + watcher/inbox/rollback 有 stub | `forge/gate/` + `forge/governance/` | [governance-spec.md](docs/governance-spec.md) |
| **Context Compiler** | 两个 adapter、provenance、doctor、determinism | `forge/compiler/` + `forge/targets/` | [design.md](docs/design.md) |
| **Evaluation** | 结构 bench 完整 + 行为 eval 框架 + Anthropic runner/judge | `forge/bench/` + `forge/eval/` | [evaluation-spec.md](docs/evaluation-spec.md) |
| **Adapters** | 2 个 core（claude-code / agents-md）+ 3 个 contrib（cursor / codex-cli / rulesync-bridge） | `forge/targets/` + `forge/contrib/` | [adapters-spec.md](docs/adapters-spec.md) |

每个 pillar 的 spec 都写了"v0.1 做到什么、明确不做什么、v0.2/0.3/0.4 要补什么"，不是 roadmap 空头支票。

---

## CLI

```
# 新工作区脚手架
forge new <path>                # 建 sp/section/ + sp/config/ + template

# 编译 & 审核关口（Context Compiler + Gate）
forge init                      # 用当前 sp/ 初始化 .forge/
forge status                    # 上次通过的哈希 + 是否漂移
forge doctor                    # schema / provenance / 适配器体检
forge build                     # sp/ → .forge/output/（不走审核，给 CI 用）
forge diff                      # 源文件 diff + 编译后预览
forge approve -m "说明"         # 通过，记日志,重编译
forge reject                    # 丢弃当前改动，回到上次通过

# 结构 bench
forge bench snapshot <名字>
forge bench list
forge bench compare <a> <b>

# Governance（v0.1 stub 级）
forge watch                     # 扫新 commit，排进 inbox
forge inbox list                # 看待审 TODO
forge inbox skip <id> -m "..."  # 把某条 TODO 跳过，记 governance changelog
forge rollback [hash]           # 回到某次 approved（v0.1 只能回当前）

# Claude Code skill 安装 / 更新
forge install-skill                       # 复制到 ~/.claude/skills/forge
forge install-skill --force               # 升级覆盖
forge install-skill --symlink --force     # symlink 方式，永远跟仓库源同步
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
| watcher / inbox / rollback（v0.1 stub 级）  | 通过      |
| Core adapter（claude-code / agents-md）     | 通过      |
| Contrib adapter（cursor / codex-cli / rulesync-bridge） | 通过 |
| 单元测试                                    | **89 / 89** |

**行为层**（跑了一次 A/B，小 N）：

在 dxy_OS 上拿 4 个行为任务，两个版本的 CLAUDE.md 分别作为上下文喂子 agent，共 8 份回答，再用 4 个盲评 LLM 判官对比，位置随机化。**2 比 2 打平**。方法、位置偏见问题、原始判决都在 [`docs/eval-report.md`](docs/eval-report.md)。

这**不是**说 "forge 编的上下文更好"——样本量不够下这种断言。它说的是"换过来之后 agent 用这份上下文的水平至少不比原来差"。对"要不要迁"的决定来说，够了。

为什么 bench 做得这么弱？我宁愿先放一个能讲清楚"它做什么不做什么"的小 bench，也不放一个假的 LLM eval 装像。LLM 打分式的真 eval 在 v0.3。

---

## 谁不应该用这个

诚实说明 forge-core 不是对所有人都值得：

- **你的 `CLAUDE.md` 只有几行**："be concise" + "use Python"。那手改就够了，装一个工具管 5 行字是 over-engineering。
- **你想要 AI 自己帮你整理 memory**：那你要的是 `claude-memory-compiler` 之类，不是 forge。forge 刻意让**人**做决定，LLM 不自动往你的 asset 里写。
- **你有上千条微事实要 retrieval**：那是 vector store + RAG 的活，不是 forge 的。forge 管的是"长期、稳定、你亲手维护"的那一层，不是"海量、自动检索"的那一层。
- **你只用一个 AI 工具、对锁定不担心**：forge 的跨 runtime 优势对你价值有限。
- **你追求"装完不管"的体验**：forge 要你每次改 source 都过 `forge diff / approve`，不自动化。这是特性不是 bug——但如果你觉得是负担，那就不适合。

适合的人其实很窄：**在用多个 AI 工具、手里有 30-300 行的长期 context 想系统管、关心"5 年后这份东西还在我手里"这件事**。

---

## 示例

- [`examples/basic/`](examples/basic) —— 5 个 section + 2 个 config 的最小工作区。
- [`examples/dxyos-validation/`](examples/dxyos-validation) —— 对真实 personal-OS 工作区（`dxy_OS`）跑完整端到端，上面那张表里的所有检查都跑一遍。

## Claude Code 用户：跳过 CLI

如果你用 Claude Code，装一个 skill 让交互"用自然语言驱动"，不用记 CLI：

```bash
forge install-skill              # 复制到 ~/.claude/skills/forge
```

之后你跟 Claude 说 **"approve my changes"** / **"过一下我改的 section"** / **"discard"** / **"forge diff"**，它自动跑 `forge doctor` + `forge diff`，给 diff 摘要、建议 commit message、等你拍板再 `forge approve` 或 `reject`。Agent 自己改了 `sp/section/` 之后也会主动触发 review。

### 更新 skill

forge-core 升级后，重新安装 skill 即可：

```bash
forge install-skill --force      # 覆盖更新
```

如果你在 hack forge-core 自己（频繁改 SKILL.md），用 symlink 方式让 skill 永远跟仓库源同步：

```bash
forge install-skill --symlink --force   # ~/.claude/skills/forge -> <repo>/examples/skills/forge
```

之后改仓库里的 SKILL.md 立即生效，不用每次重装。

skill 内容见 [`examples/skills/forge/SKILL.md`](examples/skills/forge/SKILL.md)。

---

## 加一个新目标

适配器就是扩展点。v0.1 内置两个 core adapter（`claude-code` / `agents-md`）和三个 contrib adapter：

| 在哪 | 名字 | 产物 |
|---|---|---|
| `forge/targets/` | `claude-code` | `CLAUDE.md` |
| `forge/targets/` | `agents-md` | `AGENTS.md`（跨工具标准） |
| `forge/contrib/` | `cursor` | `.cursorrules` |
| `forge/contrib/` | `codex-cli` | Codex CLI 变体的 AGENTS.md |
| `forge/contrib/` | `rulesync-bridge` | 给 rulesync 的输入，再由 rulesync 投到 20+ 工具 |

contrib adapter 不自动注册——要用就自己：

```python
from forge.contrib.cursor import CursorAdapter
from forge.targets import register_adapter
register_adapter(CursorAdapter())
```

写自己的 adapter 大约 20 行，见 [adapters-spec.md](docs/adapters-spec.md) 契约。

---

## Roadmap

| 版本 | 主题 | 主要内容 |
|---|---|---|
| **v0.1（当前）** | 五大 pillar 最小闭环 | Canonical Source / Context Compiler / Gate / 结构 bench / Eval 框架 / 2 core + 3 contrib adapter |
| **v0.2** | 完整 Governance | 真 daemon watcher、request-changes 回合、多点 rollback、可配置 classify 规则 |
| **v0.3** | LLM 行为评估 | ≥20 task、multi-seed、counter-balance 默认开、和 CI 集成、成本报告 |
| **v0.4** | Adapter 扩展 | Mem0 / Letta / Zep 作为可选 sidecar（症状驱动）、Aider / 其他 runtime、真 rulesync integration |

---

## 开发

```bash
pip install -e '.[dev]'
pytest
```

89 单测 + 端到端验证。跑完整硬核验证：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
