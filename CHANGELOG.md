# Changelog

记录 `forge-core` 的所有显著变动。

## 0.20.0 (Machine-owned Owner Surface) — 2026-08-24

- 后台 Run Contract 提供唯一 Owner-Facing Projection：默认静默，确需心跳时只能原样发送机器文本。
- close 从最终 Closure Snapshot 生成唯一 `OWNER-FACING SUMMARY`，包含 final state、Run、工作树、commit、Selection Coverage、Candidate Conclusion 和剩余单元。
- 真实一句话验收使用八维证据表；任一硬失败或证据不足都不能判为通过。
- 增加 [ADR-0012](docs/adr/0012-machine-owned-owner-facing-projection.md)。

## 0.19.0 (Authority-matched Preference Evidence) — 2026-08-24

- 全局 Preference Authority 的 `repeated` Candidate 必须提供两个不同 Evidence Event、两个不同 operational context 中的 owner 准确纠偏原话。
- 同一工作流反复失败只能支持该工作流的 Skill、代码、测试或状态资产，不能自动上升为全局偏好。
- 历史卡缺少当前权威证据时保留为 `legacy-unqualified`，不进入 Owner Review 或 Candidate Conclusion。
- 增加 [ADR-0011](docs/adr/0011-authority-matched-preference-evidence.md)。

## 0.18.1 (Run-Owned Sink Receipt) — 2026-08-24

- 同一 Run 的多个 Review Unit 更新同一状态 sink 时，各 disposition 保留自己的语义 note 与当时 digest；close 按 sink 验证最后一次正式 receipt，最后 receipt 之后的漂移仍拒绝。
- 避免为了通过 close 机械重写某条 disposition，从而破坏它原本解释“为什么更新这份资产”的审计语义。

## 0.18.0 (Qualified Review and Run-Owned Settlement) — 2026-08-24

### Changed

- Candidate Qualification 与 lifecycle 分轴：不符合现行合同的历史卡标记 `legacy-unqualified`，只保留审计，不进入 Owner Review 或 Candidate Conclusion。
- 合格 Candidate 的 Run Contract 返回结构化 Review Card，明确真实事件、已有覆盖、资产适配、晋升理由、准确 patch、未来影响和裁决问题。
- Codex Memory 从 Task Group 收紧为 Task Review Unit；无法归属 Task 的组级内容形成独立 Group Summary，单任务旧 checkpoint 仅在摘要完全一致时兼容迁移。
- `covered` 强制保存真实 claim、locator、excerpt；Canonical Source 改按 tracked/authoritative 属性判断，不再维护有限顶层 allowlist。
- Run 保存 dirty baseline，`volatile-state` 只接受 Run ledger 或 stale-check 后的 Run-Owned Write，close 原子提交本轮拥有的状态 sink。
- 后台筛选片最多 3 个独立单元，默认 Owner Candidate budget 为 1；Forge 主 Skill 聚焦 Run，初始化和 legacy 流程按需安装为 references。

### Tests

- 新增旧 Candidate 审计隔离、结构化 Review Card、Task/Group Summary 单元、covered 内容回执、dirty baseline、digest stale-check、Run-Owned close commit 和 Skill bundle self-install 回归。

## 0.17.0 (Attention, Receipts, and Closure Truth) — 2026-08-24

0.16.0 的一句话隔离验收仍在后台进度中泄露 Observation 细节,又允许裸路径冒充 covered/volatile-state 去向,并让持久 Run 报告与 close CLI 分别保留 158/157 两套计数。本版把三个症状统一收口到 owner 注意力、去向回执和收口快照合同。

### Changed

- `classify-*` 改为 owner `silent`;必要心跳只能表达仍在运行和当前是否出现 owner decision,不再报告处理数、剩余数或任何单元语义。
- `covered` 只接受当前 checkout 内现存、Git tracked、非私密的权威 Canonical Source;拒绝 runtime projection、scratch/output/temp、capture/system 和外部仓库。
- `volatile-state` 除同一权威路径门禁外,必须证明本 Run 真实修改了状态文件或存在 `origin=run:<id>` ledger 回执;未变化的已有状态应记 covered。
- Run close commit 后生成唯一 Closure Snapshot,把同一份 Selection Coverage、Candidate Conclusion、剩余单元和最终状态写回该 Run commit并返回 CLI。
- Agent Memory sink 搜索合同明确禁止读取或搜索 private/secret/credentials 路径。

### Tests

- 新增静默 heartbeat 合同、五类非权威 covered sink、volatile-state 真实写入回执和 post-commit Closure Snapshot 一致性测试。

## 0.16.0 (Bounded Observations and Checkout Authority) — 2026-08-24

0.15.0 的一句话隔离验收没有再制造高风险 Candidate,但仍把成功任务内容塞进 Observation,并因 detached worktree 自行切到 canonical personalOS。两者都说明模型判断不能独自承担后台池质量和工作区权限边界。

### Changed

- Observation 准入收紧为真实 `owner-correction|observed-failure|unresolved-conflict|owner-deferred`,并要求 `source_context`、`repeat_if` 与 `route_gap`。
- 单次成功调研、一般专业原则、项目特定决定、假设风险和“也许以后有用”不再进入 Observation;raw evidence 保留在来源系统。
- `run next` 明示后台进度只允许处理数、剩余数和是否出现 owner decision,禁止 source title、disposition、主题、理由和 Observation 细节。
- CLI 拒绝从当前 checkout 显式操作同一仓库的 sibling worktree;detached worktree 被视为有效隔离根。
- 黑盒验收改为八维全通过:触发路径、工作区权限、来源真实性、分流/观察质量、review worthiness、交互负担、状态真实性、成本收口。证据不足即失败,不匹配固定句子。

### Tests

- 新增 Observation admission 与跨 worktree root fail-closed 行为测试,并更新 Run Contract/CLI 对齐测试。
- [ADR-0008](docs/adr/0008-unresolved-signal-observation-admission.md) 与 [ADR-0009](docs/adr/0009-current-checkout-authority.md) 记录语义和权限边界。

## 0.14.0 (Event-grounded Review Cards) — 2026-08-24

第一次自然对话验收暴露出两个相连错误:同一 thread 的 Task Group 与 rollout summary 被当成两个独立事件;owner 对一次任务的具体要求被标成长期明确要求。最终 review 又把完整候选压缩成一句规则,owner 看不到为什么要审。

### Changed

- Observation/Candidate 将稳定 `event_ids` 与 evidence pointer 分开保存;独立事件数只按 event id 计算。
- Candidate ground 收紧为 `repeated|owner-directed|high-risk`;owner-directed 必须保存明确要求未来长期沉淀的 owner 原话,high-risk 必须说明可验证不变量与失败条件。
- Candidate 创建必须提供来源情境、现有资产覆盖与缺口、晋升理由、未来行为影响和准确裁决问题;原有范围、排除项、patch 和验证继续保留。
- `run next` 要求 Agent 用自然语言呈现完整 decision context,禁止只复述 proposal;评价看信息维度,不匹配固定措辞。
- 历史 Observation/Candidate 缺 event id 时保守计为一个 legacy event,不按证据文件数补造经历。

### Tests

- 新增同一事件多 pointer、owner-directed 原话门禁、high-risk 不变量/失败条件和完整 review card 合同测试。
- 全量回归:657 passed,3 skipped。

- [ADR-0006](docs/adr/0006-event-grounded-review-cards.md) 记录 Evidence Event 与 owner decision sufficiency。

## 0.13.0 (Semantic Review Units) — 2026-08-23

连续真实 Run 证明“每批最多 10 个文件”仍是错误边界：Codex provider 把任务主题组、聚合索引、持续增长的历史流和数百 MB 归档会话混在同一文件列表中；整批一条 disposition 会掩埋差异，而候选池暂时为零又会被误说成“没有候选”。本版把候选筛选的真值下沉到 Review Unit 与 Selection Coverage。

### Added

- Codex Memory 以 `MEMORY.md` Task Group 为 Review Unit；Claude Memory 以非索引 memory 文件为单元。
- Source Batch 同时受 10 单元与 128 KiB 限制；聚合索引/raw history/archived sessions 单独报告排除计数。
- `forge run next` 每次返回一个 `classify-source-item`；`run disposition --item` 强制逐单元分流。
- `run status/close` 新增 `selection_coverage`、`candidate_conclusion`、`unprocessed_review_units`；有 backlog 时候选结论只能是 `unknown`。
- Run 持久报告使用 close 时刷新后的同一份剩余计数；CLI 明确回报 scoped commit。

### Fixed

- 不再允许多个性质不同的 Memory 文件共用一次 `closed/covered`。
- 已跟踪的 `.forge/agent_memory_state.json` 纳入 Run scoped commit；真正 gitignored side state 仍不提交。
- 修复 Run 文件、终端输出和最终回复可能分别报告 628/627/“没有提交”的事实漂移。

- [ADR-0005](docs/adr/0005-review-units-and-candidate-conclusion.md) 记录 Review Unit 和全局候选结论。

## 0.12.0 (Deterministic Source Settlement) — 2026-08-23

真实 Run 证明“Source Signal 必须有 disposition”仍不足以稳定交互：聚合计数会在会话中变化，Memory 没有持久 cursor，剪藏写了去向后仍可能重复报警，Agent 也会临场选择不同处理范围。本版把批次、来源结算、唯一下一步和最终状态下沉到 CLI。

### Added

- `Source Batch`：Agent Memory 每批最多 10 个文件，Web clipping 每批最多 5 个文件；digest 只由批次内路径和内容决定。
- provider-specific `Source Settlement`：Memory 非 defer disposition 推进 seen checkpoint；clipping 结算写回 marker，`covered` 强制指向已有 canonical asset。
- `forge run next` 返回唯一的 Run Contract，包括当前 action、批次文件、范围约束和剩余候选预算。
- `run close` 区分 `complete / batch-complete / incomplete`，并机器核验 Run 是否关闭、工作树 clean/dirty 与剩余来源数。
- [ADR-0004](docs/adr/0004-deterministic-source-settlement.md) 记录稳定批次与结算合同。

### Changed

- 重复 `run open` 保留已打开 Run 的原批次；会话期间新到的同类文件留给下一轮，不再替换 input 或使 disposition 失效。
- Web clipping 只通过有界 Source Batch 进入 Run，不再同时作为普通 capture evidence 重复出现。
- Memory 首次 baseline/import reminder 仍可由 monitor 报告，但不会伪装成没有可结算 item 的 Run batch。
- Packaged Forge Skill 改为循环消费 `run next`；不得自行扩大 Memory 批次，clipping 默认只查已有资产，close 后原样报告机器事实。

### Tests

- 覆盖稳定 reopen、Memory/剪藏批次上限、provider checkpoint、越界 sink、首次 baseline、重复 capture 抑制、三张候选预算及 close 最终事实。

## 0.11.1 (Source Signal completeness) — 2026-08-23

