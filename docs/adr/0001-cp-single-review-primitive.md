# ADR-0001: CP 是唯一 review 原语,approve 自动执行至 git commit

Date: 2026-06-10
Status: superseded by [ADR-0002](0002-forge-run-workflow.md)(工作流与决策面部分;机件层——patch 契约、stale 守卫、scoped commit、原子 apply、1 变更 ↔ 1 commit——由 ADR-0002 第 4 条保留)

## Context

forge 运行一段时间后,review 体系出现系统性失效:三套审阅形式并存(proposal.md /
workbench.md item 决策 / 直接编辑的 git diff),决策记录分散且不可查询;大批量
import(38 条 memory items)在 batch 串行结构下整体搁置;diff 不可读导致 owner
无脑通过——gate 把未审内容洗成"已审真值"。根因:系统假设 owner 有充足成块的审阅
时间,而真实约束是**注意力稀缺且碎片化**。

## Decision

1. **CP(Change Proposal)是对 canonical source 的唯一变更入口和唯一 review
   原语**:patch(target/anchor/before→after)+ 证据 + 影响 + 状态机,
   file-per-CP 存于 `system/cp/`。来源(monitor capture / bulk import / agent
   会话)只改变证据形态,不改变审阅与决策机制。
2. **workbench 退役为 triage 工作纸**:它过滤信号(IGNORE/COVERED/emit-CP),
   不再承载用户决策;`user_decision`/`final_action` 字段废止。
3. **approve 即执行,终点是 git commit**:apply patch → 重编译受影响 runtime →
   验证 section→runtime 映射 → 仅 add CP 触及的文件 → commit(`CP-Id:`
   trailer,1 commit ↔ 1 CP)。安全护栏:apply 前校验 diff 基准,目标文件已被
   其他变更先动则 CP 转 `stale` 退回,绝不盲 apply;commit 前 fresh 读取当前
   分支并记入账本。
4. **portal 从只读审计面升级为决策+执行面**(serve 增加本地决策端点)。只读
   原则保留给审计视角;决策面必须能行动,否则 owner 充当消息总线,决策被摩擦
   推迟。

## Alternatives considered

- **统一到 GitHub PR 机制**:评审粒度是段落/事实级而非文件级,评审者是单一
  owner 而非团队,workspace 本地优先。借用 PR 心智模型,不引入其机制。
- **保留三套表单,只做 UI 聚合**:不解决决策记录分散与机制不一致的根因,
  agent 仍需理解三套流程。
- **approve 止于写文件,不自动 commit**:provenance 断在文件层,账本与 git
  历史无法一一对应;owner 选择了完整自动化(决策记录于本 ADR 同日)。

## Consequences

- approve log / reject log 退役为 CP 账本的状态视图;applied CP 即 derive
  record,audit graph 的 `declared_without_derive_record` gap 随覆盖率上升
  而结构性消亡。
- agent 对 canonical source 的直接写入被禁止,必须经 CP;owner 手改在后续
  阶段以 auto-CP 记账(本 ADR 不覆盖其实现)。
- `forge/proposal/` 模块进入 legacy 期,新功能不再扩展它。
- 后续阶段(风险车道 / provisional / 优先级衰减 / gate 周报)以本 ADR 的
  CP 状态机为地基,见 CONTEXT.md 术语表。
