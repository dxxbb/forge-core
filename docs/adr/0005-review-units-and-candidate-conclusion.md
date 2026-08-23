# ADR-0005: Review Units and Candidate Conclusion

Date: 2026-08-23
Status: accepted

## Context

ADR-0004 用“每批最多 10 个 Memory 文件”控制一次 Run 的范围，但真实 dogfood 证明文件不是稳定的语义边界。Codex provider 同时暴露任务主题组、聚合索引、持续增长的 JSONL 和数百 MB 原始归档会话；一个文件批次既可能超过实际阅读预算，也会迫使多个性质不同的内容共用一条 disposition。

同一实现还把 `pending candidates = 0` 直接展示为“没有候选”。当 provider 仍有数百项未筛选时，这个数字只说明当前候选池为空，不能证明所有可晋升内容都已处理，也不能证明剩余内容已经进入 Observation。

## Decision

1. Source Batch 的原子分类对象从文件改为 Review Unit。每个 Review Unit 必须独立记录 disposition；批次级非 defer disposition 被拒绝。
2. Codex Memory 的 Review Unit 是 `MEMORY.md` 中一个完整 Task Group。Task Group 引用的 rollout summary / raw session 继续作为 evidence pointer，不在 Forge Run 中重复扫描。Claude Memory 的 Review Unit 仍是一个非索引 memory 文件。
3. `MEMORY.md`、`memory_summary.md`、`raw_memories.md`、session index、history stream 和 archived session 是 provider aggregate/raw surfaces，不计入 Review Unit backlog。Forge 必须报告它们被排除的类别与数量，不能把排除说成已筛选或 closed。
4. Source Batch 同时受单元数与字节数限制。超限内容不能因只计算文件数而进入合同；单个非法超大单元应 fail loud，等待 provider 先压缩成有边界的 Task Group。
5. 新增 Selection Coverage：只要仍有 Source Review Unit 或 standalone capture evidence 未取得 disposition，coverage 就是 incomplete。provider-managed raw capture 是来源证据副本,不重复计数。
6. 新增 Candidate Conclusion：有 pending Candidate 时为 `available`；Selection Coverage complete 且无 pending Candidate 时才为 `none`；其他情况一律为 `unknown`。
7. `forge run status`、`run next`、`run close` 和持久 Run 报告必须使用同一份待筛选清单计算 Selection Coverage / Candidate Conclusion，不允许本批计数替代全局结论。
8. Provider checkpoint 属于 Run settlement。若 checkpoint 文件已被 workspace Git 跟踪，close 的 scoped commit 必须包含它；真正 gitignored 的 side state 保持不提交。
9. Review Unit 身份由稳定 unit id 或输入路径确定,内容 digest 只用于版本/漂移校验。两个内容相同但路径或语义单元不同的输入不能共享 disposition。

## Alternatives considered

- 继续限制“10 个文件”并增加一句提示：不能解决聚合文件尺寸、mixed disposition 和全局零候选误导。
- 扫描所有 archived sessions：复制造价极高的完整 intake，而且绕过 Codex 已有的 Task Group 消化层。
- 只改最终文案为“本批 0”：能减少误解，但系统内部仍无法证明哪些内容已经筛选，后续状态和报告会继续漂移。

## Consequences

- 旧 file-level Memory checkpoint 保留用于兼容监控，但不再作为 Candidate Selection Coverage 的证明。
- 旧 schema 的 closed Run 已记录过的 capture path+digest 视为历史 disposition,不把同一批证据重新制造成 backlog；内容变化后 digest 不同,仍会重新进入筛选。
- 第一次启用 Review Unit checkpoint 时，既有 Task Group 会诚实显示为未筛选；不得用历史 file-level `seen` 自动冒充已完成筛选。
- Run 可以继续按小批结束，但在 backlog 清零之前候选结论始终是 `unknown`。
- owner 仍只审 Candidate Asset；Review Unit 的 covered/closed/observe/candidate 分流由 Agent 在合同范围内完成。