真实狗粮测试发现 `forge monitor` 可报告数百条 Memory 更新,但 `forge run open` 只扫描 `capture/`,因此能关闭空 Run 并误称“全部处理完成”。本版把来源发现和已捕获 evidence 接到同一份 Run 完整性账本。

### Added

- `Source Signal`:按 agent-memory、web-clipping、skill-projection、pending inbox/proposal、context/import/project/content 等类别聚合 monitor 发现,以 `source://<kind>` 进入 Run,不自动复制外部语料库。
- `run status` 新增 `source_attention` 与 `source_signal_counts`。
- Source Signal 专用 `defer --note <reason>`;下次 Run 重新出现。

### Changed

- `run close` 对未分流来源 fail closed;来源仍 actionable 时只能解决或明确 defer。存在 defer 的报告写“本轮未完成”。
- 真正干净的空 Run 不再生成审计文件或 Git commit。
- Memory state 未跟踪的文件统一称 `unseen`;其中 mtime 早于 provider baseline 的再单列 `historical backlog`,不再猜测它们是否最近新产出。

### Tests

- 新增 Source Signal CLI 端到端测试,并扩展 Memory baseline 与空 Run 回归测试。

## 0.11.0 (Evidence-to-Asset Promotion) — 2026-08-23

真实 Memory intake 证明“逐条蒸馏输入再批量 review”仍会把 owner 成本绑定到输入量。本版保留 capture、zone、compile gate、ledger、compiler、Portal provenance 和 eval 底座,把 Run 的选择单元改成跨独立事件聚合的主题。

### Added

- `system/observations/`:按 theme 聚合 evidence,记录 last-seen/expiry;到期自动关闭但不删除 raw capture。
- `system/candidates/`:带 `repeated|explicit|high-risk` 准入、scope、exclusions、准确 patch 和 verification 的 Candidate Asset。
- `forge observation record/list`、`forge candidate create/list/show/feedback`、`forge run disposition`。
- Candidate `approve|reject|observe` 生命周期;approve 复用 ledger 与 verified-snapshot gate。
- Run status 新增 Candidate/Observation 状态、接受率、平均审查时间、真实使用与 effective/revise/retire 分布。

### Changed

- `forge run ask` 默认最多三张 Candidate;conflict/unqualified-change 置顶;certification freshness 只作审计信号。
- `forge run close` 在任何新 input 尚无 disposition 时 fail closed,并报告输入去向与 Observation expiry。
- Portal 改为只读 Candidate card + Evidence-to-Asset 工作流;旧 proposal/workbench 进入 compatibility-only。

### Fixed

- Ledger 与 Run frontmatter parser 只识别独立分隔行;patch anchor 或字段值包含字面量 `---` 时不再截断账本。
- `forge run close` 不再吞掉 scoped commit 失败并假报“结算完毕”;失败时恢复为可继续的 open Run 并明确报错。

## Unreleased (compiled-output soft budget) — 2026-06-11

此前唯一的体积约束是 rule zone 的 `budget_lines` (默认 150 行, 只覆盖规则区 section 源文件); 编译产物 (`context build/runtime/claude-code/CLAUDE.md` 等) 没有任何 size guard——产物膨胀无人察觉。

### Added

- **编译产物 soft budget** (`forge/budget.py`): 可选的行数 / token 软预算。全局默认写在 `zones.yaml` 的 `output_budget: {lines, tokens}`; 每个产物可在 config frontmatter 用同名 `output_budget:` 按 key 覆盖 (`0` / `null` 显式关闭某一维度)。超预算时 `forge doctor` 和 `forge build` 输出 WARN——软预算, 永不 fail。未配置 = 不检查, 完全 opt-in。
- **token 估算 heuristic**: `estimate_tokens()` = CJK 字符 × 0.75 + 其他字符 × 0.25。是估计不是 tokenizer; 对一个 CJK-heavy 的真实 runtime 样本 (175 行 / ~17KB) 估出 4231 tokens, 与实际约 4.2K 吻合。
- **rule zone budget 提前预警**: 用量 ≥ 预算的 ~87% (`int(budget * 0.87)`, 默认 150 行时 130 行起) 即 WARN "nearly full", 在 cap 真正命中前给 owner 压缩压力; 超预算仍是原有 "exceeded" 警告, 两者不重复出现。

### Tests

- 新增 `tests/test_output_budget.py` (20 条): zones.yaml / config frontmatter 预算解析与非法值拒绝、token heuristic、doctor 对超行数 / 超 token 产物的 WARN (且 `report.ok` 保持 True)、config 覆盖全局、`0` 关闭继承维度、无 zones.yaml 时 config 预算独立生效、未 build 产物跳过、`forge build` CLI 打印 WARN、87% 阈值 (130/150) 与 nearly-full / exceeded 互斥。
- 当前验证: `605 passed, 3 skipped`。

## Unreleased (run-path target sync) — 2026-06-11

### Fixed

- **run 路径不再让外部 target binding 过期**: `forge target install` 的承诺是 runtime 重建后外部文件自动刷新, 但 target sync 此前只挂在 legacy `forge approve` 上。run-era 路径 (`forge run decide` 的 rule approve/reject、`forge run close`、ledger `apply_write` / `revert` / `reconcile`) 经 `gate.build` 重建 runtime 后, 绑定的 `~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md` 等保持 stale, 只能手动 `forge target install --force` 补救。现在 `gate.build` 重建后统一调用 `sync_targets`, 所有重建路径 (含 `forge build` / `forge migrate`) 都会刷新 manifest 里的 target bindings。

### Tests

- `tests/test_run_cycle.py` 新增两条回归: rule change 经 `forge run decide --approve` 后 bound external file 内容即时更新 (close 后仍一致); ledger `apply_write` 落账后同样刷新。
- 当前验证: `585 passed, 3 skipped`。

## Unreleased (context audit portal review lens) — 2026-06-09

Context Audit Portal 从静态 provenance 图推进到可审阅的 desktop review surface: 目标不是在 Portal 里编辑 truth,而是让 owner 能快速判断一段 context 从哪来、怎么进入 section、如何被编译进 runtime,以及本次 diff/PR 到底改了什么。

### Added

- **External Input lane**: audit graph 新增 `ExternalNode` 与 `external_to_source` 边,把 capture / memory source frontmatter 中的 `source:` / `origin:` / `imported_from:` 显式画成 upstream import 节点。Portal 现在能展示 `External Input → Capture → Section → Runtime` 四层链路。
- **Floating review drawer**: 节点 / 边点击后固定到右侧详情 drawer,支持拖拽宽度、最大化、关闭和 overview。长正文、长 diff、runtime hit 全量内容保留在 drawer 内滚动。
- **Hover review lens**: hover 不再打开完整 drawer,而是展示一屏预览。节点优先显示本次 change diff;边优先显示 `From / To` 双栏,直接对照"把什么拷贝 / 摘录 / 摘要成了什么",并标出 `method` / `status` / `confidence`。
- **Edge chips + direct edge inspector**: 图上的边有可点击 / hover 的 chip,不必猜曲线路径。`Source → Section`、`Section → Runtime`、`External Input → Capture` 三类边都有对应详情文案。
- **Keyboard navigation**: 方向键按 lane 导航;左右跨 provenance lane 并选择相近高度节点,上下只在当前 lane 内移动。`Enter` 固定当前节点到详情 drawer,`Esc` 关闭 hover / drawer。
- **Review mode filters**: diff mode 下支持只看改动,并在 overview 中集中列出 changed nodes 和 review gaps。

### Tests

- `tests/test_audit_portal.py` 覆盖 external input graph 节点、import edge inspector copy、hover card / keyboard contract、review lens HTML contract。
- 当前验证: `550 passed, 3 skipped`。

## 0.9.1 (remove _import_updates memory overlap) — 2026-05-10

修一个 v0.9.0 没顺手清理掉的设计 leftover: 老 v0.2 era `_import_updates` 路径仍然用 whole-corpus digest 跟踪 Claude auto-memory drift, 跟 v0.9.0 新的 per-file `.forge/agent_memory_state.json` baseline + diff 机制重叠, 同一源用两套机制以两种 scope (legacy: 跨 project 所有文件 concat; v0.9.0: 仅当前 workspace 对应 slug, per-file) 报, monitor 输出出现 duplicate signal: 用户看到 `import source updates: 1, Claude Code memory (changed, 23 files)` 同时 `agent-memory: initialized baseline (1 file tracked)`, 信号噪音高。

v0.9.1 把 `_import_updates` 里的 Claude memory 块删掉, agent-memory 监控权完整移交给 v0.9.0 watcher。`_import_updates` 仍然负责其它 import 候选(静态文件 CLAUDE.md / AGENTS.md / .cursorrules), 这部分行为不变。

### Fixed

- **`_import_updates` 不再追踪 Claude auto-memory**: cli.py 里的 memory whole-corpus digest 比较代码移除 (forge ingest --detect 和 forge capture --from-claude-memory 仍然使用 `_read_claude_memory`, 但这两个是 explicit user-triggered 流程, 不是 monitor 的自动报告路径, 不与 v0.9.0 冲突)。
- **monitor 输出去重**: 一个 workspace 当前 slug 下 memory 文件 drift 现在只走 v0.9.0 watcher 的 `agent-memory updates: N (new K, modified M)` 行, 不再叠加 legacy `import source updates: 1, Claude Code memory (changed, N files)`。

### Compatibility

- `forge ingest --detect` 行为不变。
- `forge capture --from-claude-memory` 行为不变。
- `_import_updates` 对静态文件 CLAUDE.md / AGENTS.md / .cursorrules / 其它 _FILE_CANDIDATES 的检测不变, 包括 v0.4.2 的 self-loop guard (target binding paths skip)。
- v0.9.0 引入的 `.forge/agent_memory_state.json` 不变; baseline-on-activation 行为不变。

### Skill / docs

- pyproject.toml / `forge/__init__.py` / SKILL.md frontmatter version `0.9.0` → `0.9.1`。

## 0.9.0 (agent-memory monitor) — 2026-05-09

修复一个**衰退**: v0.2 (commit 95d9240, 2026-04-26) 把 Claude Code auto-memory (`~/.claude/projects/<slug>/memory/*.md`) 加成一等 onboarding 源, SKILL.md Step 4 显式列为三大 source family 之一; v0.4.0+ monitor 抽象迭代时这条没被纳入新 pattern, 沦为 "ingest-only, 不被 daily monitor 监控", 实际等于从 daily 工作流里消失。

forge 的核心论点是 review-gated context compiler, 任何长期影响 agent 的源都要走 capture → inbox → PR → review。auto-memory 是这个论点上最直接的漏洞 —— Claude 自己写, 自己读, 完全 bypass governance —— 也是 forge 跟 Mem0/Letta 区分开的命脉。本版补回。

### Added

