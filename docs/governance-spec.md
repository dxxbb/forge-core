# Governance pillar 设计

Governance 是 forge 五大 pillar 里最先被问到的那个问题——**什么能进系统、为什么进、谁批准的、怎么撤销**。

v0.1 ship 到什么程度，在文末列得很清楚。下面先把完整模型写清楚。

---

## 整条链路

```
修改源文件（手改 / agent 提议 / 外部 ingest）
    │
    ▼
watcher 扫 git log              ◀── v0.1: scan_git(), 一次性扫描
    │
    ▼
inbox（排队 + 分派）           ◀── v0.1: Inbox enqueue/list/skip
    │
    ├── skip（不相关 / 已覆盖）
    │       └─▶ 记 governance/changelog.md
    │
    └── triage → gate
              │
              ▼
          gate.diff 展示预览      ◀── v0.1: forge diff（已完成）
              │
              ├── approve  → 记 changelog、重编译 output
              ├── reject   → 丢弃改动
              └── request-changes → 退回 agent 修改（v0.2）
                            │
                            ▼
                        后续回合
                 ← ← ← ← ← ← ←
              │
              ▼
         rollback 历史跳转     ◀── v0.1: stub（只能回当前）
```

## v0.1 ship 了什么

| 组件                      | 状态  | 位置                                |
|---------------------------|-------|-------------------------------------|
| `gate.diff / approve / reject` | 完整 | `forge/gate/`                       |
| `gate.doctor` 健康检查     | 完整  | `forge/gate/doctor.py`              |
| `Inbox` enqueue/list/skip  | 完整  | `forge/governance/inbox.py`         |
| `scan_git` watcher 一次性扫 | 完整  | `forge/governance/watcher.py`       |
| 路径 → EventType 默认分派  | 完整  | `forge/governance/events.py`        |
| `rollback` 回到当前 approved | 完整（等同 reject） | `forge/governance/rollback.py` |
| `rollback` 回到历史 approved | **stub**（返回诊断） | 同上，v0.2                        |
| 文件系统 daemon watcher     | **无** | v0.2                                |
| request-changes 回合        | **无** | v0.2                                |
| 多 snapshot ring buffer     | **无** | v0.2                                |

## 数据模型

### `.forge/` 目录布局（完整版）

```
.forge/
├── approved/sp/         ← 上次通过的源文件快照（gate）
├── output/              ← 当前编译产物（gate）
├── changelog.md         ← gate 的审计日志（gate）
├── manifest.json        ← 当前 approved hash + 时间戳（gate）
├── bench/<snap>/        ← bench 快照（bench）
└── governance/
    ├── state.json       ← watcher 的 last_seen_commit
    ├── inbox/           ← 待审 TODO 队列
    │   ├── 0001-project_update.md
    │   └── ...
    └── changelog.md     ← governance 自己的审计（skip / watcher run 记录）
```

两个 changelog 分开：
- **`.forge/changelog.md`** —— gate 层（init、approve、reject）
- **`.forge/governance/changelog.md`** —— governance 层（skip、watcher run）

这样翻审计时更清楚每条记录的因果层。

### TODO 文件格式（inbox）

```markdown
---
id: 4
event_type: project_update
commit_sha: 426f4b1
path: 03 workspace/project/forge/onepage.md
created_at: 2026-04-24T12:34:56+00:00
---

auto-queued by `forge watch` from commit 426f4b1
```

Agent 在 triage 时可以编辑 body，写分析、引用决定。

## EventType

六个 MVP 事件类型（dxyOS 实际覆盖过的）：

| EventType          | 触发来源（典型）                       | 下游行为              |
|--------------------|----------------------------------------|-----------------------|
| `conversation`     | 会话沉淀入 memory                      | 走 triage → gate      |
| `cc_memory`        | Claude Code auto-memory 变更           | 走 triage → gate      |
| `pr_revision`      | 已有 PR 的 review 回合（v0.2 才完整）  | 走 request-changes    |
| `ingest`           | 外部素材入知识库                       | 走 triage → gate      |
| `project_update`   | workspace project onepage 变动         | 走 triage → gate      |
| `skill_change`     | skill 目录变动                         | 走 triage → gate      |
| `unclassified`     | 不匹配任何前缀规则                     | 通常 skip             |

分派规则可插拔——`scan_git(root, classify=my_fn)` 传入你自己的路径 → EventType 函数。

## Commit 跳过规则

watcher 主动跳过的 commit：

- Message 里带 trailer：`Approved-by:`、`Rebuilt-by:`、`System-owned-by:`（这些都是 forge / agent 自己产生的 commit，不该被二次 triage）
- 文件 frontmatter 里 `kind: derived` 或 `kind: wrapper` 或 `kind: system`（编译产物 / 包装 / 系统文件）

## v0.1 到 v0.2 的 gap

真正缺的几件事：

1. **Daemon / 事件驱动的 watcher**。v0.1 是 `forge watch` 手动跑。v0.2 要一个可以在后台跑、响应文件系统事件或 git post-commit hook 的版本。
2. **Request-changes 完整回合**。`agent 提议 → 人 review → 要求改 → agent 再提 → 再 review` 的多轮机制，v0.2 做。v0.1 只支持 reject 一次。
3. **多点回滚**。需要 `.forge/approved/` 从"只保留最近一次"升级成环形缓冲区（保留最近 N 次）或 git-based 版本化存储。v0.2 做。
4. **可配置路径分派**。v0.1 的分派规则写死在 `events.py` 里（匹配 dxyOS 目录结构）。v0.2 让它从 `.forge/governance/classify.yaml` 读。
5. **Event triage agents**。每种 EventType 有对应 triage procedure（比如 `cc_memory` 的 triage 要看两条 memory 是否语义重叠）。v0.1 所有 event 都靠人。v0.2 接 subagent triage。

## 用法示例（v0.1 能跑的）

```bash
# 在一个 git 仓里（sp/ 已经初始化）
forge watch
# scanned: 3 proposed change(s)
#   426f4b1 project_update     03 workspace/project/forge/onepage.md
#   7b9e23c skill_change       01 assist/learn and improve/skill/new.md
#   a8f4210 unclassified       random/path.md

forge inbox list
# 0001  project_update     03 workspace/project/forge/onepage.md
# 0002  skill_change       01 assist/learn and improve/skill/new.md
# 0003  unclassified       random/path.md

forge inbox skip 0003 -m "unclassified, not relevant"
# skipped inbox/0003

# 审核剩下的，走 forge diff / approve 流程
```

## 用法示例（v0.2 想做的）

```bash
forge watch --daemon                # 后台跑
forge inbox triage 0001             # 派给一个 subagent 做初步分析
forge pr request-changes 0001 -m "…" # 给 agent 反馈，等下一轮
forge rollback <old-hash>           # 跨多点回滚
```

上面这些是 v0.2 的 target。

---

## 和 `forge/gate/` 的关系

`forge/gate/` 是 governance 里"审核关口"那一小段。governance 在它前面加 watcher + inbox，在它后面加 rollback。

为什么分两个模块：
- `gate/` 的 API 独立且稳定（diff / approve / reject / doctor / build），即使你不用 watcher/inbox，单独用 gate 也够。
- `governance/` 的 API 是 stub 级别，可能在 v0.2 大改。分开放可以让 gate 的接口不被牵连。
