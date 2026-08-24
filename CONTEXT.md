# CONTEXT

forge-core 领域字典。一句话定义,只收本项目独有概念。

## Terms

- **Forge Run(结算 run)** — owner 主动发起的结算式对话:收集 → 分流 → 预算内质检 → 裁决即执行 → 报告。治理的唯一工作流;有头有尾,两次 run 之间系统对 owner 零要求。
- **Source Signal(来源信号)** — `monitor` 从外部 Memory、待综合剪藏、Skill 投影等入口发现的一组待处理事实。它是带计数和证据指针的聚合输入,不是已复制进 `capture/` 的原始 evidence;每次 Run 必须明确处理或带理由顺延。
- **Source Batch(来源批次)** — Source Signal 在一次 Run 中交给 Agent 的稳定、有上限子集。批次由具体文件指针及内容摘要确定;运行期间后来出现的新文件不能使已处理批次失效,剩余项留给下一次 Run。
- **Review Unit(可筛选单元)** — 能够独立判断去向的最小语义单元。它可以是 Source Batch 中的单元或一条 standalone capture evidence;Codex Memory 优先使用 `MEMORY.md` 中一个 `## Task` 及其按 Task 标注的结论，只有没有 Task 结构时才退回整个 Task Group；Claude Memory 使用单个非索引 memory 文件。聚合索引、原始会话流和 provider 元数据不是 Review Unit,只作为 evidence pointer 或诊断信息。
- **Background Review Slice(后台筛选片)** — 一次 Run Contract 可交给 Agent 并行判断的少量 Review Unit，默认最多 3 个。它只减少后台往返；每个 Review Unit 仍必须得到独立 disposition，不能共享结论，也不能进入 Owner 前台。
- **Evidence Event(证据事件)** — 一次真实发生的 thread/session/incident/source encounter,用稳定 `scheme:value` id 标识。Task Group、rollout summary、raw session 和行号都只是它的 evidence pointer;多个指针指向同一经历时仍只算一个事件。
- **Source Settlement(来源结算)** — disposition 对来源 provider 状态产生的持久效果,例如把已审 Memory 批次写入 seen checkpoint,或把已覆盖 clipping 标记到 canonical sink。只写 Run note 而 monitor 数量不减少不算结算。
- **Run Contract(运行合同)** — CLI 根据 Run 状态给出的唯一下一步、范围上限、禁止扩展项与结束事实。Agent 负责批次内语义判断,不能自行扩大为另一套工作流;最终答复以合同返回的 open/dirty/remaining 状态为准。
- **Owner Attention Boundary(Owner 注意力边界)** — Run Contract 对前台打扰的硬边界:`classify-*` 对 owner 静默,长任务需要心跳时只能说明仍在后台运行以及当前是否需要 owner 决策,不能暴露单元主题、来源、去向、理由或 Observation;只有 `decide-*` 和 close summary 可以呈现治理内容。
- **Owner-Facing Projection(用户可见投影)** — CLI 根据 Run action 或 Closure Snapshot 生成的唯一安全前台文本。后台 action 默认不发言;若确需心跳,Agent 只能原样使用合同给出的 heartbeat,不能自行概括后台语义。close 后同样原样使用机器生成的 summary,避免把 `batch-complete` 改写成全局完成。固定的是安全事实边界,不是对 Agent 文风做黑盒验收。
- **Disposition Receipt(去向回执)** — disposition 不只是一枚分类标签,还要证明所选去向真实成立:`covered` 必须保存当前 workspace 内现存、持久、权威且非私密的 Canonical Source、稳定 locator、实际 excerpt 与它覆盖的 claim；`volatile-state` 必须指向同类状态资产，并由 Run 开始时 clean、当前内容 digest 与 close 原子提交共同证明本 Run 的真实写入，或指向本 Run 的 ledger 记录。裸路径、runtime projection、scratch/capture/system 临时文件、Run 前已有 dirty 内容或未发生的状态写入都不是回执。
- **Run-Owned Write(本轮拥有的写入)** — Run 打开时该路径不在 dirty baseline 中，随后由当前 Run 改变且在 disposition 时保存内容 digest 的 Canonical Source 写入。写入所有权按 sink 路径归并：多个 Review Unit 可保留各自当时的语义回执，close 以该 sink 最后一次正式回执做 stale-check 并与 Run 记录原子提交；最后回执后的漂移仍拒绝。Run 前已 dirty 的用户内容不因被选作 sink 而变成 Forge 可提交内容。
- **Closure Snapshot(收口快照)** — Source Settlement 与 close commit 完成后取得的一份来源/候选/工作树终态快照。持久 Run 报告、CLI close 输出与紧随其后的状态判断必须从它派生,不能在 close 前后分别重新拼出两套计数。
- **Workspace Authority(工作区权限边界)** — Forge 写入只属于当前任务所在的 Git checkout。detached worktree 仍是有效隔离根;当前 checkout 与显式 `--root` 若属于同一仓库的不同 worktree,CLI 必须拒绝跨越,不能因“canonical main 更持久”而替 Agent 扩权。
- **Observation(观察)** — 一个由真实 owner correction、observed failure、unresolved conflict 或 owner-deferred Candidate 触发、尚未解决且等待另一独立事件验证的主题。必须保存实际来源情境、什么才算再次出现的 `repeat_if` 和为什么没有更合适去向的 `route_gap`;不接收成功任务摘要、一般正确原则、项目特定事实或“也许以后有用”的内容。观察按 Evidence Event 聚合,有到期日;到期无新事件即关闭,原始 evidence 不删除。
- **Candidate Asset(候选资产)** — 已达到当前 Candidate Qualification、等待 owner 质检的一张卡。卡片必须给出具体来源情境、Evidence Event、现有资产覆盖与缺口、Asset Fit、一般化问题、晋升理由、建议资产、适用/不适用范围、未来行为影响、准确 patch、验证方法与准确裁决问题。
- **Candidate Qualification(候选资格)** — Candidate 进入 Owner Review 前的当前准入/发布门槛：Promotion Ground、独立 Evidence Event、owner 长期原话、完整 Review Card 和可执行 patch 都必须按当前合同成立。历史文件可继续作为审计记录，但缺任一当前要素时是 `legacy-unqualified`，不计入 pending Candidate、Candidate Conclusion 或 Owner 问单；后续若原始来源重新达到门槛，应创建一张按当前合同成立的新卡，而不是让 owner 替系统重做资格审查。
- **Promotion(资产晋升)** — owner 批准 Candidate Asset 后,通过既有 ledger / compile gate 把它写入 Canonical Source。频率本身不构成晋升理由。
- **Promotion Ground(晋升依据)** — Candidate Asset 的准入依据,仅两类:`repeated`(两个以上不同 Evidence Event)或 `owner-directed`(owner 明确要求未来长期沉淀并保留原话)。`high-risk` 只改变处理优先级与控制路径,不替代长期资产证据。
- **Asset Fit(资产适配性)** — 为什么 owner 管的某个 Canonical Source 是当前 durable delta 的正确权威落点,而不是代码/测试、易变状态、可复用 Skill、平台/模型通用底线或 Observation。无法说明 Asset Fit 的主题不是 Candidate Asset。
- **Preference Authority(全局偏好权威)** — 由当前 checkout 的编译关系确定：目标本身是 rule-zone 的 `type: preference` Section，或是该 Section 明示的 upstream，才属于全局偏好权威。它不是 Agent 可自报的标签，也不靠目录名猜测。
- **Owner Correction Evidence(用户纠偏证据)** — 一次用户实际纠偏的准确原话，绑定一个 Evidence Event 和该纠偏发生的 bounded operational context（有边界的实际工作情境）。`repeated` 只有在两个不同事件、两个不同情境中各有用户原话时，才能支持全局偏好 Candidate；同一工作流的事故或内部测试失败只支持该工作流自己的 Skill、代码、测试、状态资产或 closed。
- **Rule Zone(行为规则区)** — 改变 agent 行为的内容(偏好/边界/工作规则)。delta-gated:每笔变更须 owner 在 run 中裁决;预算制(编译后默认 ≤150 行);由编译器结构性强制。
- **State Zone(状态区)** — 信息类内容(项目状态/KB/调研结论)。agent 自由写入、逐笔记账,审阅方式是读即审 + 认证。
- **Zones 配置** — owner 持有的分区声明(路径/段类 → 区);内容不能自我声明区属;本文件属规则区。
- **Compile Gate(编译器 gate)** — 规则区现内容 ≠ verified 快照时,该段以快照编译,差异转待问项。gate 的强制点在编译器,不在流程纪律。
- **Verified 快照** — 规则区每文件/段最近一次经 owner 批准的内容版本;gate 的比对基准。
- **Ledger Entry(账本条目)** — 一笔 canonical 写入的记录(`system/ledger/`):出处、证据、patch、commit 关联(`Ledger-Id:` trailer,1 写入 ↔ 1 commit)。可单笔撤销、可 blame 溯源。
- **Reconcile(对账)** — 用 git diff 捕获脱账编辑并补账/转待问项的确定性过程;使记账不依赖任何人守纪律。
- **Ask Item(待问项)** — 下次 run 要问 owner 的一件事:conflict(冲突,必问置顶)、candidate(候选资产)或 unqualified-change(绕过候选卡产生的规则区改动)。状态新鲜度只做审计信号,不进入问单。
- **Run Budget(提问预算)** — 单次 run 的候选质检上限(默认 1);conflict 与 unqualified-change 不受压缩;超出候选留在其原状态,不形成 owner 待办债务。
- **Selection Coverage(筛选覆盖状态)** — 所有 eligible Review Unit 是否都已有 disposition。来源单元或 standalone capture evidence 存在任一未筛选项时为 incomplete;只有未筛选数为零时才是 complete。Observation 已有明确去向,不属于未筛选。
- **Candidate Conclusion(候选结论)** — `available` 表示已有待审 Candidate Asset;`none` 只允许在 Selection Coverage=complete 且无待审 Candidate 时出现;其余情况必须是 `unknown`,不能把“本批 0 张”说成“没有候选”。
- **Certification(认证/盖章)** — owner 对一个状态文件当前内容的确认动作;此后"未认证变更"基于新快照计算。冲突守卫保护的对象即已认证内容。
- **Settle(落账)** — run 中把蒸馏出的状态区更新逐笔写入并记账的步骤。
- **Stale 守卫** — replace 型写入前校验 base_digest,基准漂移即拒绝,不盲改。
- **Amnesty(大赦迁移)** — 一次性清算历史积压:状态类合并落账(未认证)、超龄易变类 expired 留痕、规则候选转待问项;不得再造清单。
- **Canonical Source / Runtime View** — 既有核心分离:被治理的真值 vs 确定性编译产物。本体系只改变真值的进入与审验方式,不触碰编译分离。

