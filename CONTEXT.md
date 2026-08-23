# CONTEXT

forge-core 领域字典。一句话定义,只收本项目独有概念。

## Terms

- **Forge Run(结算 run)** — owner 主动发起的结算式对话:收集 → 分流 → 预算内质检 → 裁决即执行 → 报告。治理的唯一工作流;有头有尾,两次 run 之间系统对 owner 零要求。
- **Observation(观察)** — 一个可能复现、但证据尚不足以成为长期资产的主题。观察按独立 evidence 聚合,有到期日;到期无新证据即关闭,原始 evidence 不删除。
- **Candidate Asset(候选资产)** — 已达到晋升门槛、等待 owner 质检的一张卡。卡片必须给出 evidence、一般化问题、建议资产、适用范围、不适用范围、准确 patch 与验证方法。
- **Promotion(资产晋升)** — owner 批准 Candidate Asset 后,通过既有 ledger / compile gate 把它写入 Canonical Source。频率本身不构成晋升理由。
- **Promotion Ground(晋升依据)** — Candidate Asset 的准入依据,仅三类:两个以上独立事件、owner 明确要求长期遵守、可确定性验证的高风险不变量。
- **Rule Zone(行为规则区)** — 改变 agent 行为的内容(偏好/边界/工作规则)。delta-gated:每笔变更须 owner 在 run 中裁决;预算制(编译后默认 ≤150 行);由编译器结构性强制。
- **State Zone(状态区)** — 信息类内容(项目状态/KB/调研结论)。agent 自由写入、逐笔记账,审阅方式是读即审 + 认证。
- **Zones 配置** — owner 持有的分区声明(路径/段类 → 区);内容不能自我声明区属;本文件属规则区。
- **Compile Gate(编译器 gate)** — 规则区现内容 ≠ verified 快照时,该段以快照编译,差异转待问项。gate 的强制点在编译器,不在流程纪律。
- **Verified 快照** — 规则区每文件/段最近一次经 owner 批准的内容版本;gate 的比对基准。
- **Ledger Entry(账本条目)** — 一笔 canonical 写入的记录(`system/ledger/`):出处、证据、patch、commit 关联(`Ledger-Id:` trailer,1 写入 ↔ 1 commit)。可单笔撤销、可 blame 溯源。
- **Reconcile(对账)** — 用 git diff 捕获脱账编辑并补账/转待问项的确定性过程;使记账不依赖任何人守纪律。
- **Ask Item(待问项)** — 下次 run 要问 owner 的一件事:conflict(冲突,必问置顶)、candidate(候选资产)或 unqualified-change(绕过候选卡产生的规则区改动)。状态新鲜度只做审计信号,不进入问单。
- **Run Budget(提问预算)** — 单次 run 的候选质检上限(默认 3);conflict 与 unqualified-change 不受压缩;超出候选留在其原状态,不形成 owner 待办债务。
- **Certification(认证/盖章)** — owner 对一个状态文件当前内容的确认动作;此后"未认证变更"基于新快照计算。冲突守卫保护的对象即已认证内容。
- **Settle(落账)** — run 中把蒸馏出的状态区更新逐笔写入并记账的步骤。
- **Stale 守卫** — replace 型写入前校验 base_digest,基准漂移即拒绝,不盲改。
- **Amnesty(大赦迁移)** — 一次性清算历史积压:状态类合并落账(未认证)、超龄易变类 expired 留痕、规则候选转待问项;不得再造清单。
- **Canonical Source / Runtime View** — 既有核心分离:被治理的真值 vs 确定性编译产物。本体系只改变真值的进入与审验方式,不触碰编译分离。

## Relationships

- 1 次 run → N 条 evidence disposition + ≤budget 个 Candidate Asset + 必须处理的 conflict/unqualified-change + 1 份 run 记录(`system/run/<id>.md`)
- 1 个 Observation → 1..N 个独立 evidence → 0..1 个 Candidate Asset
- 1 个 Candidate Asset → reject|observe|promote;promote → 1 笔 Ledger Entry
- 1 笔账本条目 ↔ 1 commit(`Ledger-Id:` trailer)
- 1 个规则区文件 ↔ 1 份 verified 快照;快照仅经 run 裁决更新
- 1 个状态文件 ↔ 1 个 certified 日期 + 0..N 笔未认证变更
- Candidate Asset 状态:pending → promoted|rejected|observing
- Observation 状态:open → promoted|closed(expired|covered|no-generalizable-value)

## Aliases to avoid

- ~~CP / Change Proposal~~ — ADR-0001 时期的 owner 面概念,已降级为内部账本条目;用户面语言用"待问项 / 账本条目"。
- ~~queue / 队列~~ — 名词式工作流残留;正确说法是"下次 run 的问单"。
- ~~proposal / workbench decision / approve log~~ — legacy,由账本与 run 记录取代。
- ~~把每条 Memory 都蒸馏落账~~ — 输入不是资产;先分流,只有达到 Promotion Ground 的少数主题才能成为 Candidate Asset。

## Flagged ambiguities

- "verified" 双义(规则区快照状态 vs 状态区认证)→ 解决:规则区用 **verified 快照**,状态区用 **certified/认证**,不混用。
- "apply" 双义(裁决动作 vs 写盘动作)→ 解决:owner 的动作叫**裁决(decide/approve)**,写盘叫 apply,仅出现在机件层描述。
- "review" 泛化 → 解决:规则区的 review = run 内裁决;状态区的 review = 读即审 + 认证;不再有第三种。

## Example dialogue

> **Owner**:做一次 forge。
> **Dev**:9 天没结算了。18 份新 evidence 已分流:covered 9、one-off 3、volatile-state 4、observe 2。没有冲突;有 1 张 Candidate Asset:两个独立项目都把一次性 Bug 写成永久规则,建议以后默认在代码/测试层闭环。适用 Forge 实现缺陷,不适用 owner 明确长期要求。同意、不写、继续观察,还是先解释?
> **Owner**:同意。
> **Dev**:已通过 ledger 写入、更新 verified snapshot 并重编译 runtime。run 已关闭;raw evidence 全部保留。