- **`forge/governance/claude_memory.py` 新模块**: 镜像 `web_clipping.py` / `workspace_project.py` 的 governance pattern。导出 `format_monitor_lines(workspace) -> (issues, actions)` 与 monitor 集成; 内部 `discover_memory_files(slug)` / `compute_diff(...)` / `mark_seen(...)` / `mark_path_seen(...)`; compat shims `scan_all_projects` / `read_all_projects` / `count_transcripts` 给 `forge ingest --detect` / `forge capture --from-claude-memory` 复用。
- **状态文件 `.forge/agent_memory_state.json`**: 跟 `manifest.json` 同位 (workspace-local, gitignored), schema_version 1, 记每个 memory 文件的 `{hash, size, seen_at}`。Side-channel 而非 in-source frontmatter, 因为 memory 文件被 Claude 自动 rewrite, 写 frontmatter 会被覆盖。
- **`forge monitor` 集成**: `cli.py` 加 `_agent_memory_updates(workspace)` thin wrapper (lazy-import 兜底, 跟其它 governance 模块同 pattern), slot 进 `cmd_monitor`。报 `agent-memory updates: N (new K, modified M)` + per-file `agent-memory NEW/MODIFIED: <slug>/<filename> · forge capture --from "<abs>"`, cap 5 per category。
- **baseline-on-activation**: 第一次跑 monitor (state file 不存在) 把当前所有 memory 文件 hash snapshot 进 state, 报 info 一行 `agent-memory: initialized baseline (N files tracked)`, **不入 inbox**。已有 memory 不追溯重审; 仅 baseline 后的新增/修改进 inbox。
- **capture-time mark-seen**: `forge capture --from <path>` 调用时, 若 `path` 在 `~/.claude/projects/*/memory/` 下, hook 自动更新 state file 的 hash。capture 即"我看见这个版本了, 不要再提"; 后续 inbox/PR 是下游决定。
- **`MEMORY.md` 索引文件排除**: well-known convention, monitor 永远 skip, baseline / diff / scan 也都 skip。否则每加/删一条 memory 都触发 MEMORY.md 变化, 噪音淹没真信号。
- **scope: 仅当前 workspace 对应的 Claude project slug**: `workspace_to_slug(workspace)` 反推 (绝对路径 `/` → `-`, e.g. `/Users/<user>/personalOS` → `-Users-<user>-personalOS`); 其它 Claude project slug 默认不监控。跨 slug 配置留给 v0.9.x。

### Refactor

- **`cli.py` 三个 helper 拆出**: `_scan_claude_memory` / `_read_claude_memory` / `_count_claude_transcripts` 改成 thin compat shims, 内部 delegate 到 `forge.governance.claude_memory`。`forge ingest --detect` / `forge capture --from-claude-memory` / `forge ingest --from-claude-memory` 三个入口语义不变, 唯一行为变化: 现在统一排除 `MEMORY.md` (与 monitor 一致, 之前 detect 会把索引算进文件数)。

### Tests

- 新增 `tests/test_v090_agent_memory_monitor.py` (23 cases): slug 反推、`MEMORY.md` 排除、baseline-on-first-activation、no Claude dir 静默、unchanged 静默、新文件触发 action、modified 触发 action、deleted 静默并清 state、`MEMORY.md` 变化永不报、`is_memory_file` / `slug_for_memory_path` / `mark_path_seen` 单元、`forge capture --from <memory>` e2e mark-seen、状态文件位置 + JSON schema、跨 slug 隔离 (其它 slug 新文件不触发本 workspace monitor)、`scan_all_projects` 排除 MEMORY.md、`forge monitor` CLI 集成 e2e。
- **总数 465 → 510 通过** (3 skipped 不变, 1 deselected — 见下)。

### Fixes

- **顺手修 v0.8.0 残留**: `forge/__init__.py` 之前还停在 `0.7.0` (v0.8.0 release 时 pyproject + SKILL.md 升了, `__init__.py` 漏了)。本版 bump 到 0.9.0 时一并修。`tests/test_v031_dogfood.py::test_skill_md_carries_current_version` 之前在 main HEAD 一直 fail, 现在过。

### Compatibility

- `forge ingest --detect` 的输出格式不变, 但 `MEMORY.md` 不再计入文件数 (历史显示 28 个的工作区现在显示 27 个之类)。
- `forge capture --from-claude-memory` 行为完全不变 (整批 concat); `forge capture --from <memory file>` 现在新增 mark-seen side-effect。
- 其它一切 v0.2 / v0.3 / v0.4 / v0.5 / v0.6 / v0.7 PR + governance 行为不受影响。
- 新增的 `.forge/agent_memory_state.json` 仅当 monitor 跑过且 workspace 有 Claude memory 才创建, 跟其它 `.forge/` 文件一样 gitignored。

### Skill / docs

- **pyproject.toml** version `0.8.0` → `0.9.0`; `forge/__init__.py` 同步; `forge/assets/skills/forge/SKILL.md` frontmatter version 同步。
- README governance pillar 段加 "agent-state" 子项 (Claude auto-memory; transcripts 留给 v0.4 distill 后续)。

## 0.8.0 (configurable classify + content scanner + PR archive) — 2026-05-08

(retrospective entry — v0.8.0 shipped via commits a709981 + 26b71c9 but没有 CHANGELOG entry, 且 `forge/__init__.py` 漏 bump 至 0.7.0 → v0.9.0 一并修。)

详见 git log: `a709981` feat(monitor) + `26b71c9` docs(README restructure)。核心: configurable classify config (`.forge/governance/classify.yaml`) + `forge/governance/content_scanner.py` 报内部内容变更 + PR 归档行为整理。

## 0.7.0 (propagation resolver) — 2026-05-07

修一个 v0.6 设计漏洞: PR proposal 的 propagation 树是 agent 手画的, 但传播规则其实是机制性的 (KB topic / asset → 反查 sections.upstream → section → runtime; sections 文件直接 → runtime; KB index/log/raw clipping → terminal)。手画浪费 + 易出错。v0.7 让 agent 只列 `modified_files`, forge resolver 根据 sections.upstream 反查自动推导 propagation。schema 兼容: 旧 PR 仍可手填 propagation, 不影响。

### Added

- **`forge.proposal.resolver` 新模块**: `load_workspace_index(workspace)` 读 `context build/sections/*.md` 的 `upstream:` 列表 + `context build/config/*.md` 的 `target` / `sections:` 列表,建反查索引;`classify_path(path, index, hint)` 判分类(`section_upstream` / `section` / `config` / `terminal` / `light`);`resolve_owner(item, index)` 把 `item.modified_files` 推导成 `item.propagation` 树;`resolve_proposal(proposal, index)` 走整个 PR(含 MIXED 的 sub_items),返回 `ResolveReport`。
- **schema 扩展(Item / SubItem)**: 新增三个 optional 字段 `modified_files: list[str]`、`modifications: dict[str, str]`(path → 改动摘要)、`propagation_hints: dict[str, str]`(path → `terminal` / `light` / `full`)。Round-trip preserve;`extra` 不变。
- **`forge proposal validate` 集成**: 默认在 reformat 之后、validate 之前跑 resolver——只对 "有 `modified_files` 但 propagation 空" 的 item 生效;有 `propagation` 的 item 跳过 + warn(用户手画优先);无 `modified_files` 的 item 与 v0.6 行为一致。新加 `--no-resolve` flag 强制跳过。
- **validate 接受 `modified_files` 替代品**: APPLY item 不必再要求 propagation, 只要 `modified_files` 非空即合法(库层兼容: 库调用方先 validate 后 resolve 也能工作)。

### Resolver 算法

1. 加载 sections frontmatter(`name` / `upstream`),configs frontmatter(`target` / `sections`)。
2. 对每个 `modified_file` path: 检查 `propagation_hints` → `terminal` 单节点终止 / `light` 终止 + label `light update`。
3. 默认: 反查 sections.upstream 命中(目录 prefix 或精确匹配)→ asset → section → runtime per matching config;不命中 → terminal + warn `not in any section.upstream`。
4. 文件本身在 sections_dir → 直接 section → runtime(无 asset 父节点);在 configs_dir → config terminal。
5. **Grouping**: 多个 modified file 同 section → 一个容器 branch(label `N assets → <section>`),每文件一个子 asset 分支,共享一个 section / runtime 子树(deduped)。多个 file 不同 section → 独立 branches。
6. 自动给 section / runtime 内部节点填合成 modification 文本(`auto-recompiled (section.upstream changed)` / `auto-recompiled by \`forge build\` (target: ...)`)以满足 `_validate_node` 的 "non-terminal APPLY 必须有 modification" 约束。

### Tests

- 新增 `tests/test_v070_propagation_resolver.py`(20 cases): KB topic 单文件、asset → preference、多文件 grouping、KB index/log 默认 + 显式 hint、raw clipping、`hint=terminal` / `hint=light`、sections 文件直 → runtime、不命中 → terminal + warn、空 modified_files → fallback v0.6、已有 propagation → resolver skip、TSMC e2e(5 文件,3 KB topic + 2 index/log)、不同 section 独立 branches、config 文件分类、modifications 传到 leaf、schema round-trip 保留 v0.7 字段、`resolve_proposal` 走 sub_items、validate 接受 `modified_files` 替代品、CLI `forge proposal validate` 写回 propagation。
- **总数 445 → 465 通过**(3 skipped 不变)。

### Compatibility

- v0.2 / v0.3 / v0.4 / v0.5 / v0.6 PR(手填 propagation)不受影响。
- 新 PR 可用 `modified_files` 风格,也可仍用手填 propagation。
- v0.6 / v0.5 / v0.4 已 ship 的 PR propagation tree 不重写。

### Skill / docs

- **pyproject.toml** version `0.6.0` → `0.7.0`(minor bump,新功能 + schema 扩展);`forge/__init__.py` 同步。

## 0.6.0 (web-clipping synthesize) — 2026-05-07

补齐原 dxyOS 设计但实现没做的能力:`capture/web clipping/` 下的 raw evidence 不再静默 sit 着——agent 可以把 clipping synthesize 进 KB topic 页, user review **KB topic 怎么变**(不审 clipping 原文),走标准 inbox → PR → review → approve 流程,approve 后 clipping frontmatter 加 `synthesized_at` + `synthesized_into` 标记完成。生命周期 `captured → indexed → cited/synthesized → archived/expired` 的中段补齐;clipping 文件本身永不被删除。

### Added

