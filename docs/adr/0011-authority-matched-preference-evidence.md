# ADR-0011: Authority-matched evidence for global preference candidates

Date: 2026-08-24
Status: accepted

## Context

Forge 0.18.1 的真实单句黑盒验收生成了候选“Forge 结算必须区分本批完成与全局完成”，目标是 `assist config/work preference/working-style.md`。卡片能解释两个真实事件、现有覆盖、准确 patch 和未来影响，但两个事件都属于 Forge 自己的运行与验收失败；同一规则已经由 Forge Skill、CLI 合同和测试负责。Agent 仍可用一段貌似合理的 `asset_fit` 把工作流缺陷包装成用户全局偏好。

这证明字段完整与事件重复都不足以决定资产权威。复发回答“问题是否真实”，不回答“应该由哪一层长期负责”。

## Decision

1. Candidate target 的语义权威由当前 checkout 的真实编译关系解析。目标本身是 rule-zone 的 `type: preference` Section，或出现在该 Section 的 `upstream` 中时，目标属于 Preference Authority。Agent 不提供这个分类，系统也不靠路径关键词推断。
2. `repeated` Candidate 若目标属于 Preference Authority，必须保存至少两条 Owner Correction Evidence。每条包含 Candidate Evidence Event 中的 `event_id`、准确用户纠偏 `quote` 和 bounded operational `context`。
3. 两条证据必须来自两个不同 event id 和两个不同 operational context。同一工作流内的多个事故、测试失败、Agent 观察或重复纠偏，只能支持该工作流自己的 Skill、代码、测试、状态资产或 closed，不能推导全局偏好。
4. `owner-directed` 不受跨情境数量要求影响：一次明确要求未来长期适用的 owner 原话仍可进入 Preference Authority Candidate，并继续由 Owner Review 决定是否写入。
5. 历史 pending Candidate 若按当前 target authority 需要 Owner Correction Evidence 而缺失，标记 `legacy-unqualified`，保留审计但不进入 Candidate Conclusion 或 Owner Review；不得为旧卡补占位证据。
6. Review Card 第一阅读层展示目标权威解析结果及每条纠偏的情境、事件和准确原话，让 owner 能检查证据是否真的支持全局抽象。

## Alternatives considered

- 为 Forge、monitor 或 working-style 路径增加关键词特例：只能挡住本次卡片，会继续形成产品专用黑名单。
- 继续依赖 `asset_fit` 自由文本：Agent 已证明可以用合理文案绕过权威边界。
- 只要求两个 owner quote、不要求不同情境：同一工作流反复失败仍会被错误放大全局化。
- 所有规则类资产都要求跨情境 owner quote：会阻止以工程证据维护工作流 Skill、代码门禁和其他局部规则，混淆 owner 偏好与实现权威。

## Consequences

- 全局偏好候选更少，但每张卡都能证明“这是用户跨情境的长期选择”，而不只是“系统在某处重复失败”。
- 工作流专用问题更早回到可确定性修复层，减少 owner review 负担和提示词垃圾堆。
- target authority 依赖当前编译 graph；Section type、upstream 或 zone 改变时，旧卡会按当前合同重新判断资格，而不是沿用过期分类。
- CLI 新增结构化 owner-correction 输入；额外成本只发生在稀少的全局偏好晋升点。

## Supersedes

收紧 ADR-0006/0007/0010 中 `repeated` 与 `asset_fit` 对全局偏好 Candidate 的准入语义；其他 Candidate、Observation、gate、ledger 和 Run 合同不变。
