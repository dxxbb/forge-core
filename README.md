# forge

> CLI 名 `forge`,PyPI 包名 `context-forge`。

`forge` 是一个 **review-gated context compiler(带人工质检门禁的上下文编译器)**。它保存全部原始 evidence,但只让经过筛选、验证和 owner 确认的极少数内容成为长期资产,再编译成 `CLAUDE.md`、`AGENTS.md` 等 runtime view。

它不是向量 Memory 产品,也不要求你审全部 Memory。

```text
经历 / Memory / 外部输入
          ↓
  Source Signal → Source Batch(稳定小批次) ──选择性读取──→ evidence
          ↓
   明确分流 → Source Settlement(推进来源状态)
   ├─ covered / one-off / volatile-state / closed
   └─ Observation ──新独立证据──→ Candidate Asset
                                      ↓ owner 一次审一张
                              reject / observe / promote
                                                        ↓
                                   Canonical Source → compiler → runtime
                                                        ↓
                                           effective / revise / retire
```

## 为什么需要它

直接让 Agent 自动积累长期 Memory,容易出现两个相反问题:

- 什么都写,逐渐形成 case-by-case 的规则垃圾堆;
- 什么都说“已经覆盖”,长期没有真正积累。

Forge 把“原始经历”“等待更多证据的观察”“正式候选”“已确认资产”和“runtime 编译产物”分开。资产批准后继续使用既有的 ledger、verified snapshot、scoped commit、blame 和 revert,因此每条内容都能回答“为什么在这里、谁批准、怎样撤销”。

## 安装

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

然后对 Codex / Claude Code 等 Agent 说:

> 用 forge 帮我建工作区,把现有 CLAUDE.md / AGENTS.md 接管起来。

## 日常交互

```text
你:做一次 Forge。今天只有一分钟。

Agent:距上次 9 天。本轮 Memory 固定读取 10 条,剩余 8 条留到下轮。
      CLI 指定当前只处理这一批,不会临场扩大成全量 intake。

Agent:候选:一次性实现缺陷默认在代码和回归测试层闭环,
      不写成永久协作规则。
      证据来自两个独立项目;适用范围与反例在卡片中。
      同意 / 不写 / 继续观察 / 修改 / 解释?

你:同意。

Agent:已通过 ledger 写入 assist config,重编译 runtime 并验证。
      最终状态 complete · Run 已关闭 · 工作树 clean · 剩余可筛选单元 0。
```

两次 Run 之间 Forge 不主动要求你维护观察池或 review 队列。每次默认最多展示三张 Candidate Asset;状态 freshness 只作为审计信号。

## 核心对象

| 对象 | 位置 | 作用 |
|---|---|---|
| Source Signal | Run 记录中的 `source://...` | monitor 发现的聚合入口;不自动复制整个外部语料库 |
| Source Batch | Source Signal 的 `batch_items` | 一次 Run 的稳定上限:Memory 10 个 Review Unit/128 KiB、剪藏 5 个单元 |
| Source Settlement | Run disposition + provider checkpoint | 让已处理批次不再重复出现 |
| Evidence | `capture/` | 原始材料,全部保留、可搜索 |
| Observation | `system/observations/` | 证据不足的主题,有期限、自动关闭 |
| Candidate Asset | `system/candidates/` | 通过准入、等待 owner 质检的一张卡 |
| Canonical Source | personalOS 内容区 / `context build/sections/` | 被系统承认的长期真值 |
| Ledger Entry | `system/ledger/` | 一笔写入的 evidence、patch、commit 与撤销记录 |
| Runtime View | `context build/runtime/` | 给各 Agent runtime 读取的确定性编译产物 |

Candidate 的准入依据只有三种:

- 两个以上独立事件支持;
- owner 明确要求长期遵守;
- 高风险且可确定性验证的不变量。

每张卡还必须写清 `problem / proposal / scope / exclusions / exact patch / verification`。重复频率本身不能替代抽象质量。

## Forge Run CLI

```bash
forge run status
forge run open
forge run next --budget 3

forge observation record --theme "..." --evidence capture/a.md
forge candidate create --help
forge run disposition <input> --as covered|one-off|volatile-state|observe|candidate|closed|defer

forge run ask --budget 3  # 兼容的只读问单;主流程由 run next 驱动
forge candidate show <candidate-id>
forge candidate revise <candidate-id> --scope "..." --exclusion "..."
forge run decide <candidate-id> --approve|--reject|--observe
forge run close

forge candidate feedback <candidate-id> \
  --outcome effective|revise|retire \
  --evidence <real-task-receipt>
```

语义查重、分类和抽象由运行 Forge 的 Agent 完成;CLI 负责确定性的持久状态、准入校验、预算、到期关闭、ledger、compile gate、commit 和统计。

`run open` 固定本轮批次,随后反复调用 `run next --budget N`,只执行合同返回的一个动作,直到它返回 `close`。Memory 每批最多 10 个 Review Unit 且不超过 128 KiB;Codex 以 `MEMORY.md` Task Group 为单元,不扫描聚合索引或数百 MB 原始会话。每个单元必须单独 disposition。Web clipping 每批最多 5 个单元,默认只核对已有 canonical sink,不会自行启动完整 knowledge-intake。来源仍待处理时必须真正推进 provider checkpoint,或带理由 `defer`。

`run close` 的最终状态只有三种:`complete`(无剩余)、`batch-complete`(本批已结算,仍有下一批)、`incomplete`(存在 defer)。它同时返回 Run 是否关闭、工作树 clean/dirty 和剩余具体来源数;Agent 不得用自己的总结覆盖这些机器事实。真正干净的空 Run 不生成记录和 Git 提交。

## 仍然保留的底座

- Rule Zone / State Zone 与 owner 持有的 `zones.yaml`;
- 未批准规则不进入 runtime 的 verified snapshot gate;
- Canonical Source / Runtime View 分离;
- 多 runtime adapter;
- ledger atomic apply、conflict/stale guard、blame、revert;
- Portal 的 provenance、diff 和只读 Candidate card;
- structural bench 与行为 eval harness。

旧 `system/pr`、proposal schema、Memory workbench 和批量 Portal review 仍作迁移兼容与历史审计,不再是启用 Forge Run 后的主流程。

## 常用命令

```bash
forge build / doctor / diff
forge ledger list / blame / revert / reconcile
forge state show / certify
forge audit portal
forge target install / list / remove
forge bench snapshot / compare
forge self-install
forge update
```

## 适配器

| 名字 | 产物 | 类别 |
|---|---|---|
| `claude-code` | `CLAUDE.md` | core |
| `agents-md` | `AGENTS.md` | core |
| `cursor` | `.cursorrules` | contrib |
| `codex-cli` | AGENTS.md variant | contrib |
| `rulesync-bridge` | rulesync input | contrib |

## 当前状态

`0.13.0` Alpha,dogfood 阶段。Review Unit、Selection Coverage 与 Candidate Conclusion 已把“本批 0”与“全局没有候选”分开;语义分类质量与真实长期使用效果仍需连续 Run 验证。

## 开发

```bash
pip install -e '.[dev]'
pytest -q
```

设计入口:[`docs/run-design.md`](docs/run-design.md) · 验收条款:[`docs/run-acceptance-spec.md`](docs/run-acceptance-spec.md) · 决策:[`ADR-0003`](docs/adr/0003-evidence-to-asset-promotion.md)、[`ADR-0004`](docs/adr/0004-deterministic-source-settlement.md)

## License

MIT,见 [`LICENSE`](LICENSE)。

---

*English:[`README.en.md`](README.en.md).*