- **`forge synthesize-clipping <path>` 命令**: 读 `capture/web clipping/<file>.md`,生成 capture 落到 `capture/import/<batch>/synthesize-clipping-<slug>.md` + 创 inbox item `type: web-clipping-synthesize`。capture 内含: clipping 元数据(title / source / captured_at)、候选 KB topic 列表(扫 `public knowledge base/topic/**/*.md`)、clipping body 头 80 行、agent 填 schema 指引。Inbox frontmatter 含 `web_clipping: <path>` 让后续 approve 找回 clipping。支持 absolute / workspace-relative / 裸文件名(`alpha.md` 自动到 `capture/web clipping/`)。
- **`forge monitor` 扫 web clipping**: 新增"未 synthesize clipping"扫描——读每个 `capture/web clipping/*.md` 的 frontmatter,无 `synthesized_at` 即报 `web-clipping pending synthesize: N` + per-clipping `next: forge synthesize-clipping "<path>"` 行(路径自动加引号,因为 `web clipping/` 含空格)。无 frontmatter 的文件静默忽略(out of scope)。
- **`forge pr done` 写回 clipping frontmatter**: 当 PR `type: web-clipping-synthesize` 且非 `--reject`,扫 `inbox_sources[]` 找 `web_clipping:` 字段,从 proposal `items[].propagation` 树(含 sub_items)收集所有 `public knowledge base/topic/...md` 路径,把它们 union 到 clipping frontmatter 的 `synthesized_into[]`,同时写入 `synthesized_at` ISO 时间戳。Reject 不写。Print: `synthesized: <clip> -> <topic1>, <topic2>`。
- **`forge.governance.web_clipping` 新模块**: `WebClipping` dataclass、`load_clipping` / `discover_clippings` / `pending_clippings`、`discover_kb_topic_files`(排除 `topic/` 顶层 `index.md` / `log.md`)、`build_synthesize_capture_markdown`、`mark_synthesized`(union 已有 entries 不重复)、`kb_topic_paths_from_propagation`(BFS 走 propagation 树)、`format_monitor_lines`。

### Design

- **forge 不替 agent 判断 clipping 该进哪个 topic**——只列候选 + 创 stub 走 PR 流程,agent 在填 schema 时决定,user review **KB topic 改动**(不审 clipping)。无 LLM API 调用,无外部依赖。
- **synthesized 标记跟 source 走**: 选 (a) clipping frontmatter 加字段,而非 (b) `.forge/manifest.json` 维护 list。Rationale: clipping 自身是 source,marker 跟着 source,文件移动不丢追踪,无并行 manifest 同步成本。
- **生命周期最后是 archive,不 delete**: 永不删 clipping 原文,即使已 synthesized;archive/expire 是 user 手工决策,forge 不介入。
- **Clipping 可一直 sit**: monitor 报但不 fail(`status: attention` 仅提示,exit 0);不强制 synthesize。

### Tests

- 新增 `tests/test_v060_clipping_synthesize.py`(25 cases),覆盖 WebClipping schema parsing、KB topic discovery、monitor 集成、`forge synthesize-clipping` CLI、capture builder、`mark_synthesized` 写回 + union、propagation 树解析、`forge pr done` approve 写回 + reject 不写、headline e2e fixture(clip → monitor → synthesize → 手填 proposal → approve → frontmatter stamped + 文件不删 + 后续 monitor silent)。
- **总数 420 → 445 通过**(3 skipped 不变)。

### Skill / docs

- **SKILL.md** version `0.5.1` → `0.6.0`。
- **pyproject.toml** version `0.5.1` → `0.6.0`(minor bump,新功能);`forge/__init__.py` 同步。

## 0.5.1 (legacy onepage schema auto-migrate) — 2026-05-07

修一个 v0.5.0 设计漏洞: legacy onepage(v0.4.x 时代写的 `last_synced` 缺 `dirty_hash` / `dirty_count` 字段)要让 forge 写回新字段,只能走完整 PR review 流程(capture → inbox → proposal → review → approve → pr done)——但这个流程没任何 design 决策需要 user 判断,纯粹是 forge 机械填充 sha256(porcelain)。让 user review 是 over-engineering,违反 forge "review-gated 仅用于有 design 决策的内容" 主线。

### Added

- **`forge migrate-onepage` 命令**: 扫 `workspace/project/*/onepage.md`,对每个"有 `last_synced.commit` 但缺 `dirty_hash` 字段"的 legacy onepage,在 `upstream.local_dir` 跑 `git status --porcelain -uall`,算 sha256 + 计数,inline patch onepage frontmatter 加 `dirty_hash` + `dirty_count` 并把 `at` 更新到当前 UTC。**不走 PR review**(没 design 决策)。`--dry-run` 预览,`--verbose` / `-v` 每个 onepage 一行。分类:`upgraded` / `current`(已 v0.5)/ `no-baseline`(从未同步,等 capture)/ `warn`(`local_dir` 不存在或不是 git repo)。
- **`forge monitor` 末尾 legacy 提示**: 若检测到 N 个 legacy onepage,在 `status: clean` / `status: attention` 输出末尾追加 `note: N project onepage(s) on legacy schema (no dirty_hash). run \`forge migrate-onepage\` to auto-fill.`。不强制 auto-run, user invoked。
- **`forge.governance.workspace_project` 新增模块层 API**: `migrate_legacy_onepage_schema(workspace, *, dry_run, now_iso)`、`count_legacy_onepages(workspace)`、`MigrateOnepageReport` / `MigrateOnepageOutcome` dataclass,供其它流程(skill / 测试)直接调用。

### Tests

- 新增 `tests/test_v051_migrate.py`(10 cases):
  - **legacy onepage → upgraded inline**: 写 dirty_hash + dirty_count, 不创建 PR / inbox。
  - **already v0.5 → current skip**: 文件 byte-for-byte 不变。
  - **multiple onepages mixed**: legacy + v0.5 + never-synced 三类各自分类,互不干扰。
  - **`--dry-run` writes nothing**: 文件 byte-for-byte 不变,但 report 仍正确分类。
  - **never-synced → no-baseline**(不算 legacy): 等 capture 建立 v0.5 baseline,`count_legacy_onepages` 也不计。
  - **monitor 末尾提示 legacy 计数 + 命令名**(`status: clean` 路径)。
  - **monitor 不提示当无 legacy**(belt-and-suspenders)。
  - **CLI `--dry-run` summary 含 `[dry-run]` / `would be:` / `upgraded=N` / re-run 提示**。
  - **CLI `--verbose`** 每类各打一行。
  - **e2e fixture**: legacy onepage + 外部 dirty repo → migrate → 文件 inline 写入 + `probe_project` clean + 无 PR / inbox 残留 + monitor 后续不再提示。
- **总数 410 → 420 通过**(3 skipped 不变)。

### Skill / docs

- **SKILL.md**(`forge/assets/skills/forge/SKILL.md`)version `0.5.0` → `0.5.1`,monitor 流程加一条 bullet:若 monitor 末尾出现 `note: ... legacy schema`,跑 `forge migrate-onepage` 即可,无需 review。
- **pyproject.toml** version `0.5.0` → `0.5.1`,`forge/__init__.py` 同步。

## 0.4.2 (monitor self-loop + README sync) — 2026-05-07

修一个跟 v0.4.1 target install 落地后立刻冒出来的 dogfood bug:`forge monitor --root ~/personalOS` 把本工作区自己绑定的外部 target(`~/.claude/CLAUDE.md` / `~/.codex/AGENTS.md`)报成 "import source updates"——因为 copy-mode `forge approve` 每跑一次就 mtime+contents 双变化, symlink-mode 则 resolve 到我们自己的 runtime artifact, monitor 的 `_import_updates` 不知道这是自己的 output, 当成外部源把它捞回来, 一个 review cycle 就空转一次。同时 README/README.en 顶部的"现状"段还在 v0.1.0 alpha 描述, 跟 v0.2.3-v0.4.1 的 8 个 rc tag、§0.5 schema-aware proposal 渲染、workspace-project sync、target install layout-aware 等新能力对不上。本版一起修。

### Fixed

- **`forge.cli._import_updates` self-loop guard**: 新增 `_target_binding_paths(workspace)` helper, 读 `.forge/manifest.json::targets[]`,把每个 binding 的 `path` 字段(literal + `Path.resolve(strict=False)` 后的 real path)汇成 set。`_import_updates` 遍历 `_FILE_CANDIDATES` 时若 `str(p)` 或 `str(real)` 命中此 set, 直接 `continue`, 不进 capture record digest 比对、不进 updates 列表。symlink-mode 和 copy-mode 两种 binding 都被 cover, 因为我们同时记 literal 和 resolved 形态。
- **legacy/无 manifest 行为不变**: `.forge/manifest.json` 不存在 / `targets` 为空 / JSON broken 三种情况下 `_target_binding_paths` 返回空 set,沿用历史的"全报"逻辑。Legacy SP layout 工作区 + 还没跑过 `forge target install` 的工作区都不受影响。

### Docs

- **README.md 顶部状态段落 surgical update**: 把"当前: v0.1.0 alpha"段改写为 v0.4.2-rc1 现状,带 8 rc tag 列表 + §0.5 / workspace-project / target install / self-loop detection 新功能 bullet。不动核心叙事 / 30 秒 demo / "5 pillars" architecture / Roadmap 表格——这些 v0.1.0 写就的内容仍然准确。硬核验证表 "单元测试" 行 `106 / 106` → `390 / 390`,带括注"v0.1.0 时 106 / 106"保留历史锚点。
- **README.en.md 同步**: line 33 的 "Status: v0.1.0 alpha" 段同样 surgical update,内容口径与中文 README 一致。
- **CHANGELOG.md** 加 v0.4.2 entry(本段)。

### Tests

- 新增 `tests/test_v042_monitor_self_loop.py`(9 cases):
  - **`_target_binding_paths` helper**(3): 无 manifest / 有 manifest 无 `targets` 键 / 有 binding 时同时收 literal + resolved。
  - **必修的 4 cases**: case 1 manifest 含 `~/.claude/CLAUDE.md` binding → monitor 不报; case 2 无 manifest → monitor 沿用旧行为, 报 import update; case 3 binding 在但目标 mtime / 内容刚被 `forge approve` 改过 → 仍不报 (这是 self-loop, 不是 external drift); case 4 一个 bound target + 一个 un-bound external source 共存 → 前者被压住, 后者仍正常报。
  - **symlink-mode 覆盖**(1): symlink → runtime artifact 形态的 binding 同样被 self-loop guard 命中。
  - **malformed manifest 容错**(1): broken JSON 时 monitor 不 crash, 降级到 legacy 行为。
- **总数 381 → 390 通过**(3 skipped 不变)。

### Skill / install

- `forge self-install` 同步 v0.4.2(`forge/assets/skills/forge/SKILL.md` `version: 0.4.2`)。
- 不动 v0.4.0 workspace-project sync 链路、不动 v0.4.1 target install 解析、不动 schema、不引入 dep。
- e2e fixture(non-personalOS,tmp_path)验证: 假 manifest binding + 假 fake_home 下 `_import_updates` 不报 bound target、仍报 un-bound external source。主 agent ~/personalOS 不动(避免与 dogfood race)。

## 0.4.1 (target install on personalOS layout) — 2026-05-07

