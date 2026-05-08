# forge

> CLI 名 `forge`，PyPI 包名 `context-forge`（`forge-core` 已被占用）。

**`forge`** 是一个审核关口：改完长期内容（section），看一眼编译产物（CLAUDE.md / AGENTS.md）会变什么，通过了再推给 agent。不做 memory、不做同步、不做 prompt 编译。

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

---

## 安装

```bash
# 从 GitHub 安装（推荐）
pipx install git+https://github.com/dxxbb/forge-core.git

# 或用 uv
uv tool install git+https://github.com/dxxbb/forge-core.git

# 验证
forge --version
```

> PyPI 发布后会简化为 `pipx install context-forge`。升级用 `forge update`。

---

## 2 分钟上手

### 方式 A：Claude Code 驱动（推荐）

```bash
forge self-install               # 把 forge skill 绑到 Claude Code
```

打开 Claude Code，说一句话：

> "帮我搭一个 forge 工作区，把我现有的 ~/.claude/CLAUDE.md 用 forge 管"

Claude 会带你走完 8 步（建工作区 → 导入 → review → approve → 绑定到 `~/.claude/CLAUDE.md`）。**全程对话，不敲 CLI**。

### 方式 B：纯 CLI

```bash
# 1. 建工作区
forge new ~/forge-context
cd ~/forge-context

# 2. 看结构
ls sp/section/                              # 5 段 section + _preface
ls sp/config/                               # claude-code.md + agents-md.md

# 3. 初始化
forge init                                  # sp 成为 approved 基线

# 4. 导入现有 context
forge ingest --from ~/.claude/CLAUDE.md     # 自动分类到 5 段 section
                                            # 没 API key? 加 --no-llm

# 5. review
forge review                                # 一屏看 Origin + What changed +
                                            #   Affects + Bench + 完整 diff

# 6. approve
forge approve -m "import existing CLAUDE.md"

# 7. 绑定到真 Claude Code（一次绑定，永久同步）
forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink
```

日常使用：

```bash
$EDITOR sp/section/preferences.md           # 加一条规则
forge review                                # 看影响
forge approve -m "no auto git push"         # 通过，自动同步到 ~/.claude/CLAUDE.md
```

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

## 谁不应该用这个

- **你的 `CLAUDE.md` 只有几行**：手改就够了。
- **你想要 AI 自己帮你整理 memory**：那你要的是 `claude-memory-compiler` 之类，不是 forge。
- **你有上千条微事实要 retrieval**：那是 vector store + RAG 的活。
- **你只用一个 AI 工具、对锁定不担心**：forge 的跨 runtime 优势对你价值有限。
- **你追求"装完不管"的体验**：forge 要你每次改 source 都过 `forge review / approve`。

适合的人：**在用多个 AI 工具、手里有 30-300 行的长期 context 想系统管、关心"5 年后这份东西还在我手里"这件事**。

---

## 五个概念

- **Section**（源文件）——一个 markdown 文件一个主题。YAML frontmatter + 正文。
- **Config**（配方）——"给谁、挑哪几段、什么顺序"。不装内容。
- **Output**（产物）——某个工具真读的那份文件（`output/CLAUDE.md` 等），不手改。
- **Gate**——approve = `git commit`，reject = `git restore`，rollback 任意 hash，audit = `git log`。
- **Target**（绑定）——把某个 output 推到外部路径（如 `~/.claude/CLAUDE.md`），approve 自动同步。

完整设计：[`docs/design.md`](docs/design.md)。

---

## CLI 命令

### 核心命令（任何 forge 工作区）

