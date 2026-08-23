# ADR-0003: Evidence-to-Asset Promotion

## Context

ADR-0002 把持续治理收敛为 owner 主动发起的 Forge Run,并保留 rule zone、compile gate 与 ledger。真实 Memory intake 继续暴露一个上层失效:Run 仍从“逐条蒸馏输入”出发,大量 `covered/archive/certification-due` 内容会占用解释与审阅注意力;同一事件的重复记录也可能被误当成长期规律。

## Decision

1. Run 的选择单元从“输入条目”改为“跨独立事件聚合的主题”。原始 evidence 全部留在 `capture/`,不因未晋升而删除。
2. evidence 先得到明确 disposition:covered、one-off、volatile-state、observe、candidate 或 closed。只有 observe/candidate 进入新的系统状态。
3. `system/observations/` 保存有期限的 Observation。到期无新增独立 evidence 自动关闭;它不是 owner 待办队列。
4. `system/candidates/` 保存 Candidate Asset。准入至少满足一项:两个以上独立事件、owner 明确长期要求、可验证高风险不变量。
5. Candidate Asset 必须携带 evidence、problem、proposal、scope、exclusions、准确 patch 与 verification。频率不能单独替代这些字段。
6. Run 问单只包含 conflict、Candidate Asset 与绕过候选机制形成的 unqualified rule change。候选默认每轮最多 3 张;状态文件 freshness 只在 status/portal 审计,不再产生 certification-due 问项。
7. owner 对候选只做 approve、reject 或 observe。approve 复用 ledger、compile gate、scoped commit 与 runtime rebuild;reject/observe 均保留 evidence。
8. Portal 保留 provenance/diff 审计能力,但主要 review surface 改为一次一张候选卡。旧 proposal/workbench 只作 legacy evidence,不再进入主流程。

## Consequences

- owner 成本由输入量决定改为由少量晋升候选决定。
- Forge 不再用“写了多少”代表 Memory 价值;报告区分 evidence、observations、candidates、promotions 与 closures。
- 自动语义分类仍由运行 Forge 的 agent 完成;CLI 只提供确定性的状态、准入校验、预算、执行与审计。
- 错误抽象仍可能发生,因此首版保持人工晋升门禁并记录接受/拒绝/回观察的结果,不做无审核自动晋升。

## Supersedes

本 ADR 取代 ADR-0002 中“逐条蒸馏落账”和 `certification-due` 进入 Run 问单的部分。ADR-0002 的 zone、compile gate、ledger、owner-initiated Run 与无后台打扰原则继续有效。