修一个跟 v0.2.3 的 ingest legacy-path bug 同性质的 v0.4.0 遗留:`forge target install <adapter> --to <path>` 在 personalOS / v0428 layout(`context build/config/*.md` + `context build/runtime/<adapter>/<filename>`)下报"no compiled output for adapter ..."(部分老 install 报"no config in sp/config/ has `target: <adapter>`"),原因是 `forge.gate.sync._output_path_for_adapter` 把 runtime artifact 解析成 `state.output_dir / <filename>`(legacy SP 的 flat 形态),没有像 `gate.actions._rebuild_outputs` 那样按 `layout.runtime_nested_by_target` 走 `state.output_dir / <adapter-name> / <filename>` 的嵌套路径。

### Fixed

- **`forge.gate.sync._output_path_for_adapter` layout-aware 解析**: 读 `state.layout` 后,若 `runtime_nested_by_target=True`(v0428 / personalOS layout)走嵌套形态 `state.output_dir / adapter.name / filename`;否则(legacy SP layout)沿用 `state.output_dir / filename`。逻辑跟 `gate.actions._rebuild_outputs` 写出端严格对称,`forge target install / list / remove`、`forge approve` 自动 sync 在两种 layout 下都拿到同一 path。
- **找不到匹配 config 时的错误信息使用当前 layout 的 source label**: 之前固定 hard-code `sp/config/`,在 v0428 layout 下误导用户去找一个不存在的目录。改为读 `state.layout.source_label`,personalOS 下出 `no config in context build/config/ has target: <adapter>`。

### Tests

- 新增 `tests/test_v041_target_install_personal_os.py`(8 cases):
  - **install resolves nested runtime**:claude-code / agents-md 在 v0428 layout 下都能定位到 `context build/runtime/<adapter>/<filename>`,symlink / copy 模式都验。
  - **post-install auto-refresh**:section 改完跑 `forge approve`,symlink target / copy file 都拿到新 render。
  - **target list**:两个 binding 都正确返回外部路径。
  - **legacy SP 回归保护**:legacy `forge new` workspace 下 install 仍走 `output/<filename>` flat 路径。
  - **error message uses layout label**:v0428 下未知 adapter 的报错文本含 `context build/config/`,不含 `sp/config/`。
- 调整 `tests/test_target_sync.py::test_install_target_unknown_adapter`:正则从字面 `no config in sp/config/` 放宽到 `no config in .*config/`,兼容两种 layout(legacy 仍命中 `sp/`,新 layout 命中 `context build/`)。
- **总数 373 → 381 通过**(3 skipped 不变)。

### Skill / install

- `forge self-install` 同步 v0.4.1(`forge/assets/skills/forge/SKILL.md` `version: 0.4.1`)。
- 不动 v0.4.0 workspace-project sync 链路、不动 schema、不引入 dep。
- e2e fixture(non-personalOS,tmp_path)验证:`install_target` → 创真 symlink → 改 section → `gate.approve` → 外部 symlink 内容更新;主 agent ~/personalOS 不动(避免与 dogfood race)。

## 0.4.0 (workspace-project sync) — 2026-05-07

新增 `kind: project` onepage 上游同步链路:用户在 `workspace/project/<name>/onepage.md` 声明外部工作目录(`upstream.local_dir` + 可选 `git_remote` / `status_sources`)后,forge 即可在本地 git HEAD 与 `last_synced.commit` 不一致时报变化、把 `git log/diff/status` + status_sources head 抓为 capture inbox 项,并在 PR approve 时把当前 HEAD 写回 `last_synced`。本版只做"觉察 + 抓状态 + 写回",不自动总结、不远端 fetch、不复杂 diff。

### Added

- **schema 识别**: `forge/governance/workspace_project.py` 新增 `ProjectOnepage` / `load_project_onepage` / `discover_project_onepages`,用 PyYAML 解析嵌套 frontmatter(`upstream:` / `last_synced:`),tilde / env 展开,YAML auto-parse 的 datetime 标准化为 ISO 字串。`kind: project` 之外的 onepage 仍按旧路径处理(向后兼容)。
- **doctor INFO lint**: `forge/gate/doctor.py` 新增 `_project_onepage_lines`,扫到 `kind: project` 但缺 `upstream.local_dir` 时输出 INFO(不是 WARN / ERROR)——onepage 仍是合法 onepage,只是 sync 链路未启用。无 project onepage 时此段不出现。
- **forge monitor 扩展**: `forge/cli.py::monitor` 新增 `_workspace_project_updates`,对每个有 upstream 的 project 跑 `probe_project`(本地 `git rev-parse HEAD` vs `last_synced.commit`、`status_sources` mtime vs `last_synced.at`)。drift 进 attention `next:` 列表为 `workspace-project changed: <name> · ...` 行;`local_dir` 缺失 / 非 git 仅输出 `warn:`,不把 status 抬到 attention。
- **forge capture --workspace-project `<name>`**: capture 路径新增第 4 个互斥 input mode。命中时合成 capture markdown(`# Summary` + `## Commits since last_synced`(git log oneline)+ `## Diff stat since last_synced`(git diff --stat)+ `## Working tree status`(git status --short)+ `## Status sources`(每文件 head 50 行 + mtime)),写入 `capture/import/<ts>/workspace-project-<name>.md` + `system/inbox/<ts>-workspace-project-<name>.md`(`type: workspace-project-update`)。从未 sync(`last_synced.commit` 空)走"showing last 20 commits" fallback,不报错。
- **forge pr done atomic last_synced 写回**: approve(非 `--reject`)时,`_sync_last_synced_for_modified_onepages` 扫工作树中已修改的 project onepage,从 `upstream.local_dir` 读当前 HEAD,把 `{commit, at}` 注入 onepage frontmatter。用户下一次 git commit 把 last_synced 跟 onepage body 改动绑成一笔——审核+写回原子化。`--reject` 不动 onepage(PR 不代表真实 sync)。
- **SKILL.md `Workspace-Project Sync` 章节**: `forge/assets/skills/forge/SKILL.md` 加一节解释 schema、`forge capture --workspace-project` 触发、PR 审核回写 last_synced 流程。`forge monitor` 触发清单加 `workspace-project changed: <name>` 一行。
- **subprocess only**: 不引入 GitPython 等外部 dep,所有 git 调用走 `subprocess.run`,从不 `git fetch`(纯本地 state 信号)。

### Tests

- 新增 `tests/test_v040_workspace_project_sync.py`(29 cases),分 5 组:
  - **schema 解析**(6):`load_project_onepage` 全字段、跳过非 `kind: project`、空 `upstream` 容忍、`~` 展开、`discover_project_onepages` 排序与过滤、`split_frontmatter` 处理 YAML 嵌套。
  - **doctor INFO lint**(2):missing `upstream.local_dir` 进 INFO 而非 WARN/ERROR;无 project onepage 时不输出此段。
  - **monitor probe + CLI**(7):commit drift / never-synced / status_source mtime drift / `local_dir` 不存在 / 非 git;CLI `monitor` 检到 drift 报 `workspace-project changed`、无 drift 报 `status: clean`、`local_dir` 缺失仅 `warn:` 不抬 attention。
  - **capture CLI**(5):正常路径写 capture + inbox、未知 name 报错、缺 `upstream.local_dir` 报错、与其他 input mode 互斥、never-synced 走 last-20 fallback。
  - **last_synced 写回**(7):`update_last_synced` 注入 / 跳过非 project / 覆盖旧值;`find_modified_project_onepages` 检 modified + untracked;`pr done` approve 路径写回、`--reject` 路径不写回。
  - **e2e**(1):真上游 git repo + 真 personalOS root + monitor → capture → 改 onepage → 创 fake PR → `pr done` 全链路,assert `last_synced.commit` 等于新上游 HEAD。
- **总数 344 → 373 通过**(3 skipped 不变)。

### Skill / install

- `forge self-install` 同步 v0.4.0 (`forge/assets/skills/forge/SKILL.md` `version: 0.4.0`)。
- onepage 老版本(`kind` 非 `project` 或 无 `upstream:`)无任何变化:不进 monitor / doctor / capture 新逻辑。

## 0.3.4 (wrap corners) — 2026-05-06

主 agent 在 ~/personalOS dogfood v0.3.3 渲染 `system/pr/20260505-211750-context-import/proposal.md` 时,发现 wrap 算法三个 corner-case bug:**(A)** 文件名 `CLAUDE.md` 被在 `.` 处错切成 `CLAUDE.\n│ md`(类似还会影响 `forge.md`、`192.168.1.1`、`example.com`、`v0.3.3` 等);**(B)** `└─ X` 末节段落 wrap 续行 prefix 是 14 空格,跟前 3 cols 段首 `└─ ` 视觉错位;**(C)** `├─ X` 段落 wrap 续行 prefix 是 `│ `(2 cols)而段首 `├─ ` 是 3 cols,差 1 列。本版统一修。

### Fixed

- **Bug A · ASCII `,;.!?)` 跟随 space 才作 break candidate**: `forge.proposal.renderer._find_break` 之前把 ASCII 句号 `.`、逗号 `,`、分号 `;`、感叹号 `!`、问号 `?`、右括号 `)` 一律当 break point,导致文件扩展名(`CLAUDE.md` → `CLAUDE.` + `md`)、IP(`192.168.1.1`)、域名(`example.com`)、版本号(`v0.3.3`)等"标点夹在 token 内部"的形态被切断。v0.3.4 把 break-after 集合拆成两类:`_CJK_BREAK_AFTER`(fullwidth `，。；：、！？）】」』` + `→`,break 立即生效)和 `_ASCII_BREAK_AFTER`(`,;.!?)`,**仅当下一字符是 space 或 EOS 才作 break candidate**)。`forge.proposal.reformat._find_punct_break` 同步,frontmatter break-long-lines 也遵循相同规则。
- **Bug B · `└─ X` 段落 wrap 续行用 `   `(3 cols)对齐**: `_field_block(tree=True)` 的最后一个 paragraph(连接器 `└─`)wrap 续行 prefix 之前是 12 空格 + `  `(2 空格)= 14 空格,但段首是 12 空格 + `└─` + 1 空格 = 15 cols,内容起点错位 1 列。改为 12 空格 + `   `(3 空格)= 15 cols,跟段首内容严格同列,且**没有 `│`**(末节子树终止)。
- **Bug C · `├─ X` 段落 wrap 续行用 `│  `(3 cols)对齐**: 同上,`├─` 连接器 wrap 续行之前是 12 空格 + `│ `(│ + 1 空格)= 14 cols,跟段首 `├─` + 1 空格 = 15 cols 错位。改为 12 空格 + `│  `(│ + 2 空格)= 15 cols,续行内容跟段首内容(`Why:` 等)严格同列对齐。

### Tests