```
forge new <path>                # 建工作区
forge init                      # 初始化 approved 基线
forge status                    # 上次通过的哈希 + 是否漂移
forge doctor                    # schema / provenance / 适配器体检
forge build                     # sp/ → output/（不走审核，给 CI 用）

forge review                    # 推荐入口：一屏看 Origin/What changed/
                                #   Affects/Bench + 完整 diff
forge review --summary-only     # 只看 panels，跳过 raw diff
forge review --tui              # 键盘驱动 TUI（需真终端）
forge diff                      # 老入口（= git diff HEAD -- sp/）

forge approve -m "说明"         # = git commit + 重编译 + 同步 target
forge reject                    # = git restore HEAD -- sp/ output/
forge changelog                 # 从 git log 渲染审计
forge rollback [hash]           # 回到某次 approved

forge ingest --from <file>      # 导入现有 context，自动分类到 section
```

### 目标绑定

```
forge target install <adapter> --to <path>      # e.g. claude-code --to ~/.claude/CLAUDE.md
forge target install <adapter> --to <path> --mode symlink
forge target list
forge target remove <adapter>
```

### 结构 bench

```
forge bench snapshot <名字>
forge bench list
forge bench compare <a> <b>
```

### Agent skill 管理

```
forge self-install              # 绑 forge skill 到检测到的 agent runtime
forge self-install --dry-run    # 看会做什么
forge update                    # 升级 CLI + refresh skill
```

### personalOS 扩展命令

以下命令需要 personalOS 工作区布局（`capture/` / `system/inbox/` / `system/pr/` 等），普通 forge 工作区不需要：

```
forge monitor                   # 扫描 personalOS 工作区的全局状态变化
forge capture                   # 抓取原始证据到 capture/
forge proposal new              # 从 inbox 生成 schema-aware proposal
forge proposal validate         # 校验 proposal 完整性
forge pr render                 # 渲染 §0.5 视图
forge pr done                   # 关闭 PR，归档到 approve log
forge inbox done                # 关闭 inbox 条目
forge synthesize-clipping       # web clipping → KB topic 合成
forge migrate-onepage           # 升级 onepage schema
```

---

## 适配器

内置两个 core adapter + 三个 contrib adapter：

| 位置 | 名字 | 产物 |
|---|---|---|
| `forge/targets/` | `claude-code` | `CLAUDE.md` |
| `forge/targets/` | `agents-md` | `AGENTS.md`（跨工具标准） |
| `forge/contrib/` | `cursor` | `.cursorrules` |
| `forge/contrib/` | `codex-cli` | Codex CLI 变体的 AGENTS.md |
| `forge/contrib/` | `rulesync-bridge` | 给 rulesync 的输入 |

写自己的 adapter 大约 20 行，见 [adapters-spec.md](docs/adapters-spec.md)。

---

## 示例

- [`examples/basic/`](examples/basic) —— 最小工作区
- [`examples/dxyos-validation/`](examples/dxyos-validation) —— 真实 personal-OS 端到端验证
- [`docs/personalos-v0428.md`](docs/personalos-v0428.md) —— personalOS v0428 layout

---

## 验证

**488 单测 / 0 失败**（v0.1.0 时 88）。逐行保留率 vs 手搓 `CLAUDE.md` 维持 **91.5%**。

行为层跑了一次 4 task A/B，2:2 打平。方法和原始判决在 [`docs/eval-report.md`](docs/eval-report.md)。

---

## Roadmap

| 版本 | 主题 | 主要内容 |
|---|---|---|
| **v0.1** | 五大 pillar 最小闭环 | Canonical Source / Context Compiler / Gate / 结构 bench / Eval 框架 / 5 adapter |
| **v0.2** | git 是底层 | approve = `git commit`，reject = `git restore`，rollback 任意 hash |
| **v0.3–v0.7（当前）** | Governance + personalOS | schema-aware proposal / workspace-project sync / configurable classify / content scanner / PR archive |
| **v0.8** | LLM 行为评估 | ≥20 task、multi-seed、counter-balance、CI 集成 |
| **v0.9** | Adapter 扩展 | Mem0 / Letta / Zep 可选 sidecar、更多 runtime |

---

## 开发

```bash
pip install -e '.[dev]'
pytest -q                       # 488 tests, ~27s
```

---

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
