# ADR-0010: Reviewable Candidate and Run-Owned Settlement

Date: 2026-08-24
Status: accepted

## Context

Forge 0.17.0 的真实一句话验收仍暴露了同一个根问题的三种表现：

1. 0.13.0 产生的一张医疗候选卡只来自一次成功调研。Owner 当时说的是“这次很重要、先判断、再给教程”，不是未来长期沉淀要求；新版本虽然为旧卡补了占位字段，仍把它当作 pending Candidate 推到 Owner 面前。Owner 既看不出为什么提出，也不应该替系统完成准入审查。
2. `volatile-state` 把一个当前 dirty 文件当作写入回执，但 close 没有提交该文件，报告仍称来源 settled。路径存在与工作树 dirty 都不能证明写入属于本 Run、已经持久化或可追溯。
3. 一个 Codex `Task Group` 经常包含多个任务、owner correction、项目状态和可复用知识。强制整个 Task Group 共用一个 disposition，会产生假 covered 或遗漏部分信号；只验证 covered sink 路径存在又放大了这个问题。

这些不是展示文案缺陷，而是 Candidate publication、Review Unit identity 与 disposition authority 的合同缺口。

## Decision

1. Candidate 文件的生命周期与 Candidate Qualification 分轴。只有按当前合同满足 `repeated|owner-directed`、稳定 Evidence Event、准确长期 owner 原话（适用时）、完整 Review Card 和可执行 patch 的 `qualified` 卡，才计入 pending Candidate、Candidate Conclusion 和 Owner 问单。
2. 旧 Candidate 文件继续可读、可审计，但缺当前资格时标记 `legacy-unqualified`。系统不得用占位文案把缺失字段伪装为完整卡，也不得问 Owner 是否批准。原始来源若以后重新达到门槛，按当前合同创建新卡；旧卡不自动继承资格。
3. `run next` 为 qualified Candidate 同时返回结构化 `review_card` 与可读 detail。第一阅读层必须能回答：哪次真实经历触发、为什么不是已有资产/代码/状态/Skill/平台底线、为什么现在达到晋升门槛、准确写什么、以后改变什么。字段存在但内容仍由真实对话验收判断，CLI 不自批语义质量。
4. Codex Memory Review Unit 从 Task Group 收紧为一个 `## Task` 加上 group scope 及明确标注该 Task 的 preference/knowledge/failure 条目。无 Task 结构才回退整个 Task Group；未标注且无法归属的 group 内容形成单独 summary unit，不静默丢弃。
5. Run Contract 可以一次返回最多 3 个后台 Review Unit，称 Background Review Slice。每单元仍独立 disposition、独立 checkpoint、独立 stale check；这只减少 Agent/CLI 往返，不改变 owner 零打扰边界。
6. `covered` 回执必须保存 `coverage_claim`、`coverage_locator` 与在 sink 中真实存在的 `coverage_excerpt`。Canonical Source eligibility 由“当前 checkout 内、Git tracked、非私密、非 capture/system/runtime/临时或生成面”判定，不再靠有限的正向顶层目录硬编码。
7. Run open 保存完整 dirty baseline。`volatile-state` 只有两条合法路径：本 Run ledger receipt；或 Run 开始时不 dirty、之后真实改变、disposition 保存 sink digest 的 Run-Owned Write。close stale-check 后把 Run-Owned Write 与 Run 记录原子提交。Run 前已有 dirty 路径必须拒绝，不能借 Forge close 提交用户内容。
8. 默认 Owner Candidate budget 从 3 降为 1。未展示的 qualified Candidate 保留在系统状态，但不称为 owner 欠下的待办。
9. Forge Run 主 Skill 只保留 Run 所需合同；初始化、导入和 legacy proposal 流程下沉为按需 reference，并由 self-install 一并安装。真实成本验收同时看耗时、模型/工具往返和 Owner 交互，不用测试通过替代。

## Alternatives considered

- 只要求 Agent 多说一句“为什么”：无法阻止旧的、根本不合格的卡进入 Review。
- 自动把所有旧 Candidate 标成 rejected：把系统准入失效伪装成 Owner 拒绝，混淆资格与裁决两条轴。
- 保持 Task Group 单元并允许一个 composite disposition：会把多种去向重新塞回一个复杂对象，checkpoint、覆盖证明和成本都更难验证。Task-level unit 更接近现有 Memory 的显式结构。
- close 时提交所有 dirty sink：会吞入 Run 前已有的用户改动，破坏 checkout authority。
- 为 `medical knowledge base/` 再加一个 allowlist 前缀：继续积累目录特例，没有解决 Canonical Source 的真实属性定义。

## Consequences

- Owner 只会看到系统已经完成资格审查的少量卡；旧卡仍可追溯，但不会继续制造 Review 负担。
- 一部分过去按 Task Group settled 的多任务 Memory 会按更细单元重新进入筛选；这是对旧假覆盖的诚实修复。单任务组可以继承兼容 checkpoint，避免无意义重做。
- `covered` 和 `volatile-state` CLI 参数增加，但它们把原本隐藏在 Agent 文案里的关键事实变成可 stale-check 的回执。
- close 对 Run-Owned Write 取得明确提交权限，但权限只来自 Run baseline 之后的精确路径和 digest；其他 dirty 内容继续保留。
- 主 Skill 变短，非 Run 用户首次进入初始化/导入时会按 routing 再读取一个 reference。

## Supersedes

本 ADR 收紧 ADR-0004/0005 的 Source Settlement 与 Review Unit、ADR-0006/0007 的 Candidate review publication，以及默认 Candidate budget。Evidence Event、Promotion Ground、Observation admission、compile gate、ledger 和 checkout authority 的其他语义继续有效。