- 新增 `tests/test_v034_wrap_corners.py`(14 cases):
  - **Bug A**:`CLAUDE.md` / IP `192.168.1.1` / 域名 `example.com` / 版本号 `v0.3.3` 不被切;ASCII `. ` / `, ` 后跟空格仍是 break;CJK fullwidth `，。` 仍立即 break;`_find_break` 在 `CLAUDE.md` 内部不返回 dot-break;`_find_break` 在 `First. Second.` 处正确返回 dot-break。
  - **Bug B**:`render` 后 `└─` 段落续行严格 `<12sp>   `(3 cols, 无 `│`),内容起点对齐到段首内容列。
  - **Bug C**:`render` 后 `├─` 段落续行严格 `<12sp>│  `(3 cols),内容起点对齐到段首内容列。
  - **回归**:CJK fullwidth `，` 单独的多行 extracted 仍正常 wrap 到 78 cols;`_CJK_BREAK_AFTER` / `_ASCII_BREAK_AFTER` 两集合不互相泄露 ASCII / non-ASCII 字符。
- 更新 `tests/test_v033_render_width.py`:`test_wrap_long_chinese_breaks_at_punct`、`test_break_long_string_breaks_at_cjk_punct`、`test_break_long_string_arrow_is_break_point`、4 处 `test_reformat_*`、`test_needs_reformat_*`、`test_cli_proposal_reformat_default_breaks_lines` 共 7 处 fixture 中的 ASCII `,`(夹在 CJK 字符之间)改为 fullwidth `，`,匹配 v0.3.4 新约定:**ASCII `,` 在 CJK 字符之间不再作 break candidate,中文断句请用 fullwidth `，`**。新增 `test_wrap_long_chinese_breaks_at_cjk_fullwidth_punct` 单独 pin fullwidth `，` 的 break-after 行为。**总数 329 → 344 通过**(3 skipped 不变)。

### E2E (~/personalOS dogfood)

在 `~/personalOS/system/pr/20260505-211750-context-import/proposal.md` 上重 render(`forge pr render --stdout`):

- sub 3.13 `提取信息` 段:`├─ 原文承认: "该偏好已经在 CLAUDE.md About user 段写明 ...` 全行可读,**`CLAUDE.md` 不再被 dot-split**(v0.3.3 → v0.3.4 diff:`CLAUDE.\n│ md` 消失,改为 `CLAUDE.md ` 整词不切)。
- sub 3.13 `├─ Why:` 段:续行 prefix 从 `│ 默认还是说中文` 变 `│  triage 中纠正)`(2 cols → 3 cols),`triage` / `Why:` 起点同列。
- sub 3.13 `└─ shell 命令` 段:续行 prefix 从 `              user 明确说英文时切换。`(14 空格)变 `   user 明确说英文时切换。`(3 空格,无 `│`),`user` / `shell` 起点同列。
- 全文 `grep "CLAUDE\.$"` body 区(line 645+)= **0 matches**(v0.3.3 时该段渲染含 `CLAUDE.\n` 行,v0.3.4 已修)。

### Skill

- `forge` skill doc(`forge/assets/skills/forge/SKILL.md`):无需新增章节(wrap 行为是 render layer 内部事,用户面 API 不变)。`forge self-install` 同步把版本号 reference 从 v0.3.3 → v0.3.4(如有)。

## 0.3.3 (render width + wrap) — 2026-05-06

主 agent 在 ~/personalOS dogfood v0.3.2 时反馈 proposal.md body §0.5 渲染输出"换行奇怪":default render width 73 cols,但文本行(`提取信息`、`理由`、`修改:` 等)长达 100+ chars 没自动 wrap,Obsidian / 终端按 viewport 折回时折叠点不规则。frontmatter 区也有若干 130-176 byte 的长 plain scalar 单行(无内嵌 `\n`),YAML dumper 未做软换行,看着挤。本版统一处理:render 默认 wrap 到 78 cols(display width,CJK = 2 cols),frontmatter dumper 默认在中文/ASCII 标点处 break long plain scalar。

### Added

- **`render(..., width=78, wrap=True)` 默认 wrap**: `forge.proposal.renderer.render` 默认参数从 `width=73` → `width=78`,新增 `wrap: bool = True` 控制内容软换行。常量 `WRAP_WIDTH = 78` 暴露在模块 top-level,所有内部 helper 使用同一默认。
- **content soft-wrap helper `_wrap_line`**: 通用软换行函数,优先在 CJK / ASCII 标点(`，。、；：！？,;.!?）)】」』→`)处断开,其次 ASCII 空格;超长无断点的字符串走 hard-cut(display-width-aware)。每个调用点提供 `first_prefix` / `cont_prefix` 决定行首和续行前缀,所以 wrap 不破坏 tree 形状或字段对齐。
- **`提取信息` 多行 + tree-prefix wrap**: `_field_block(tree=True)` 处理 `extracted` 的多行值时,每段(用户原 `\n` 切)单独 wrap;段首 `├─` / `└─`,wrap 续行 `│ ` / `  ` (跟段首对齐),保持 tree 整体性。
- **`修改:` 行 wrap 用 `│        ` 续行 prefix**: `_render_branch` / `_render_merged_propagation` 的 modification 渲染:**第一行** `├─ 修改: ...`,后续(用户 `\n` 或 wrap 自动)统一 `│        ` (8-space pad),visually 对齐到 `修改:` 后的内容列。这恢复了 v0.3.2 的 `│        ` continuation,同时支持 wrap-induced sub-lines。
- **box 边框 / sub-item 标题 display-width 对齐**: `══ ITEM N ═══...═` 起始行、`═══...═` 闭合行、`── ITEM N / sub N.M · ICON ──...──` 子项标题条全部按 display width(CJK = 2 cols)pad,起止两行严格等宽。
- **COVERED 压缩列表 row-wrap**: `_render_covered_table` 在 label 或 covered_by 让单行 row 超过 `width` cols 时,fallback 到双行 stacked form: `<id>  <label-wrap>` / `         → <covered_by-wrap>`。labels / paths 自身也走 `_wrap_line` 防爆破。
- **`forge pr render --width N` flag**: CLI 默认值从 73 改为 78,显式 `--width N` 让用户调整。
- **`forge pr render --no-wrap` flag**: 关掉 content soft-wrap(legacy v0.3.2-and-earlier 行为),box rules 仍按 `--width` 渲染,兼容老期望。
- **`reformat_text(..., break_long_lines=True)` 默认开**: 在 `forge.proposal.reformat` 加 `_walk_break_long`:递归走 frontmatter dict,对长 string 标量(display width > 90 cols),在 CJK / ASCII 标点(`，。；：、！？)）】」』,;.!?→`)处插入 `\n`,然后 `_ForgeDumper` 自动用 block scalar (`|`) 输出。无标点可断的句子保持单行(保守不硬切)。仅 plain-scalar 单行才触发,已有 `\n` 的 multi-line 字段不动。
- **`forge proposal reformat --no-break-lines` flag**: 关掉 break-long-lines 的内容 mutation,只做 v0.3.2 的 YAML 风格归一化。
- **`needs_reformat(text, break_long_lines=True)` 默认开**: 与 `reformat_text` 同步,doctor / dogfood 检测时把"需要 break long lines"也算作需要 reformat。

### Fixed

- **`_render_item` / `_render_sub_item` 等所有标题条 pad 方法从 `len()` 改为 `_display_width()`**: v0.3.2 用 Python `len()`(char count)算 fill 长度,在含 CJK / emoji 的标题(如 `── ITEM 3 / sub 3.13 · ✅ APPLY ──`)上结果偏短,起止边框宽度不一致。改用 display-width 后边框严格等宽。

### Tests

- 新增 `tests/test_v033_render_width.py`(29 cases):`_wrap_line` 单元(默认宽度、短行、CJK 标点 break、ASCII 空格 break、续行 prefix、无断点 fallback);`render` 集成(default width 78、显式 `--width 60`、`--no-wrap`、box 起止等宽、sub-item 标题 pad、modification wrap 用 `│ ` 续行、modification multi-line 不变成多个 `├─ 修改:` 头部、`提取信息` tree wrap 用 `│ ` 续行、v0.3.1 P10 回归);frontmatter dumper(`_break_long_string` CJK 标点 break、`→` 作为 break point、ASCII 无 punct 不切、`reformat_text` 默认 break、`--no-break-lines` opt-out、idempotent、preserves semantics、`needs_reformat` detect)。CLI 端到端(`forge pr render` default width 78、`--width 60`、`--no-wrap`、`forge proposal reformat` default break、`--no-break-lines`)。**总数 300 → 329 通过**(3 skipped 不变)。

### E2E (~/personalOS dogfood)

在 `~/personalOS/system/pr/20260505-211750-context-import/proposal.md` 上跑 `forge proposal reformat` + `forge pr render` 后:

- frontmatter 区(line 1-639): display-width > 95 cols 单行 = **2 行**(下降 from 大量 130-176 byte 长行;两行均为无内部 break 标点的单句)
- body 区 BEGIN..END(line 645-1245): display-width > 90 cols 单行 = **0 行**(原 13 行长 row 全部 wrap;COVERED 压缩列表也修正)
- box rule 起止等宽: 全部 78 cols(`══ ITEM N ═══...═` ↔ `═══...═` 对齐)

### Skill

- `forge` skill doc(`forge/assets/skills/forge/SKILL.md`)v0.3.2 → v0.3.3:"Process Inbox To Proposal" §3 加一段说明 v0.3.3 起 render / reformat 默认 wrap / break-long-lines 到 78 / 90 cols,以及 `--width N` / `--no-wrap` / `--no-break-lines` opt-out。`forge self-install` 同步到 `~/.claude/skills/forge/SKILL.md`。

## 0.3.2 (yaml block-scalar) — 2026-05-06

主 agent 在 ~/personalOS 跑 v0.3.1 的 `forge proposal new`,proposal.md frontmatter 里多行字符串字段(`extracted` / `rationale` / `covered_by`)被 PyYAML 默认 dump 成两种丑陋形态:**(A)** double-quoted flow scalar(单行 632–746 字符塞 `\n` escape),**(B)** single-quoted folded scalar(段落间双 newline + 6-space 缩进 + `''` 转义)。Obsidian 里读着累、diff 难看、ergonomics 拉。本版统一用 YAML literal block scalar (`|`)。

### Fixed

- **多行字符串 dump 用 block scalar**: 新增 `forge.proposal.schema._ForgeDumper`(yaml.SafeDumper subclass)+ custom str representer:任何含 `\n` 的字符串自动用 `style='|'`,行尾 trailing whitespace 清理(否则 PyYAML 会 fallback 到 quoted style)。`dump_proposal` 通过 `forge_yaml_dump()` 走新 dumper。stub / validate auto-render / pr render 路径全部受益,无需在调用处改动。
- **`_split_frontmatter` 保留 closing `---` 之前的换行**: v0.3.1 切下来的 frontmatter slice 不含 `---` 之前的换行,导致 `|`(clip,保留 1 个尾部 `\n`)round-trip 后变成 `|-`(strip)。修 split 把 trailing `\n` 留在 frontmatter slice 里,literal block scalar 的 chomp indicator 现在 round-trip 稳定。
- **`dump_proposal` 不再 rstrip 整个 dump 输出**: v0.3.1 用 `yaml.safe_dump(...).rstrip()`,会把 block scalar 末尾必要的换行也吃掉。改为只在最末尾保证一个 trailing newline,中间的 chomp 语义保留。