## Relationships

- 1 条 Source Signal → 1 个 Source Batch → 1..N 个 Background Review Slice → 每片 1..3 个 Review Unit → 每单元 1 条 disposition → 每单元 0..1 次 Source Settlement;仍有剩余项时下一次 Run 取得下一批
- 1 次 run → N 条 Source Batch/capture evidence disposition + ≤budget 个 Candidate Asset + 必须处理的 conflict/unqualified-change + 0..1 份持久 run 记录(`system/run/<id>.md`;完全干净的空 Run 不落 Git)
- 1 个 Evidence Event → 1..N 个 evidence pointer;pointer 不参与独立事件计数
- 1 个 Observation → 1..N 个 Evidence Event → 0..1 个 Candidate Asset
- 1 个 Candidate Asset → reject|observe|promote;promote → 1 笔 Ledger Entry
- 1 笔账本条目 ↔ 1 commit(`Ledger-Id:` trailer)
- 1 个规则区文件 ↔ 1 份 verified 快照;快照仅经 run 裁决更新
- 1 个状态文件 ↔ 1 个 certified 日期 + 0..N 笔未认证变更
- Candidate Qualification:qualified|legacy-unqualified；只有 qualified 卡进入 Candidate Asset 生命周期 `pending → promoted|rejected|observing`
- 1 个 repeated 全局偏好 Candidate → ≥2 条 Owner Correction Evidence → ≥2 个 Evidence Event + ≥2 个 operational context；owner-directed 仍由一次准确长期要求成立
- Observation 状态:open → promoted|closed(expired|covered|no-generalizable-value)

