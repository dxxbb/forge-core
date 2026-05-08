# forge

> CLI 名 `forge`，PyPI 包名 `context-forge`（`forge-core` 已被占用）。

## 上手

在 Claude Code 里跟 agent 说：

> "安装 forge，帮我把现有的 CLAUDE.md 用 forge 管"

Agent 会自动安装 CLI、搭建工作区、导入现有内容、跑 review。你只管看结果说 ok 或 reject。

<details>
<summary>手动安装</summary>

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

</details>

---

## 是什么

**`forge`** 是一个 review-gated context compiler：你的长期内容（偏好、项目状态、知识库、技能）是源文件，agent 真正读到的 `CLAUDE.md` / `AGENTS.md` 是编译产物。中间有一道审核关口——改了什么、影响谁、多大，看清楚再 approve。

推荐的使用方式是在 Claude Code 里跟 agent 对话，agent 驱动整个流程，你做审核决策。

---

## 日常长什么样

你更新了工作日志，又存了一篇技术文章的 web clipping。跟 Claude 说"forge 一下"：

```
你：forge 一下

Claude：monitor 检测到 2 个变化。生成 proposal：

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     监控:  user space/daily/work-log.md (2048 bytes, modified)
  ══════════════════════════════════════════════════════════════════════

    提取信息    - 工作日志更新
                - 项目 A 进入测试阶段
                - 项目 B 调研中
    处理结果    📦 ARCHIVE · 滚动日志，不传播到 context build
    理由        个人工作日志，capture 留存作审计 trail

  ══ ITEM 2 ══════════════════════════════════════════════════════════
     监控:  capture/web clipping/react-server-components.md
  ══════════════════════════════════════════════════════════════════════

    提取信息    - React Server Components 架构深度解析
                - RSC vs SSR 的本质区别
                - 与现有 react-patterns.md 互补（架构 vs 实践）
    处理结果    ✅ APPLY · 新建 rsc.md + react-patterns 交叉引用
    理由        现有 KB 无 RSC 架构维度，这篇填补空白

    传播链路
    └─ public knowledge base/topic/tech/frontend/rsc.md
       ├─ 修改: 新建主题页，提炼文章要点
       └─ context build/sections/knowledge base.md
          ├─ 修改: 索引追加 rsc 条目
          └─ (终止)

  总分布: 📦 × 1, ✅ × 1。approve / reject?

你：ok

Claude：approved. 日志已归档，rsc.md 已创建，
       knowledge base section 已更新，CLAUDE.md 和 AGENTS.md 已重编译。
```

一个 PR 里同时处理了两类变化：

- **ARCHIVE** — 日志是工作记录，存在 capture 里但不影响 agent context
- **APPLY** — web clipping 有新知识，提炼到知识库，propagation tree 追踪影响链一直到编译产物

你只说了两个字。agent 负责 monitor → capture → proposal → build → commit 全流程。

---

## 它解决什么问题

上周你告诉 agent "用 Python，不要 TypeScript"。今天你问同样的问题，它给你 TypeScript。打开 `CLAUDE.md`，preference 那段少了一行。

你没 commit 过这个文件，git blame 查不到是谁改的。agent 不是没 memory，是它的 memory 没人管。

`forge` 给这一层补上管理流程：

- **源文件和编译产物分开** — 你改 `context build/sections/preference.md`，CLAUDE.md 和 AGENTS.md 是编译出来的，不手改
- **改动过审核关口** — 不是改完就生效，是 review 后 approve 才生效
- **一份源，多个 runtime** — 同一份 preference 同时编译到 Claude Code 和 Codex，换工具不重写
- **每次改动有 hash 和审计日志** — 三个月后想知道"这条规则什么时候加的"，`forge changelog` 一查就有

---

## 谁不应该用这个

- **你的 `CLAUDE.md` 只有几行**：手改就够了。
- **你想要 AI 自己帮你整理 memory**：那你要的是 `claude-memory-compiler` 之类。forge 刻意让人做决定。
- **你有上千条微事实要 retrieval**：那是 vector store + RAG 的活。
- **你追求"装完不管"的体验**：forge 要你每次改 source 都过 review / approve。

适合的人：**在用多个 AI 工具、手里有 30+ 行的长期 context 想系统管、关心"这些内容的变更有迹可查"这件事**。

---

## 核心概念

```
capture/web clipping/   ─┐
user space/daily/        ├─→ forge monitor 检测变化
workspace/project/       │
public knowledge base/  ─┘
         │
         ▼
   forge capture → system/inbox/ → system/pr/proposal.md
         │                              │
         │         ┌────────────────────┘
         │         ▼
         │   agent 生成 proposal:
         │   items[] → disposition (APPLY/ARCHIVE/COVERED)
         │          → propagation tree (哪些 asset 要改)
         │         │
         ▼         ▼
   你 review → approve / reject
         │
         ▼
   context build/sections/ → forge build → CLAUDE.md + AGENTS.md
         │
         ▼
   forge target install → ~/.claude/CLAUDE.md (auto-sync)
```

- **Capture** — 原始证据（web clipping、日志、agent memory），只存不改
- **Proposal** — 每个监控到的变化是一个 item，agent 分类为 APPLY / ARCHIVE / COVERED / DECIDE，附 propagation tree 说明影响链
- **Section** — context build 的源文件，一个文件一个主题（about user / workspace / knowledge base / preference / skill）
- **Output** — 编译产物（CLAUDE.md / AGENTS.md），不手改，approve 后自动重生成
- **Target** — 把 output 绑到外部路径，approve 自动同步

---

## CLI 命令

### 核心命令

```
forge new <path>                # 建工作区
forge init                      # 初始化 approved 基线
forge build                     # section → output 编译
forge review                    # 一屏看影响 + diff
forge approve -m "说明"         # = git commit + 重编译 + 同步
forge reject                    # 回退到上次 approved
forge changelog                 # 审计日志
forge rollback [hash]           # 回到任意历史版本
```

### Governance（推荐在 agent 对话中使用）

```
forge monitor                   # 扫描工作区全局状态变化
forge capture                   # 抓取原始证据
forge proposal new              # 生成 schema-aware proposal
forge proposal validate         # 校验 proposal
forge pr render                 # 渲染 §0.5 视图
forge pr done                   # 归档 PR
forge inbox done                # 关闭 inbox 条目
forge synthesize-clipping       # web clipping → KB topic 合成
```

### 目标绑定 & 工具

```
forge target install <adapter> --to <path>
forge target list / remove
forge bench snapshot / compare
forge self-install              # 绑 forge skill 到 agent runtime
forge update                    # 升级 CLI
```

---

## 适配器

| 名字 | 产物 | 说明 |
|---|---|---|
| `claude-code` | `CLAUDE.md` | Claude Code |
| `agents-md` | `AGENTS.md` | 跨工具标准 |
| `cursor` | `.cursorrules` | Cursor |
| `codex-cli` | AGENTS.md variant | OpenAI Codex |
| `rulesync-bridge` | rulesync input | 转接 20+ 工具 |

写自己的 adapter 约 20 行，见 [adapters-spec.md](docs/adapters-spec.md)。

---

## 验证

**488 单测 / 0 失败**。逐行保留率 vs 手搓 `CLAUDE.md`：**91.5%**。行为层 4 task A/B 评估 2:2 打平，方法见 [`docs/eval-report.md`](docs/eval-report.md)。

---

## 开发

```bash
pip install -e '.[dev]'
pytest -q                       # 488 tests, ~27s
```

## License

MIT，见 [`LICENSE`](LICENSE)。

---

*英文版：[`README.en.md`](README.en.md)。*
