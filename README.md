# forge

> CLI 名 `forge`，PyPI 包名 `context-forge`（`forge-core` 已被占用）。

模型在 commoditize。每隔几个月一版新模型，能力差距收敛。"你用什么模型"的差异化在变小，**你给 AI 的 context** 在变大——你的工作方式、偏好、领域知识、判断原则，是真正长在你身上的资产。

但这份资产现在不像资产。`CLAUDE.md` 里有几行你记不清什么时候加的、为什么加。换工具就重配一次。出问题查不到是哪次改坏的。这不是内容的问题，是**没人管它**。

`forge` 是给这层资产补管理流程的最小工具——一个 review-gated context compiler。

---

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

可以自己在终端跑，也可以粘给你的 agent 让它跑。

装好之后跟 agent（Claude Code / Codex / Cursor 等）说：

> "用 forge 帮我建工作区，把现有的 CLAUDE.md / AGENTS.md 接管起来"

Agent 会建工作区、导入现有内容、跑 review。你只管看结果说 ok 或 reject。

---

## 是什么

**`forge`** 把你的长期内容当**源文件**管，把 agent 真正读到的 `CLAUDE.md` / `AGENTS.md` 当**编译产物**：

```
长期内容（你的 source）  ─→  review gate  ─→  编译产物（agent 读的 view）
preferences / workspace                       CLAUDE.md
knowledge base / skill                        AGENTS.md
                                              .cursorrules ...
```

源文件和产物明确分离。源是你能直接读的 markdown，产物从源编译出来，**不手改**。中间有一道审核关口——每次源变了都展示给你：变了什么、影响哪些产物、最终 agent 行为会怎么变，看清楚再 approve。

推荐的使用方式是在 agent 对话里驱动整个流程：你说改什么，agent 提案、编译、跑 diff，你做审核决策。

---

## 它解决什么问题

把同样一份内容当**资产**管而不是**杂货**管，需要三件事同时成立：

- **可理解** — source 是普通 markdown，不是向量、embedding、或 LLM 整理出来的黑盒摘要。打开就能看懂
- **可解释** — 编译产物里每一行都能追溯到哪个 section、哪次 approve。`forge changelog` 一查就有
- **可控制** — 进入 runtime 前要过 review gate。AI 不能绕过你修改你的 preference 或身份叙事

`CLAUDE.md` 直接手改满足不了这三条。让 LLM 自动整理 memory 也不行——LLM 整理出来的越像别的 LLM 整理出来的，你越没差异化。差异化只能来自**你自己决定留什么、删什么**。

`forge` 提供的就是让"自己决定"成为可能的最小结构：source / gate / compiler / multi-runtime adapter。

---

## 日常长什么样

你更新了工作日志，又存了一篇技术文章的 web clipping。跟 agent 说"forge 一下"：

```
你：forge 一下

Agent：monitor 检测到 2 个变化。生成 proposal：

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     监控:  user space/daily/work-log.md (2048 bytes, modified)
  ══════════════════════════════════════════════════════════════════════

    提取信息    - 工作日志更新（项目 A 测试阶段 / 项目 B 调研中）
    处理结果    📦 ARCHIVE
    理由        日志只是 trail，agent 不需要读到
    传播链路    (空 — 链路在 capture 截止，CLAUDE.md 不动)

  ══ ITEM 2 ══════════════════════════════════════════════════════════
     监控:  capture/web clipping/react-server-components.md
  ══════════════════════════════════════════════════════════════════════

    提取信息    - React Server Components 架构深度解析
                - RSC vs SSR 的本质区别
                - 与现有 react-patterns.md 互补（架构 vs 实践）
    处理结果    ✅ APPLY · 新建 rsc.md + 索引追加
    理由        现有 KB 没有 RSC 架构维度

    传播链路
    └─ public knowledge base/topic/tech/frontend/rsc.md     [新建]
       └─ context build/sections/knowledge base.md          [索引 +1 行]
          ├─ CLAUDE.md                                       [重编译]
          └─ AGENTS.md                                       [重编译]

  总分布: 📦 × 1, ✅ × 1。approve / reject?

你：ok

Agent：approved. CLAUDE.md / AGENTS.md 已重编译。
       knowledge base 段新增一行：

         + - tech/frontend/rsc.md — RSC 架构深度解析（与 react-patterns 互补）

       下次启动 agent，就会基于这条新条目回答 RSC 相关问题。
```

两类变化的关键区别就在传播链：

- **ARCHIVE** — 链路在 capture 截止。文件存了，但 agent 读到的 CLAUDE.md 不变
- **APPLY** — 链路一路传到 CLAUDE.md / AGENTS.md。编译产物多了一行，agent 下次启动行为会变

每个 item 都把"会不会影响最终编译产物"明确画给你看，approve 之前你已经知道结果。

---

## 谁不应该用这个

- **`CLAUDE.md` 只有几行**：手改就够了，`forge` 是 overkill
- **想要 AI 自己帮你整理 memory**：那是 `claude-memory-compiler` 之类。`forge` 刻意让人做最后决定
- **有上千条微事实要 retrieval**：那是 vector store + RAG 的活，不是这个工具
- **追求"装完不管"的体验**：每次源变都要过 review / approve，跳不过去