## Aliases to avoid

- ~~CP / Change Proposal~~ — ADR-0001 时期的 owner 面概念,已降级为内部账本条目;用户面语言用"待问项 / 账本条目"。
- ~~queue / 队列~~ — 名词式工作流残留;正确说法是"下次 run 的问单"。
- ~~proposal / workbench decision / approve log~~ — legacy,由账本与 run 记录取代。
- ~~把每条 Memory 都蒸馏落账~~ — 输入不是资产;先分流,只有达到 Promotion Ground 的少数主题才能成为 Candidate Asset。
- ~~候选 0 / 没有候选~~ — 批次局部统计不能充当全局结论;有未筛选 Review Unit 时只能说 Candidate Conclusion=unknown。
- ~~explicit ground~~ — “明确”容易把本次任务要求误当长期要求;新建 Candidate 只使用 **owner-directed**,并保存明确要求未来长期沉淀的 owner 原话。
- ~~历史 Candidate 默认继续待审~~ — 历史文件存在不等于符合当前 Candidate Qualification；缺当前准入字段或仍用旧 ground 的记录只保留审计，不进入 Owner Review。
- ~~high-risk ground~~ — 严重后果不等于长期资产证据;高风险单次事件优先走确定性控制修复或 Observation,不能凭假设风险占用 owner review。
- ~~同一工作流反复出错 = 全局偏好~~ — 复发只证明问题真实，不证明资产权威；同一工作流内的纠偏进入其 Skill/代码/测试/状态资产。只有跨情境用户纠偏或 owner 明确长期指定，才有资格占用全局偏好 Review。
- ~~不确定就 Observation~~ — Observation 不是未晋升内容的默认池;没有真实纠正/失败/冲突与可检验复现条件时,应进入已有资产、代码/测试、项目状态或 closed,raw evidence 仍保留。
- ~~detached worktree 不持久所以切回 main~~ — 任务 checkout 就是本轮权限边界;隔离验收不得自行写入 sibling canonical checkout。