### Added

- **`forge proposal reformat <pr-id>` 命令**: 一次性把现有 proposal.md frontmatter 重 dump 成 block-scalar 形态。idempotent(已经 block-scalar 的文件返回 `no change`),body(含 `<!-- BEGIN AUTO-RENDERED -->` / `<!-- END -->` 之间的 §0.5 渲染块)逐字保留。默认写一份 `proposal.md.bak`,加 `--no-backup` 关闭。
- **`forge proposal validate` 默认顺手 reformat**: 默认行为先 reformat 再 validate,变更时打印 `reformatted frontmatter → block-scalar (X → Y bytes)`。加 `--no-reformat` 关闭(用于"我只想 lint 不想动文件"的场景)。

### Migration

现有 v0.3.1 PR(尤其是 `~/personalOS/system/pr/<id>/proposal.md`)建议跑一次:

```bash
forge proposal reformat <pr-id> --root <workspace>
```

或下次 `forge proposal validate` 时 auto-reformat 会顺手处理。语义不变(load → 同 dict),仅 YAML 序列化形态从 flow/folded → block-scalar。

### Tests

新增 `tests/test_v032_yaml_block_scalar.py`(19 cases):dumper 单元、`reformat_text` 行为、CLI 端到端、idempotency、body 保留、`--no-reformat` opt-out。`test_v031_dogfood::test_validate_no_render_flag_skips_auto_render` 加 `--no-reformat` 适配新默认。**总数 281 → 300 通过**(3 skipped 不变)。

### Skill

- `forge` skill doc(`forge/assets/skills/forge/SKILL.md`)v0.3.1 → v0.3.2:"Process Inbox To Proposal" §3 加一段说明 v0.3.2 起 validate 默认 auto-reformat,以及 `forge proposal reformat` standalone 用法。`forge self-install` 同步到 `~/.claude/skills/forge/SKILL.md`。

## 0.3.1 (dogfood) — 2026-05-05

主 agent 在 ~/personalOS 真实跑了一遍 v0.3.0,暴露 13 条问题(8 bug + 5 cosmetic/spec)。本版修齐 12 条(P6 仅文档化无代码变更)。

**核心 UX 修复**:proposal.md body 自身就是 review-ready 的 §0.5 视图 — 用户在 Obsidian 里打开 `system/pr/<id>/proposal.md` 直接看到渲染结果,无需 `forge pr render | cat` 之类。

### Fixed

- **P1 · proposal.md body 现在自带 §0.5 视图 (BLOCKING UX)**: `forge proposal new` 在 body 里写 `<!-- BEGIN AUTO-RENDERED -->` ... `<!-- END AUTO-RENDERED -->` 标记块。`forge pr render` 默认行为变为**写入** body 的标记块之间(in-place,保留 frontmatter 和标记外的用户手写内容);加 `--stdout` 才输出到 stdout(原 v0.3.0 行为)。`forge proposal validate` schema 完整时**自动调 render**,让 body 与 schema 同步;加 `--no-render` 跳过。
- **P2 · stub `disposition:` 字段命名修正,enum 占位放对位置**: v0.3.0 stub 把 `<APPLY|COVERED|...>` 占位放在 `disposition_note:`(非必填字段),agent 容易误改这个 → schema validate 报 missing disposition。v0.3.1 把 enum 占位放在正确的 `disposition:` 字段,占位字符串(`<...|...>`)被 validate / schema 识别为"仍是占位,等同未填",不会乱解析。`disposition_note:` 留空。
- **P3 · stub propagation 形状对齐 validator**: v0.3.0 stub 用 `label: 监控源` / `terminal: true`,但 APPLY validator 要求 `layer:` + `modification:`,agent 不修就提交会 fail。v0.3.1 stub 默认输出符合 validator 形状的 placeholder(含 `layer: 'Layer 0 · monitor source'` + `modification: '<TODO: 改动内容>'`)。
- **P4 · ARCHIVE 不再强制要 propagation**: SKILL.md §2 disposition reference 写明 ARCHIVE 是 "Capture-only audit trail, no propagation",但 v0.3.0 validator 仍要求 ARCHIVE 至少一个 propagation branch — 文档与实现不同步。改 validator:ARCHIVE 的 `_REQUIRED_BY_DISPO` 设为空集,允许空 propagation。如果作者**显式**给了 propagation,structural sanity 检查仍会跑(path/label 必有其一,non-terminal APPLY 节点必有 modification)。
- **P5 / P13 · skill SKILL.md 同步到 user 路径**: sub-agent 改完 `forge/assets/skills/forge/SKILL.md`(forge-core repo),release 完工时显式跑 `forge self-install`,用 v0.3.1 内容覆盖 `~/.claude/skills/forge/SKILL.md`(managed marker 校验)。**注意**: 当前 Claude Code session 不会 reload skill — 主 agent 需要 spawn 新 sub-agent / 开新 session 才能用上新 skill。
- **P7 · shared_with 行尾不再重复列举所有兄弟**: v0.3.0 给 sub 3.2/3.3/3.4 的 b 节点都追加 "(b 与 sub 3.1, sub 3.2, sub 3.3, sub 3.4 共享触发)",4 次重复读着累。v0.3.1 改为:first owner (id 自然序最小,如 3.1) 显示 "(共享触发的子链路, 见 sub 3.2 / 3.3 / 3.4)",列出**其他**兄弟。
- **P8 · 共享传播,后续兄弟只显示一行 abbreviation**: 3.2/3.3/3.4 渲染时,b 节点直接是叶子 "(同 sub 3.1 共享传播)",**不再**完整重复 b → c 子链。canonical owner (3.1) 完整展开。
- **P9 · 处理结果标题始终带 ENUM_NAME + disposition_note**: v0.3.0 标题模板 `[icon] [note 或 ENUM_NAME]` 二选一 — disposition_note 非空时 ENUM_NAME 消失,reviewer 不看 frontmatter 看不出 disposition 是哪个枚举值。v0.3.1 改为 `[icon] [ENUM_NAME] · [disposition_note]`(note 非空时追加,note == ENUM_NAME 时不重复)。`rule:`(APPLY 用)继续以 `· 提炼为 §10` 形式追加。
- **P10 · 提取信息多行内容渲染成 ├─ / └─ 树形**: 多行 `extracted` 不再平铺缩进,自动按行解析:最后一行 `└─`,其余 `├─`。第一行(label 同行)不加前缀。

### Documented (P6)

- **MIXED 父项的 capture 整体归档不计入 disposition 分布**: v0.3.0 的 dogfood 在总分布显示 `📦 × 7` (含 ITEM 2 + 6 dxy_OS legacy sub-items),但 ITEM 3 的 capture 整体也归档了,没单独计数 — 这是**故意**的,v0.3.1 在 SKILL.md 显式写明:"counting rule for MIXED:disposition distribution counts 仅 sub-items, 不算 MIXED 父项"。父项的 archive trail 在 `disposition_note` 文字里说,不作单独 ARCHIVE 行。新增 test 锁定该不变量。

### Changed

- **`forge` skill doc (`forge/assets/skills/forge/SKILL.md`) v0.3.0 → v0.3.1**: "Process Inbox To Proposal" 流程 step 1/3/4 改写以反映新 stub 形状、validate 自动 render、`pr render` 默认 inline 行为。Disposition reference 表 ARCHIVE 行改为 "Propagation is **optional**"。新增 "Counting rule for MIXED" 段。

### Internal

- 新增 `tests/test_v031_dogfood.py`(15 tests),按 P1 / P2 / P3 / P4 / P6 / P7 / P8 / P9 / P10 / P11 一一锁定回归。**关键 e2e**: `test_p11_pure_stub_fill_validates_clean` 模拟"纯净 agent 第一次跑 `forge proposal new` → 用 sed 替换 stub 占位 → `forge proposal validate` 一遍过",作为下次回归的最强保护。
- `test_proposal_cli.py::test_render_cli_outputs_view` 拆分为 `test_render_cli_writes_inline_by_default` + `test_render_cli_stdout_flag`,分别锁住默认 inline 行为和 `--stdout` 行为。
- 全套 `pytest`: **281 passed / 3 skipped** (265 baseline + 1 拆分测试 + 15 dogfood tests)。

### Compat

- v0.3.0 已生成的 proposal.md(body 没有 BEGIN/END 标记)首次跑 `forge pr render` 时,新版本会**追加** BEGIN/END 块到 body 末尾,后续 render 走 in-place 替换。Frontmatter 不动。
- `forge pr render --stdout` 行为与 v0.3.0 默认行为完全相同(向后兼容旧脚本/automation)。
- 旧手写 markdown proposal 不受影响:`forge pr render` 仍报 schema-opt-out 并 exit 2,`forge proposal validate` 仍报"schema not opted in",`forge pr done` / `forge approve` 行为不变。

## 0.3.0 (proposal-render) — 2026-05-05

把 review-gated PR 的"§0.5 监控 item 视图"机制化:agent 不再手写 markdown,改为填一份 schema-aware 的 YAML frontmatter,再用 `forge pr render` 渲染出与手写版形态等价的 §0.5 输出。完全 opt-in,旧的 hand-written proposal 仍兼容。

### Added

- **新模块 `forge.proposal`**: 4 子模块 — `schema` (dataclass + YAML I/O)、`validate` (per-disposition 完整性检查)、`renderer` (确定性模板渲染,box-drawing + ASCII fallback)、`scaffold` (`forge proposal new` 骨架生成)。
- **`forge proposal new --root <root> [--inbox <id-prefix>]`**: 从 pending inbox 文件 + capture frontmatter 生成 `system/pr/<id>/proposal.md` stub,自动预填 inbox_sources / capture_sources / items[] 骨架(每条 inbox 一个 item, monitor_info / extracted 自动填,disposition 留空待 agent 决定)。
- **`forge proposal validate <pr-id> --root <root>`**: 检查 schema 完整性 — 必填字段、disposition 枚举、APPLY 必有 propagation tree(非叶节点必有 modification)、DECIDE 必有 options[]、COVERED 必有 covered_by、NA 必有 reason、MIXED 必有 sub_items[]、shared_with 引用真实存在的兄弟 id。`forge doctor` 风格输出,违规时 exit code 1。
- **`forge pr render <pr-id> --root <root> [--plain]`**: 把 proposal frontmatter 渲染成 §0.5 监控 item 视图 — per-item / per-sub-item disposition + propagation 树 + 合并改动汇总 + approve 流水线 + 一句话总结。`--plain` 切到 ASCII。
- **`forge doctor` 新增 schema 扫描**: 跑完原有检查后,扫 `system/pr/*/proposal.md`,对每个 PR 报告 schema=ok / N issue(s) / opt-out (legacy hand-written)。Info-only,不阻挡 doctor。
- **Disposition 枚举**: `APPLY ✅` `COVERED ⏭` `ARCHIVE 📦` `DECIDE ❓` `NA ➖` `MIXED 🔀`,parser 接受 `ARCHIVE-ONLY` / `N/A` 等友好别名。

