# forge

> CLI 名 `forge`，PyPI 包名 `context-forge`（`forge-core` 已被占用）。

`rulesync`（[1k 星](https://github.com/dyoshikawa/rulesync)）做规则同步，`claude-memory-compiler`（[800 星](https://github.com/coleam00/claude-memory-compiler)）做会话抓取——都是单向管道，改动直接写进长期内容。DSPy / BAML 管 prompt 编译，不管长期内容。

中间缺一道关口：改完源文件，看一眼编译产物会变什么，通过了再推给 agent。

`forge` 就做这道关口。不做 memory、不做同步、不做 prompt 编译。

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ output/       │
│ （源文件，   │    │ （配方：      │    │ CLAUDE.md    │
│  你改）      │    │  挑哪几段、   │    │ AGENTS.md    │
│              │    │  投给谁）     │    │ （不手改）   │
└──────────────┘    └──────────────┘    └──────────────┘
                           │                    │
                           ▼                    ▼ (forge target install)
                    ┌──────────────┐     ┌──────────────────┐
                    │ forge diff    │     │ ~/.claude/        │
                    │ forge approve │     │  CLAUDE.md        │
                    │ forge reject  │     │ （活产物，approve │
                    └──────────────┘     │  自动同步）        │
                                         └──────────────────┘
```

当前：**v0.1.0 alpha**，单工作区、本地跑、两个输出适配器。

---

## 一个具体场景

上周你告诉 agent "用 Python，不要 TypeScript"。今天你问同样的问题，它给你 TypeScript。打开 `CLAUDE.md`，preference 那段少了一行——就是"不要 TypeScript"那句。

你没 commit 过这个文件，git blame 查不到是谁改的。agent 不是没 memory，是它的 memory 没人管。

你管代码用 git，改、diff、review、commit，必要时 rollback。管 agent 配置用什么？多数人是手改，改完希望没出事。

`forge` 给这一层补上那套流程。不替代 git，补 git 覆盖不到的那半段：从长期内容编译成 agent 真正读的上下文，这中间的 review 和回滚。

---

## "`make` + `git` 不就行？"

差不多。如果你已经自己搭过了，继续用没问题。

我相比手搓多的几件事：

1. `forge diff` 一次给你语义 diff——源文件变了什么，**以及**每个编译目标（CLAUDE.md / AGENTS.md / …）会变成什么。`git diff` 只看文本，每个目标你都要自己重跑 build 再看一次。
2. `sp/` 整棵源文件树有个完整性哈希。`forge status` 立即看出漂移。
3. 自带一个结构 bench（下面讲它能干嘛不能干嘛）。
4. 整套约定别人也能看懂。打开 `sp/section/` + `sp/config/` + `CHANGELOG.md` 就懂。手搓脚本只有作者自己看得懂。

然后要说清楚几件我**没做**的事：

- 编译过程刻意很笨，不比你手写的 `make` 规则聪明。
- v0.1 的 bench 只做结构对比——字节、行数、每段 section 大小。不告诉你 "agent 变聪明了吗"。那要真跑 agent，是 v0.3。现在就想要 LLM 打分，请用 `promptfoo`，我不替代它们。
- 不监听会话、不自动抓、不替你做决定。section 你自己改。

规模上：`forge` 是 0 星 alpha；DSPy 是 33.6k 星的成熟项目。我不是在和 DSPy 比，我们根本不在同一件事上。我想正面对比的是 `rulesync` 和 `claude-memory-compiler`——它们是真实对手，我补的就是它们那一步"改了就推"和"LLM 直接写"之间缺的审核。

---

## 30 秒 demo

```bash
$ forge review --summary-only
══ forge review · proposed change (not yet approved) ══

┌─ Source ─────────────────────────────────────────────
│ Origin:  hand edit (no recorded ingest/event)
│ Touched: 1 section
└──────────────────────────────────────────────────────

┌─ What changed ───────────────────────────────────────
│ • preferences.md: +1 bullet rule
│     572B → 591B  (+19B, +1/-0 lines)
└──────────────────────────────────────────────────────

┌─ Affects ────────────────────────────────────────────
│ Outputs that will rebuild on approve:
│   • output/CLAUDE.md (+19B)  ← Claude Code (every session)
│   • output/AGENTS.md (+19B)  ← Codex / OpenCode / any AGENTS.md-aware tool
│
│ External targets (auto-sync on approve):
│   • /home/me/.claude/CLAUDE.md  [symlink]
└──────────────────────────────────────────────────────

┌─ Bench ──────────────────────────────────────────────
│ preferences         +   19B  (572 → 591)
└──────────────────────────────────────────────────────

$ forge approve -m "add no-emoji preference"
approved hash=a5769a233b78 at 2026-04-25T02:56:55+00:00
  wrote /home/me/forge-context/output/CLAUDE.md
  synced → /home/me/.claude/CLAUDE.md (adapter: claude-code)
```

一屏读完就知道：**哪段改了 / 改的逻辑 / 谁会读到 / 影响多大**。去掉 `--summary-only` 还接着上完整 diff 验证。

绑定到 `~/.claude/CLAUDE.md` 是一次性的 `forge target install claude-code --to ~/.claude/CLAUDE.md`，之后每次 approve 自动同步，不用 `cp` 也不用 `ln -sf`。

下面 §完整走读 有每条命令的真实终端输出。

---

## 2 分钟上手

最快的体验：装 + 自绑定到 agent runtime，然后让 Claude Code 帮你跑。

```bash
# 当前从 GitHub 直接装（推荐）：
pipx install git+https://github.com/dxxbb/forge-core.git
# 或：uv tool install git+https://github.com/dxxbb/forge-core.git

forge self-install                   # 把 forge skill 绑到检测到的 runtime（当前：claude-code）
```

> 后续发到 PyPI 之后会简化为 `pipx install context-forge`（PyPI 包名是 `context-forge`，`forge-core` 已被同名包占用，CLI 仍叫 `forge`）。
>
> 升级用 `forge update`：自动识别 pipx / uv tool / editable，跑对应的 upgrade 命令，再 re-run self-install。
>
> 本地开发：`python3 -m pip install -e '.[dev]'`，然后 `forge self-install`。

打开 Claude Code，跟它说：

> "帮我搭一个 forge 工作区，把我现有的 ~/.claude/CLAUDE.md 用 forge 管"

它会带你完整走 8 步（new → 介绍结构 → 检测现有 → 导入分类 → review → 演示 cross-runtime → approve → 同步到真 Claude Code）。**全程对话，不敲 CLI**。

如果你想自己敲 CLI 看每步做什么，下面 §完整走读 §没装 skill 怎么走 有等价命令。

---

## 完整走读（推荐路径：装 skill，让 Claude 帮你跑）

最自然的体验是装 Claude Code skill 后跟 Claude 对话，让它驱动整个流程。这一节先讲这条路径，下面 §纯 CLI 路径再讲不用 skill 的等价命令。

### 装 skill

```bash
pipx install git+https://github.com/dxxbb/forge-core.git
forge self-install                   # 检测 runtime，写 ~/.claude/skills/forge/SKILL.md（带 managed marker）
```

完事。下次你打开 Claude Code 时，skill 自动加载。

`forge self-install` 是 idempotent 的：再跑一次，没变就 unchanged，源码升级了就 updated；用户自己写过的同名文件不会被吞掉，会报 conflict 让你处理。

### 跟 Claude 说一句话开始

启动 Claude Code 之后，跟它说：

> "帮我搭一个 forge 工作区，把我现有的 ~/.claude/CLAUDE.md 用 forge 管"

或者英文：

> "Set up forge for me, import my existing CLAUDE.md"

Claude 会接管接下来的 8 步，每一步问你一次。**全程在对话里完成，你不需要敲一行 CLI**。

### 它会帮你做什么（8 步）

1. **建工作区**：`forge new ~/forge-context`（路径它会问你）。产出 5 段 SP section（about-me / preferences / workspace / knowledge-base / skills）+ 1 个 wrapper + 2 个 config（claude-code 和 agents-md，**一份源同时编译给 Claude Code 和 Codex 等其他工具**）
2. **介绍结构**：跟你说这些目录是干嘛的，让你建立心智模型
3. **检测现有 context**：扫 `~/.claude/CLAUDE.md` / 项目级 `CLAUDE.md` / `.cursorrules` 等
4. **导入并自动分类**：每份现有文件被分类塞进 5 段 section 里。**这是工作树状态，没 approve**——你像 review PR 一样可以编辑任何分错的地方
5. **展示 review 屏**：跑 `forge review`，一屏铺出来 Origin（"从 ~/.claude/CLAUDE.md 通过 forge ingest 来的"）+ What changed（语义："替换了 5 个 TODO 占位，加了 12 条 bullet rule"）+ Affects（"会出现在 output/CLAUDE.md 和 output/AGENTS.md，被 Claude Code 和 Codex 读"）+ Bench（per-section 字节涨缩，≥50% 标 ⚠）+ 完整 diff。**这就是审核关口**——你不是在审核一份"看不见的东西"
6. **演示 cross-runtime**：让你看到一份 source 同时产出 `output/CLAUDE.md` 和 `output/AGENTS.md`，未来切到 Codex / 别的工具不重建
7. **approve + 写 CHANGELOG**：你确认 commit message 后，Claude 跑 `forge approve`，工作区根的 `CHANGELOG.md` 多一条带 hash + message 的记录。**这就是 provenance**——3 个月后你想知道"这条规则什么时候加的"，grep 这个文件就行（它在工作区根目录，不藏在点目录里，PR 里也直接可见）
8. **绑定到真 Claude Code（一次绑定，永久同步）**：让你确认后跑 `forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink`。从此每次 `forge approve` 自动刷新这个外部位置——你不用记 `cp` 或 `ln -sf`，agent 不替你偷偷写 `~/.claude/`。要改/解绑：`forge target list` / `forge target remove claude-code`

跑完，你有了一个：
- 5 段结构化 source 装着你原本散落的内容
- 完整审核 / 回滚机制可以用一辈子
- 跨 runtime 编译能力（CLAUDE.md + AGENTS.md，加 cursor 只要一个新 config）
- 第一条 changelog（"import existing CLAUDE.md as initial 5 sections"）

下次你想改个 preference，直接 edit `sp/section/preferences.md`，跟 Claude 说 "approve" 或 "过一下"——skill 自动跑 doctor + diff + 让你确认 message + approve + 提示同步到 `~/.claude/CLAUDE.md`。

### 没装 skill 怎么走（纯 CLI 等价路径）

如果你不用 Claude Code，或者想自己跑 CLI 看每条命令做什么：

```bash
# 1. 起工作区
forge new ~/forge-context
cd ~/forge-context

# 2. 看一眼结构
ls sp/section/                              # 5 段 section + _preface
ls sp/config/                               # claude-code.md + agents-md.md

# 3. 第一次编译
forge init                                  # 现在 sp 是 approved 基线
ls output/                                  # CLAUDE.md + AGENTS.md, 都从同源编出
                                            # output/ 在工作区根, 不藏在 .forge/

# 4. 导入现有 CLAUDE.md
forge ingest --from ~/.claude/CLAUDE.md     # 调 Claude API 自动分类到 5 段
                                            # 没 API key? 加 --no-llm 全部塞 workspace.md
                                            # 自己后面拆

# 5. review (推荐入口)
forge review                                # 一屏看清楚: Origin (这次从哪来) +
                                            # What changed (语义概括) + Affects
                                            # (哪些 agent 会读到) + Bench (字节
                                            # 涨缩, 异常增长 ⚠) + 完整 diff
forge review --summary-only                 # 只看 panels, 不要 raw diff
forge diff                                  # 旧入口, 只回答 "字节怎么变"
                                            # (内部就是 git diff HEAD -- sp/)

# 6. (可选) 编辑分错的段
$EDITOR sp/section/preferences.md           # 改完 forge review 看效果

# 7. approve = git commit
forge approve -m "import existing CLAUDE.md as initial 5 sections"
# v0.2: 真的就是 git commit. log 里多一条带 forge-provenance trailer 的提交.
# git log / git diff / git checkout 全部直接可用.

# 8. 看 audit trail
forge changelog                             # 现场从 git log 渲染. 也能直接:
git log -- sp/                              # 任何 git 工具 (lazygit, github, ...) 都看得到

# 9. 一次绑定, 永久同步到真 Claude Code
forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink
# 之后每次 forge approve 自动刷新 ~/.claude/CLAUDE.md, 不用再 cp / ln -sf
```

后续日常使用：

```bash
$EDITOR sp/section/preferences.md           # 加一条 "no auto git push"
forge diff                                  # 双 diff 看影响
forge approve -m "no auto git push"         # ship
```

需要回滚最后一次：`yes | forge reject`（discard working tree 改动，回到上次 approved）。

### bench：测量你改了什么

bench 用来在两次状态间精确对比 output bytes 和 section sizes。**正确顺序**：

```bash
forge bench snapshot before               # 先快照
$EDITOR sp/section/preferences.md         # 编辑
forge approve -m "..."                    # 通过
forge bench snapshot after                # 再快照
forge bench compare before after          # 对比
```

输出告诉你哪个 output 涨缩多少 / 哪个 section 涨缩多少。**改 5 个 section、只有一个该变时**——bench 帮你抓出"哪些不该变的也变了"。

⚠️ 如果你 edit → snapshot → approve → snapshot 这个顺序，section 字节看起来不会变（因为两次快照间 sp/section/ 没动），只 output 字节变。先 snapshot 再编辑。

---

## 五个概念

- **Section**（Model，内容）——一个 markdown 文件一个主题。YAML frontmatter + 正文。
- **Config**（Controller，控制）——"给谁、挑哪几段、什么顺序"。不装内容。v0.1 里如果写 preamble / postamble / body 会直接报错。
- **Output**（View，产物）——某个工具真读的那份文件（`output/CLAUDE.md` 等），在工作区根，不藏。不手改。
- **Gate**——v0.2 直接落到 git：approve = `git commit`（带 `forge-provenance` trailer），reject = `git restore HEAD -- sp/`，approved 基线 = `git rev-parse HEAD`，audit trail = `git log -- sp/`。`.forge/` 只剩 target 绑定 (`manifest.json`) 和 origin tracking (`pending.json`)。
- **Target**（绑定）——把某个 output 推到外部路径（如 `~/.claude/CLAUDE.md`）。`forge target install` 一次绑定，之后每次 approve 自动同步，不用 `cp` 也不用 `ln -sf`。
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
forge build                     # sp/ → output/（不走审核，给 CI 用）
forge review                    # 推荐入口：一屏看 Origin/What changed/
                                #   Affects/Bench + 完整 diff
forge review --summary-only     # 只看 panels，跳过 raw diff
forge review --tui              # 键盘驱动 TUI：a 通过 / r 拒 / e 编辑 / q 退
                                #   (需真终端, 不能在 agent Bash 里跑)
forge diff                      # 老入口（内部 = git diff HEAD -- sp/）
forge approve -m "说明"         # = git commit 带 forge-provenance trailer，
                                #   重编译 output/，自动同步 target
forge reject                    # = git restore HEAD -- sp/ output/
forge changelog                 # 现场从 git log 渲染审计
forge rollback                  # 不带参 = 列所有 sp/ 历史 commit
forge rollback <hash>           # = git checkout <hash> -- sp/ output/
                                #   (任意历史 hash, 不是只能回最近一次)
forge migrate                   # v0.1 工作区一次性升级到 v0.2 git layout

# 把 output 绑到外部位置 (永久同步)
forge target install <adapter> --to <path>      # e.g. claude-code --to ~/.claude/CLAUDE.md
forge target install <adapter> --to <path> --mode symlink   # symlink (推荐)
forge target list                                # 看绑了哪些
forge target remove <adapter>                    # 解绑 (默认保留外部文件)
forge target remove <adapter> --delete-file      # 解绑且删除外部文件

# 结构 bench
forge bench snapshot <名字>
forge bench list
forge bench compare <a> <b>

# Governance（v0.1 stub 级）
forge watch                     # 扫新 commit，排进 inbox
forge inbox list                # 看待审 TODO
forge inbox skip <id> -m "..."  # 把某条 TODO 跳过，记 governance changelog
forge rollback [hash]           # 回到某次 approved（v0.1 只能回当前）

# 自绑定到 agent runtime / 升级
forge self-install                        # idempotent；按需写 ~/.claude/skills/forge/SKILL.md
forge self-install --dry-run              # 看会做什么，不动文件
forge update                              # 自动跑 pipx/uv tool upgrade，再 self-install
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
| 单元测试                                    | **106 / 106** |

**行为层**（跑了一次 A/B，小 N）：

在 dxy_OS 上拿 4 个行为任务，两个版本的 CLAUDE.md 分别作为上下文喂子 agent，共 8 份回答，再用 4 个盲评 LLM 判官对比，位置随机化。**2 比 2 打平**。方法、位置偏见问题、原始判决都在 [`docs/eval-report.md`](docs/eval-report.md)。

这**不是**说 "forge 编的上下文更好"——样本量不够下这种断言。它说的是"换过来之后 agent 用这份上下文的水平至少不比原来差"。对"要不要迁"的决定来说，够了。

为什么 bench 做得这么弱？我宁愿先放一个能讲清楚"它做什么不做什么"的小 bench，也不放一个假的 LLM eval 装像。LLM 打分式的真 eval 在 v0.3。

---

## 谁不应该用这个

诚实说明 forge 不是对所有人都值得：

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
- [`docs/personalos-v0428.md`](docs/personalos-v0428.md) —— 新的 personalOS v0428 layout：`capture -> inbox -> pr -> context build -> runtime`。

## Claude Code 用户：跳过 CLI

如果你用 Claude Code，装一个 skill 让交互"用自然语言驱动"，不用记 CLI：

```bash
forge self-install               # 检测 runtime，写 ~/.claude/skills/forge/SKILL.md
```

之后你跟 Claude 说 **"approve my changes"** / **"过一下我改的 section"** / **"discard"** / **"forge diff"**，它自动跑 `forge doctor` + `forge diff`，给 diff 摘要、建议 commit message、等你拍板再 `forge approve` 或 `reject`。Agent 自己改了 `sp/section/` 之后也会主动触发 review。

### 升级

```bash
forge update                     # 检测 pipx / uv tool / editable，跑对应 upgrade，再 self-install
```

`self-install` 是 idempotent 的：升级后再跑一次只会 refresh 它自己写过（带 managed-by marker）的文件，不会覆盖你手写的同名文件——那种情况会报 `conflict`，要你显式 `--force` 才覆盖。

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
| **v0.1** | 五大 pillar 最小闭环 | Canonical Source / Context Compiler / Gate / 结构 bench / Eval 框架 / 2 core + 3 contrib adapter（self-contained, 跟 git 无关） |
| **v0.2（当前）** | git 是底层 | approve = `git commit`，reject = `git restore`，rollback 任意历史 hash，audit = `git log`。删 `.forge/approved/sp/` 和独立 CHANGELOG.md 文件。`forge migrate` 把 v0.1 工作区一键升上来。 |
| **v0.3** | 完整 Governance | 真 daemon watcher、request-changes 回合、可配置 classify 规则、跨工具同步 |
| **v0.4** | LLM 行为评估 | ≥20 task、multi-seed、counter-balance 默认开、和 CI 集成、成本报告 |
| **v0.5** | Adapter 扩展 | Mem0 / Letta / Zep 作为可选 sidecar、Aider / 其他 runtime、真 rulesync integration |

---

## 开发

```bash
pip install -e '.[dev]'
pytest -q
```

跑完整硬核验证：

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
