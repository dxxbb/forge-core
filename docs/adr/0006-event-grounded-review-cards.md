# ADR-0006: Event-grounded Candidate Review Cards

Date: 2026-08-24
Status: accepted

## Context

第一次真实对话验收中,Agent 把 `MEMORY.md` Task Group 和它指向的 rollout summary 当成两份独立证据,又把 owner 对一次医疗调研的“这次要认真调研”解释成明确的长期要求。系统因此把单次、仍可能过拟合的经验晋升成 Candidate。CLI 只校验 evidence 字符串数量和 `explicit` 标签,无法区分文件指针、真实经历和长期 owner 指令。

同一 Candidate 的持久文件其实保存了部分“为什么”,但 `run next` 只要求 Agent 展示候选卡,真实回答最终压缩成一句抽象规则。Owner 看不到触发事件、与现有资产的差异、晋升理由或写入后的行为影响,因此没有足够信息裁决。

## Decision

1. Evidence Event 与 evidence pointer 分离。Observation 和 Candidate 都保存稳定 `event_ids`;独立事件数只由去重后的 event id 计算。多个文件、摘要、行号或镜像指向同一 thread/session/source event 时共享一个 id。
2. 新建 Candidate 的 ground 只允许 `repeated|owner-directed|high-risk`。`explicit` 不再是创建接口:owner-directed 必须保存 owner 明确要求未来长期沉淀的准确原话;high-risk 必须保存可验证不变量与失败条件。
3. repeated 至少需要两个不同 event id。两个 evidence path 即使内容不同也不能替代两个事件。历史 Observation/Candidate 缺 event id 时保守映射为一个 legacy event,不凭文件数补造独立经历。
4. Candidate 创建前必须比较目标与直接相关 canonical asset。卡片新增 `source_context`、`existing_coverage`、`promotion_rationale`、`expected_effect` 与 `decision_question`;原有 problem/proposal/scope/exclusions/patch/verification 继续保留。
5. `run next` 返回完整 owner decision context,并明确禁止 Agent 只展示 proposal 句子。展示允许自然语言重组,不要求固定模板,但不得遗漏为什么现在提出、来源事件、现有覆盖与缺口、晋升依据、未来影响、准确 patch 和裁决问题。
6. 当 Agent 的诚实建议仍是“继续观察”时,必须直接创建/更新 Observation,不能先创建 Candidate 再把不成熟判断转嫁给 owner。
7. 真实对话验收按多维证据判断,不按固定句子匹配:来源可追溯、准入成立、抽象不过拟合、与现有资产协调、owner 可理解写入影响、Run 状态诚实、治理边界正确、成本有界。

## Alternatives considered

- 只修改最终回复模板:不能阻止同一事件被重复计数,也不能阻止单次要求冒充长期要求。
- 用 evidence 内容 hash 去重:同一事件的 Task Group 和 rollout summary 内容不同,仍会被误计为两个事件;不同事件也可能有相同摘要。
- 自动用语义模型判断是否过拟合:不可确定、难以回归验证,也会把 owner 的治理门禁重新变成模型自批。首版保留 Agent 判断,但让输入合同和 review evidence 可检查。

## Consequences

- Candidate CLI 参数更多,但候选本应稀少;额外成本发生在晋升点,不施加给所有输入。
- 旧自动化使用 `explicit` 创建 Candidate 会 fail loud,必须说明长期 owner 原话或改走 Observation。
- Owner 不再只审一句听起来正确的规则,而是审“这次经历是否足以形成什么长期资产以及会改变什么”。
- 真实对话仍可能暴露语义质量问题;验收必须报告逐维证据,不能由测试通过或单一顺眼回答替代。