适合的人：**在用多个 AI 工具、手里有 30+ 行的长期 context、关心 5 年后这份内容还在不在自己手里**。

---

## 核心概念

```
capture/web clipping/         ─┐
user space/daily/              │
workspace/project/             ├─→ forge monitor 检测变化
public knowledge base/         │
~/.claude/projects/*/memory/  ─┘   (agent 自己写的 auto-memory)
         │
         ▼
   forge capture → system/inbox/ → system/pr/proposal.md
         │                              │
         │                              ▼
         │   agent 生成 proposal:
         │   items[] → disposition (APPLY/ARCHIVE/COVERED/...)
         │          → propagation tree (哪些 asset 要改)
         │              │
         ▼              ▼
   你 review → approve / reject
         │
         ▼
   context build/sections/ → forge build → CLAUDE.md / AGENTS.md / ...
         │
         ▼
   forge target install → ~/.claude/CLAUDE.md (auto-sync)
```

- **Capture** — 原始证据（web clipping、日志、workspace-project 上游、agent auto-memory）。只存不改。`forge monitor` 持续监控这五类源, 任何一类有 drift 都会surface 进 inbox 走 review
- **Inbox** — 进入审核流程前的待处理队列
- **Proposal** — 每个监控到的变化是一个 item，agent 分类（APPLY / ARCHIVE / COVERED / DECIDE / NA / MIXED），附 propagation tree
- **Section** — context build 的源文件，按主题分（about user / workspace / knowledge base / preference / skill）
- **Output** — 编译产物（CLAUDE.md / AGENTS.md），不手改，approve 后自动重生成
- **Target** — 把 output 绑到外部路径（如 `~/.claude/CLAUDE.md`），approve 自动同步

---

## CLI 命令

### 核心

```
forge new <path>          # 建工作区
forge build               # section → output 编译
forge review              # 一屏看影响 + diff
forge approve -m "..."    # = git commit + 重编译 + 同步
forge reject              # 回退到上次 approved
forge changelog           # 审计日志
forge rollback [hash]     # 回到任意历史版本
```

### Governance（推荐在 agent 对话中使用）

```
forge monitor             # 扫描工作区全局状态变化
forge capture             # 抓取原始证据
forge proposal new        # 生成 schema-aware proposal
forge proposal validate   # 校验 proposal
forge pr render           # 渲染 §0.5 视图
forge pr done             # 归档 PR
forge inbox done          # 关闭 inbox 条目
```

### 目标绑定 & 工具

```
forge target install <adapter> --to <path>
forge target list / remove
forge bench snapshot / compare    # 结构快照对比
forge self-install                # 绑 forge skill 到 agent runtime
forge update                      # 升级 CLI
```

---

## 适配器

| 名字 | 产物 | 类别 |
|---|---|---|
| `claude-code` | `CLAUDE.md` | core |
| `agents-md` | `AGENTS.md` | core |
| `cursor` | `.cursorrules` | contrib |
| `codex-cli` | AGENTS.md variant | contrib |
| `rulesync-bridge` | rulesync input | contrib |

Core adapter 默认加载，contrib 需要 `register_adapter(...)` 显式启用。写自己的 adapter 约 20 行，见 [`docs/adapters-spec.md`](docs/adapters-spec.md)。

---

## 怎么自己跑 bench

forge 没有也不应该有"通用 benchmark"。你的 context 内容、你常问 agent 的问题，跟别人的不一样，**有意义的 bench 必须自己建**。`forge bench snapshot / compare` 只做结构快照（compile 前后内容有没有丢），不是行为评估。

行为 eval 的最小 recipe：

1. **挑 3–5 个 task**，是你真实会问 agent 的问题，覆盖不同 section（about-user / workspace / preference 等）
2. **准备两份 CLAUDE.md**：一份基线（M，比如手搓的或上个版本），一份待测（F，forge 当前编译的）
3. **每个 task 跑两次**：分别只读 M 或只读 F，agent 不调任何工具，只基于这份内容回答
4. **judge 比较**：人工或第三个 agent 当 judge，盲对比每对答案，记 win/tie/loss

样板 task（替换成你自己的）：

```
- identity-summary:    "用 3 句话总结我是谁、在做什么、当前核心挑战"
- workspace-awareness: "列出我当前最重要的 3 个 project 或 topic"
- grounding-rule:      "我问你某产品的发布时间，你应该首先做什么？"
```

完整跑法见 [`docs/eval-report.md`](docs/eval-report.md) 的 setup。换上你的 task 和你的两份 CLAUDE.md 就能复用。

---

## 当前状态

Alpha。仍在 dogfood 阶段，作者自己用。schema、CLI 接口、目录结构都可能不向前兼容。文档与实现可能有不同步的地方，遇到不一致请以代码为准。

---

## 开发

```bash
pip install -e '.[dev]'
pytest -q
```

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
