# ADR-0012: Machine-owned Owner-Facing Projection

Date: 2026-08-24
Status: accepted

## Context

Forge 0.19.0 的真实单句黑盒验收中，`run next` 已把后台 action 标成
`owner_visibility: silent`，并列出禁止公开的主题、去向和理由。Agent 仍在执行
`classify-*` 时主动解释了 PH Research 的具体状态变化；close 后又用“Forge 完成”
概括 `batch-complete`。CLI 事实是正确的，但负面约束依赖 Agent 自行重写，前台仍然
发生语义泄露和状态失真。

这不是 PH、Forge 或某句话的关键词问题。内部 Review Unit 必须对 Agent 可见才能做
语义分流，而 Owner 前台只能看到极窄的运行状态。缺少的是一个由机器生成、Agent
不能再解释的公开投影。

## Decision

1. Run Contract 增加 **Owner-Facing Projection**。后台 action 的默认投影是
   `silent`；只有确需心跳时，才允许原样发送机器提供的
   `heartbeat_if_required`，不能改写或补充。
2. 后台心跳只表达“仍在运行”和“当前是否需要 Owner 决策”。Review Unit 的标题、
   来源、主题、去向、理由、数量、Observation 和剩余工作继续只存在于内部合同。
3. `forge run close` 根据最终 Closure Snapshot 生成唯一 `OWNER-FACING SUMMARY`。
   它显式包含 `final_state`、Run closed、工作树状态、commit、Selection Coverage、
   Candidate Conclusion 和剩余可筛选单元。Agent 只能原样发送，不得再加“Forge
   完成”等自行概括。
4. `decide-*` 不改成固定话术。Candidate 仍需由 Agent 用简单语言解释真实事件、
   资产缺口、权威落点、晋升依据、准确 patch 和 Owner 决策；固定的是信息边界，
   不是表达风格。
5. 一句话黑盒验收继续按八个行为维度取证，不匹配固定回复。八项均有正面证据且无
   硬失败才算通过；任何证据不足均不得称为“符合预期”。

## Alternatives considered

- **继续增加 forbidden 字段或提示词**：上次合同已完整列出禁区，真实 Agent 仍会把
  内部内容组织成“有帮助的进展说明”。
- **为 PH、Forge 或泄露句式加黑名单**：只能挡当前案例，无法覆盖下一个主题。
- **不把 Review Unit 内容交给 Agent**：会失去语义分流能力，Forge 退化成机械分类器。
- **用固定整段回复做黑盒验收**：会把文风一致误当成机制正确，无法验证资产质量、
  权威、结算和状态真实性。

## Consequences

- 后台过程的 Owner 前台表达更窄、更确定；Agent 仍保留内部语义判断能力。
- close 的公开事实来自一个快照，不再由 Agent 将局部状态升级成全局结论。
- 固定 heartbeat/summary 的单元测试只验证安全投影合同；真实对话是否符合预期仍由
  八维证据审计决定。

## Supersedes

收紧 ADR-0004/0005/0010 的 Run Contract、Closure Snapshot 和 Owner 零打扰边界；
Candidate Qualification、Disposition、Observation、ledger 与 checkout authority
保持不变。
