# ADR-0008: Observation 只接收真实、未解决、可复验的信号

Date: 2026-08-24
Status: accepted

## Context

0.15.0 的真实一句话验收不再制造高风险 Candidate,但 Agent 把“一次成功项目讨论”和“一次可能成为偏好的表达”都放进 Observation。旧定义“可能复现但证据不足”过宽,把 Observation 变成了所有未晋升内容的默认池。这样虽然暂时不打扰 owner,仍会形成低质量后台垃圾堆,以后也无法判断两个事件是否真的属于同一模式。

## Decision

1. Observation 只接收四种真实信号:`owner-correction`、`observed-failure`、`unresolved-conflict`、owner 已审 Candidate 的 `owner-deferred`。
2. 新建 Observation 必须保存实际发生内容的 `source_context`、另一个独立事件怎样才算同一模式的 `repeat_if`,以及为什么当前不能走 covered、one-off、volatile-state、正确项目落点、closed 或 Candidate 的 `route_gap`。
3. 单次成功调研、可复用任务知识、项目特定决定、一般专业底线、假设风险和“也许以后有用”不进入 Observation。raw evidence 继续由来源系统保留;Forge 给它们正确 disposition 后即可前进。
4. Observation 仍按 theme 聚合 Evidence Event 并到期关闭;同一 theme 的 signal type 不允许静默漂移。历史 Observation 可读,再次刷新时必须补齐新合同。
5. `classify-*` 对 owner 静默;长任务需要心跳时只能说明仍在后台运行以及当前是否出现 owner decision,不得暴露处理数、剩余数、disposition 类型、主题、理由或 Observation 细节。

## Consequences

- Observation 数量会显著减少,但每条都有未来事件可匹配的明确测试。
- 不值得形成资产的成功内容不会被删除;它保留在原始 Memory/capture,只是 Forge 不再复制成第二个池。
- Agent 不能用“先观察”逃避选择正确的代码、状态、项目资产或 closed 去向。

## Supersedes

收紧 ADR-0003 与 ADR-0007 中 Observation 的宽泛准入表述;候选晋升、到期和 owner decision 语义不变。
