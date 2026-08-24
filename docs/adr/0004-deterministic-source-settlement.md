# ADR-0004: Deterministic Source Settlement and Run Contract

Date: 2026-08-23
Status: accepted

## Context

ADR-0003 把 monitor 的外部变化接成聚合 Source Signal，并要求每条信号在 Run 内得到 disposition。真实 dogfood 证明这仍不足以稳定交互：`agent-memory` 的聚合计数会在会话期间增长，导致已写 disposition 失效；`web-clipping` 写入非 KB canonical asset 后仍持续报警；Agent 面对同一个聚合信号会临场选择整批 defer、完整 knowledge-intake 或其他不同流程。CLI 能阻止假关闭，却不能保证一次低成本、有进展的处理。

## Decision

1. 每个支持的 Source Signal 必须提供一个稳定、有上限的 Source Batch。首版 Agent Memory 每批最多 10 个文件，Web clipping 每批最多 5 个文件。
2. 批次 digest 只由批次内具体 item 的路径与内容 digest 决定，不包含不断变化的总 backlog 数；同一批在 Run 期间保持稳定。
3. 非 defer disposition 必须触发 provider-specific Source Settlement。Memory 结算推进 seen checkpoint；clipping 的 covered 结算写入 canonical sink marker。`covered` 只接受当前 workspace 内被跟踪的权威非私密 Canonical Source；`volatile-state` 还必须有本 Run 的真实状态写入或 ledger 回执。裸路径和只写 Run note 都不算结算。
4. 一批处理完成但同类来源仍有剩余时，允许关闭 Run，状态称 `batch-complete`，并报告剩余来源；下一次 Run 获取下一批。未处理批次仍只能 defer，状态称 `incomplete`。
5. `forge run next` 提供 Run Contract：唯一下一步、批次范围、允许动作和禁止扩展项。Memory 批次只做有界语义分流；clipping 默认只查 existing canonical sink，未经 owner 明确要求不得升级成完整 knowledge-intake。
6. `forge run close` 在 close commit 后形成唯一 Closure Snapshot,把同一份 Run 是否关闭、工作树是否干净、当前剩余来源与候选结论写回 Run commit并返回 CLI。Agent 最终答复不得覆盖这些事实。

## Alternatives considered

- **只修改 Forge Skill 提示词**：成本最低，但仍依赖不同 Agent 对同一提示的解释，无法推进 provider checkpoint，也无法机械验证最终状态。
- **一次导入完整 Memory 语料库**：能生成稳定快照，但重建了高成本大 review surface，并复制数百 MB 外部语料。
- **保持聚合 Signal，每轮手工挑文件**：没有持久 cursor；新文件到达会改变 digest，重复劳动与交互漂移仍然存在。

## Consequences

- Agent 仍负责语义质量，但不能决定批次大小、跨工作流扩张或最终状态口径。
- Run 可以诚实地区分 `complete`、`batch-complete` 与 `incomplete`。
- provider 需要实现小而明确的 batch/settlement 接口；新增来源不能只提供 monitor 文本。
- 历史 evidence 不删除；checkpoint 表示已分流，不表示已晋升为资产。

## Superseded in part

[ADR-0005](0005-review-units-and-candidate-conclusion.md) 将本 ADR 的“Memory 文件批次/整批 disposition”收紧为“有字节上限的 Review Unit 批次/逐单元 disposition”，并规定 Candidate Conclusion 的全局真实性。稳定批次、provider settlement、`complete|batch-complete|incomplete` 和唯一 Run Contract 继续有效。
