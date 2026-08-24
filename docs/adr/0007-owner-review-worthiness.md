# ADR-0007: Owner Review Worthiness

Date: 2026-08-24
Status: accepted

## Context

Forge 0.14.0 已能按真实 Evidence Event 去重,并要求 Candidate 展示来源、现有覆盖、晋升依据和准确 patch。独立真实任务仍暴露两种失效:

1. Agent 在后台分类进度中突然念出一条 Observation。它不是 owner 待办,却因缺少来源解释而被误解为待审规则。
2. Agent 从一次成功的医疗调研中想象“如果误判可能伤害用户”,再用 `high-risk` 直接生成医疗回答 Candidate。卡片字段完整,但来源事件没有实际失败或长期 owner 指令;建议还是平台/专业基线,没有证明为什么值得占用个人长期资产和 owner review。

这说明“证据真实”和“卡片解释完整”仍不等于“值得 owner 审”。

## Decision

1. Promotion Ground 只保留 `repeated|owner-directed`。`high-risk` 降为优先级和处理路径信号,不能替代长期资产证据。
2. 单次高风险事件若暴露可确定性控制缺陷,走 `one-off` 的代码、测试或门禁闭环;否则进入 Observation。只有 owner 明确要求未来长期沉淀时,单次事件才可生成 Candidate。
3. Candidate 的 `source_context` 必须描述真实发生的行为、纠正、决定或失败。假设风险和一般领域危险不能充当事件证据。
4. Candidate 新增必填 `asset_fit`:说明为什么 owner 管的指定 Canonical Source 是正确权威落点,而不是代码/测试、易变状态、可复用 Skill、平台/模型通用底线或 Observation。无法说明时不得建卡。
5. Run Contract 明确 owner visibility:`classify-*` 是 background,进度只报聚合数量与是否出现 owner 决策;`decide-integrity` / `decide-candidate` 才进入前台。
6. Candidate review 必须把“为什么值得成为 owner 的长期资产”放进第一阅读层。字段完整仍不代表抽象正确;真实对话验收继续检查来源是否真的支持问题与 Asset Fit。

## Consequences

- 单次医疗/安全/合规场景不会仅凭严重后果制造个人规则。
- 项目特有的高风险门禁仍可在 owner 明确长期要求后进入 Candidate;可确定性实现缺陷无需等重复事件,直接在代码/测试层闭环。
- Observation 继续完整留痕,但默认不占用 owner 注意力。
- `forge candidate create --ground high-risk` 会 fail loud;新卡必须提供 `--asset-fit`。
- 0.14.0 及更早版本的 Candidate 文件仍可读取和审计;新建与修订按新合同执行。

## Supersedes

本 ADR 取代 ADR-0003 和 ADR-0006 中将 `high-risk` 视为独立 Promotion Ground 的部分,并补充 ADR-0003 中“Observation 不是 owner 待办”的前台可见性语义。其他 Evidence Event、Candidate 卡、ledger、compile gate 与 owner 裁决规则保持不变。
