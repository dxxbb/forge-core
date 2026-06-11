# CONTEXT

forge-core 领域字典。一句话定义,只收本项目独有概念。

## Terms

- **Forge Run(结算 run)** — owner 主动发起的结算式对话:收集 → 落账 → 预算内提问 → 裁决即执行 → 报告。治理的唯一工作流;有头有尾,两次 run 之间系统对 owner 零要求。
- **Rule Zone(行为规则区)** — 改变 agent 行为的内容(偏好/边界/工作规则)。delta-gated:每笔变更须 owner 在 run 中裁决;预算制(编译后默认 ≤150 行);由编译器结构性强制。
- **State Zone(状态区)** — 信息类内容(项目状态/KB/调研结论)。agent 自由写入、逐笔记账,审阅方式是读即审 + 认证。
- **Zones 配置** — owner 持有的分区声明(路径/段类 → 区);内容不能自我声明区属;本文件属规则区。
- **Compile Gate(编译器 gate)** — 规则区现内容 ≠ verified 快照时,该段以快照编译,差异转待问项。gate 的强制点在编译器,不在流程纪律。
- **Verified 快照** — 规则区每文件/段最近一次经 owner 批准的内容版本;gate 的比对基准。
- **Ledger Entry(账本条目)** — 一笔 canonical 写入的记录(`system/ledger/`):出处、证据、patch、commit 关联(`Ledger-Id:` trailer,1 写入 ↔ 1 commit)。可单笔撤销、可 blame 溯源。
- **Reconcile(对账)** — 用 git diff 捕获脱账编辑并补账/转待问项的确定性过程;使记账不依赖任何人守纪律。
- **Ask Item(待问项)** — 下次 run 要问 owner 的一件事,仅三类:conflict(冲突,必问置顶)、rule-change(规则区变更)、certification-due(到期认证)。不存在于任何持久"队列"表面,只存在于问单生成逻辑中。
- **Run Budget(提问预算)** — 单次 run 的提问上限(默认 5);conflict 不受压缩;超出者顺延。
- **Certification(认证/盖章)** — owner 对一个状态文件当前内容的确认动作;此后"未认证变更"基于新快照计算。冲突守卫保护的对象即已认证内容。
- **Settle(落账)** — run 中把蒸馏出的状态区更新逐笔写入并记账的步骤。
- **Stale 守卫** — replace 型写入前校验 base_digest,基准漂移即拒绝,不盲改。
- **Amnesty(大赦迁移)** — 一次性清算历史积压:状态类合并落账(未认证)、超龄易变类 expired 留痕、规则候选转待问项;不得再造清单。
- **Canonical Source / Runtime View** — 既有核心分离:被治理的真值 vs 确定性编译产物。本体系只改变真值的进入与审验方式,不触碰编译分离。

## Relationships

- 1 次 run → N 笔落账 + ≤budget 个提问 + 1 份 run 记录(`system/run/<id>.md`)
- 1 笔账本条目 ↔ 1 commit(`Ledger-Id:` trailer)
- 1 个规则区文件 ↔ 1 份 verified 快照;快照仅经 run 裁决更新
- 1 个状态文件 ↔ 1 个 certified 日期 + 0..N 笔未认证变更
- 待问项状态:open → asked → decided(approve/reject)| deferred(顺延,不累积成清单)

## Aliases to avoid

- ~~CP / Change Proposal~~ — ADR-0001 时期的 owner 面概念,已降级为内部账本条目;用户面语言用"待问项 / 账本条目"。
- ~~queue / 队列~~ — 名词式工作流残留;正确说法是"下次 run 的问单"。
- ~~proposal / workbench decision / approve log~~ — legacy,由账本与 run 记录取代。

## Flagged ambiguities

- "verified" 双义(规则区快照状态 vs 状态区认证)→ 解决:规则区用 **verified 快照**,状态区用 **certified/认证**,不混用。
- "apply" 双义(裁决动作 vs 写盘动作)→ 解决:owner 的动作叫**裁决(decide/approve)**,写盘叫 apply,仅出现在机件层描述。
- "review" 泛化 → 解决:规则区的 review = run 内裁决;状态区的 review = 读即审 + 认证;不再有第三种。

## Example dialogue

> **Owner**:做一次 forge。
> **Dev**:9 天没结算了。这期间 4 次会话,11 笔状态更新已落账(project-alpha 6、forge 3、project-beta 2)。待问 3 件,预算内:① conflict——配置值你认证过 A,新会话说换 B;② rule-change——"交付前必须跑 security-review",加 3 行;③ project-alpha 状态 40 天没认证,攒了 9 笔。
> **Owner**:① 新的对;② 加;③ 念重点。
> **Dev**:①② 已执行各自 commit;③ 9 笔里你撤了 1 笔,已盖章。run 报告写好了,下次见。