## Flagged ambiguities

- "verified" 双义(规则区快照状态 vs 状态区认证)→ 解决:规则区用 **verified 快照**,状态区用 **certified/认证**,不混用。
- "apply" 双义(裁决动作 vs 写盘动作)→ 解决:owner 的动作叫**裁决(decide/approve)**,写盘叫 apply,仅出现在机件层描述。
- "review" 泛化 → 解决:规则区的 review = run 内裁决;状态区的 review = 读即审 + 认证;不再有第三种。
- "evidence" 双义(证明材料 vs 独立发生次数)→ 解决:文件/摘要叫 **evidence pointer**,真实经历叫 **Evidence Event**;只有后者参与 repeated 准入计数。
- "观察" 双义(未晋升素材池 vs 未解决复现假设)→ 解决:只保留后者;成功素材与普通知识不进入 Observation。

## Example dialogue

> **Owner**:做一次 forge。
> **Dev**:9 天没结算了。18 份新 evidence 已分流:covered 9、one-off 3、volatile-state 4、observe 2。没有冲突;有 1 张 Candidate Asset:两个独立项目都把一次性 Bug 写成永久规则,建议以后默认在代码/测试层闭环。适用 Forge 实现缺陷,不适用 owner 明确长期要求。同意、不写、继续观察,还是先解释?
> **Owner**:同意。
> **Dev**:已通过 ledger 写入、更新 verified snapshot 并重编译 runtime。run 已关闭;raw evidence 全部保留。