### Changed

- **`forge` skill doc (`forge/assets/skills/forge/SKILL.md`) v0.2.2 → v0.3.0**: "Process Inbox To Proposal" 流程改写为 5 步:`forge proposal new` 生成 stub → 填字段 → `forge proposal validate` → `forge pr render` 给用户看 → `forge inbox done`。不再让 agent 手写 markdown proposal。保留 "Fallback: hand-written markdown proposal" 段说明 opt-out 路径。
- **proposal frontmatter schema 扩展**: 在原有 `kind / type / status / created_at / inbox_sources / capture_sources` 之上新增 `revised_at / items[] / summary{}`。Items 嵌套 sub_items[](MIXED)、options[](DECIDE)、propagation[]→PropagationBranch→PropagationNode→children[]。

### Compat

- 旧的手写 markdown proposal 完全兼容 — 没有 `items:` 块的 proposal 走 `forge pr done` / `forge approve` 与 v0.2.x 一样。`forge pr render` 拒绝渲染 schema-opt-out proposal 并给 hint(exit code 2),不会破坏其他流程。
- `forge doctor` 对 schema-opt-out proposal 报 `schema=opt-out (legacy hand-written)` info-only,不视为错误。

### Internal

- 48 条新增测试 (`tests/test_proposal_*.py` × 5 + `tests/test_doctor_proposal.py`):schema round-trip / disposition parse / 完整 §0.5 形态等价(以 dogfood PR `20260505-183300-context-import` 为基准)/ CLI exit code / doctor 集成。全套 `pytest`: 265 passed / 3 skipped (217 baseline + 48 new)。
- §0.5 形态等价测试覆盖:3 items + 28 sub-items 的完整 disposition 分布(4 ✅ + 18 ⏭ + 2 📦 + 1 ❓ + 5 ➖)、所有 propagation path 出现、所有 modification 摘要出现、合并视图正确嵌套(feedback-log → preference → runtime)、approve 流水线 + 一句话总结。

## 0.2.3 (dogfood) — 2026-05-05

dogfood pass 修了 7 条 dxyOS 真实使用中暴露的问题。**纯 bug 修复 + 新架构对齐**, 不引入新功能。

### Fixed

- **Bug 1 · `forge ingest --detect` 推荐改用 `forge capture`**: `--detect` 输出末尾的 "to ingest:" 段过去推荐 legacy `forge ingest --from <path>` / `forge ingest --from-claude-memory`,在 personalOS root 下会把 agent 引到 Bug 2 的死路。改为 "to capture:" 段,推荐 `forge capture --from / --from-claude-memory`,与 SKILL.md 的 import 流程一致。
- **Bug 2 · `forge ingest` 在 personalOS root 不再要求 `forge new`**: legacy `forge ingest` 只检查 `sp/section/` 目录,在 v0428 layout 下报 "not a forge workspace. Run `forge new <root>` first." —— 而 skill 明令禁止 `forge new` 用于 personalOS onboarding。改为检测到 personalOS layout (capture/ / system/inbox/ / context build/) 时,直接以 deprecation-style 警告指向 `forge capture`,exit code 2。Legacy SP root 下 `forge ingest` 行为不变。
- **Bug 3 · monitor 与 detect 对 symlink 源路径报告口径一致**: `forge monitor` 过去显示符号链接 resolve 后的 target (`/Users/.../dxy_OS/01 assist/SP/output/codex/AGENTS.md`),`forge ingest --detect` 显示用户配置的符号链接路径 (`~/.codex/AGENTS.md`)。两者口径不一致。统一为符号链接路径 (即用户/工具实际配置的路径); resolved 路径仅用于内部 digest 比对和向后兼容查找。
- **Bug 4 · skill doc ↔ CLI 命令名对齐 (回归测试)**: 新增 `tests/test_bug_4_skill_cli_alignment.py` pin 住 SKILL.md 中的 `forge capture --from / --from-claude-memory` 与 CLI `--help` 输出一致, 以及 `forge ingest --detect` tail 推荐与 SKILL.md 一致 (Bug 1 修完后自然成立)。
- **Bug 5 · BLOCKER · `forge capture` 同秒并发不再崩溃**: `batch_dir.mkdir(parents=True, exist_ok=False)` 在两条 capture 命令落到同一秒时会让第二条抛 `FileExistsError`。改为冲突时追加 `-1` / `-2` ... 序号后缀 (推荐方案 b),保留 `YYYYMMDD-HHMMSS` 主时间戳的可读性,同时 audit trail 仍清晰可分辨。
- **Bug 6 · `forge inbox list` 数据源与 `forge monitor` 一致**: `inbox list` 过去读 `.forge/governance/inbox/` (legacy),`monitor` 读 `system/inbox/` (personalOS),导致同一 root 下 `monitor` 报 3 个 pending、`inbox list` 输出 "(inbox is empty)"。改为优先列 `system/inbox/*.md`,无 personalOS 文件时回退到 legacy queue。
- **Bug 7 · `forge inbox` group 接受 `--root`**: `forge inbox --root <path> list` / `done` / `skip` 过去全部报 `No such option: --root`。在 inbox group 上加了 `--root`,通过 click context 传给 subcommand;subcommand 自身的 `--root` 仍优先生效 (back-compat)。

### Internal

- 新增工具函数 `_looks_like_personal_os(workspace)` 用于 ingest 路径分流。
- 新增 `_inbox_root(ctx, sub_root)` / `_list_personal_os_inbox(workspace)` 用于 inbox 子命令的 root 解析与 source 选择。
- 13 条新增/更新的回归测试 (`tests/test_bug_*.py`),全套 pytest 217 passed / 3 skipped。

## [0.1.0] — 2026-04-24

首次发布。带 schema 检查、provenance、MVC 分层的 review-gated context compiler。

### MVC 分层（这次最重要的架构修正）

- `Section` = Model，装内容。
- `Config` = Controller，**只装控制信息**。v0.1 第一版把 `preamble` / `postamble` / `body` 放在 Config 里是错的——那是内容，现在全部砍掉，强制走 section。v0.1 直接拒绝这三个字段并给出明确迁移指引，不做向后兼容（alpha 阶段，破坏面可控）。
- `Output` = View，编译产物，不手改。
- **Wrapper section（`type: wrapper`）**：用来承载前言 / 结语这种"不是主体 section"的文字。body 原样输出，不 emit `## <name>` 标题、不参与 heading 降级。约定以 `_` 开头命名。

### 新增
- **Compiler core** — `Section` + `Config` + `Renderer`。YAML frontmatter + markdown body。确定性编译。
- **Section provenance** — frontmatter 字段：`kind`、`upstream`、`generated_by`；`last_rebuild_at` 作为 `updated_at` 的 fallback（兼容 dxyOS 风格 schema）。
- **Config schema** — `required_sections` 由 `forge doctor` 强制。
- **Output frontmatter** — 可选 `output_frontmatter: {...}` 字段，在 compiled 产出顶部 emit 用户指定的 YAML；`generated_by: forge-core@<ver>` 和 `last_rebuild_at` 自动注入（不覆盖用户已提供的字段）。
- **Demote section headings** — 可选 `demote_section_headings: true`，给自带 leading H1/H2 的 section 提供干净层级（strip 首 heading + 其余 demote 一级）。
- **Compiled output provenance** — 每个 CLAUDE.md / AGENTS.md 都带机读 header：config 名、target、SHA256 digest (12 hex)、编译时间、per-section type / kind / upstream / generated_by / bytes。
- **Target adapters** — `claude-code`（→ CLAUDE.md）和 `agents-md`（→ AGENTS.md）。带 `register_adapter()` 用于自定义 runtime。
- **Review gate CLI** — `forge init / status / doctor / build / diff / approve / reject`。
- **结构 bench** — `forge bench snapshot / list / compare`。per-file + per-section byte / line delta、新增 / 删除 section。
- **Schema 健康检查** — `forge doctor` 验证 section 引用、required-section 覆盖、adapter 注册、orphan section、kind=derived 但 upstream 为空。
- **Eval 框架 stub** — `forge.eval` 模块：`EvalTask`、`Runner` ABC、`SimulationRunner`、`EvalReport`、`JudgeVerdict`。6 个默认行为任务。v0.1 是 interface + 参考实现；LLM runner 自己挂。
- **Examples**
  - `examples/basic/` — 最小 4-section 工作区 + 2 个 config。
  - `examples/dxyos-validation/` — 对真实 personal-OS vault 的完整硬核验证：语义等价性（vs vault 自己 SP-compiled CLAUDE.md 的 line recall）、completeness、doctor、gate + bench 循环。还会自动产出 `diff-vs-dxyos.txt` 供人类对比。
- **迁移指南** — `docs/migration-from-personal-os.md`。
- **Eval 报告** — `docs/eval-report.md`，真实 4 任务 × 2 版本 subagent A/B + 4 blind judge，位置随机化，2-2 打平。
- **单测** — 65 个 pytest（section parser、loader、两个 adapter、所有 gate action、bench、provenance、doctor、heading demotion、adapter 扩展、eval 接口、MVC / wrapper）。

### 已验证
- 结构 line recall vs dxyOS 自己 SP-compiled CLAUDE.md：**91.5%**（8.5% gap 是 wrapper 说明文字的措辞差异，不是内容丢失）。
- 编译确定性：同输入两次跑输出 bytes 完全相同。
- Gate 循环（diff → approve → rollback）在真实 vault 内容上通过。
- 行为 A/B eval：4 任务 × 2 版本 subagent + 4 blind judge，位置随机化，2-2 打平，**无行为回退**。

### 已知限制（诚实版）
- 没有 watcher / inbox / auto-ingest。section 手动编辑或脚本编辑。（v0.2）
- 不做 `@file` 包含解析——Claude Code 的 `@README.md` 透传在 runtime 层。要把 @-imported 内容搬进 section，或留一个瘦根 CLAUDE.md 用 `@` import 一个 forge 生成的文件。
- 没有外部 memory provider 的 adapter（Mem0 / Letta / Zep）。（v0.4，症状驱动）
- Bench 是**结构的**，不是 LLM-based。v0.3 加真实 LLM-graded eval harness。
- 没有跨工具 rules sync（超出 claude-code + agents-md）。加一个 adapter 就能扩。

---

*英文版见 [`CHANGELOG.en.md`](CHANGELOG.en.md)。*
