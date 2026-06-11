# ADR-0002: 工作流抽象为 forge run;资产分两区;编译器承担 gate

Date: 2026-06-10
Status: accepted (supersedes ADR-0001 的工作流与决策面部分;其机件层条款保留)

## Context

ADR-0001 确立了 CP 作为唯一 review 原语与"approve 自动执行至 commit"。继续推演后发现更深一层的问题:CP 队列仍是**名词式工作流**——一个持续存在、等 owner 打理的地方。运行期的全部失效(搁置、腐烂、无脑通过)都源于名词式抽象对稀缺、碎片化注意力的错配;在其上叠加车道/TTL/周报属于体验优化,未触及根因。同时,前序设计把 gate 寄托在流程纪律(agent 自觉走流程、人记得审)上,纪律是最弱环节,而 forge 本就握有一个确定性强制点:编译器。

## Decision

1. **工作流抽象 = 一个动词**:`forge run`,owner 主动发起的结算式对话——有头有尾、预算制提问(冲突 → 规则候选 → 到期认证)、裁决即执行、结束即干净。两次 run 之间系统对 owner 零要求;不存在任何持久的待办表面(队列/收件箱/工作台)。
2. **资产分两区,机械划界**(owner 持有的 zones 配置,内容不能自我声明区属):行为规则区 delta-gated 且预算制(编译后默认 ≤150 行);状态区自由写入、逐笔记账、读即审(认证机制)。
3. **gate 从工作流搬进编译器**:规则区现内容 ≠ verified 快照 → 该段以快照编译,差异转待问项。控制从"希望守规矩"变为"结构上不可能绕过"。
4. **CP 降级为内部账本条目**(`system/ledger/`):patch 契约、base_digest stale 守卫、scoped commit、原子 apply、1 写入 ↔ 1 commit(trailer 关联)全部保留为执行机件;不再作为 owner 面对的概念。
5. **portal 收缩为只读审计面**;ADR-0001 第 4 条(portal 升级为决策+执行面)废止,serve 决策端点不实现。
6. **冲突守卫**:与已认证内容矛盾的写入永不静默落地,置顶下次 run。

## Alternatives considered

- **CP 优先级队列 + portal 决策面**(ADR-0001 路线):审"变更流",成本 ∝ 流入量,无界;且需要 portal 访问习惯与 serve 端点等持续维护面。
- **会话内插话 / hook 注入提案**:污染工作心流,且把 gate 建在模型自觉上;会话收尾恰是注意力最低时刻,结构性复刻无脑通过。owner 明确否决。
- **cron 离线自动蒸馏作为 v1 地基**:正确方向但非根本,且有实现/维护成本;v1 在 run 内联完成,离线化留作 plus。

## Consequences

- 实现面大幅收缩:serve 决策端点、token、并发锁、cron、digest 管道、独立的优先级/TTL/车道机制,v1 全部不建。
- 必建三件:zones+编译器 gate、账本(含对账/撤销/blame)、run CLI 骨架 + playbook skill。
- 旧概念退役:workbench 决策字段、proposal.md、approve/reject log(由账本与 run 记录取代);`forge/proposal/` 进入 legacy。
- 最坏失败模式被设计为"陈旧但安全":owner 长期不 run,规则冻结、状态留痕流动,损失新鲜度不损失控制权。
- 风险移位:蒸馏质量成为主要变量,由单笔可撤 + 冲突守卫 + 认证人眼兜底,并在 run 报告中量化。
