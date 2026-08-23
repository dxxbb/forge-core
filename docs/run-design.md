# Forge Run 体系设计

**一句话。** Forge 保存全部 evidence,但只让经过独立证据、明确边界和 owner 质检的极少数 Candidate Asset 晋升为正式资产。

资产晋升决策见 [ADR-0003](adr/0003-evidence-to-asset-promotion.md);稳定来源结算见 [ADR-0004](adr/0004-deterministic-source-settlement.md);底层 zone / gate / ledger 决策见 [ADR-0002](adr/0002-forge-run-workflow.md);可测条款见 [run-acceptance-spec.md](run-acceptance-spec.md)。

## 1. 设计目标

Forge 要同时满足:

1. 经历不会因“本轮没价值”而丢失;
2. 一次性缺陷不会被过拟合成永久规则;
3. owner 不需要审全部 Memory、维护队列或清理观察池;
4. 正式资产仍然可追溯、可验证、可修正和可退役。

过去的 Run 已解决“谁能改规则”和“如何追溯写入”,但仍从输入条目出发逐条蒸馏。输入量一大,`covered/archive/certification-due` 也会消耗解释和审查注意力。新的选择单元是跨独立事件聚合的主题,不是输入文件。

## 2. 主流程

```text
持续产生的经历
      ↓
Source Signal(聚合发现,不复制整库)
      ↓ CLI 固定范围
Source Batch(Memory ≤10 / clipping ≤5)
      ↓ 选择性读取/捕获
capture 原始证据(全部保留)
      ↓ Agent 查重、分类、给出 disposition
Source Settlement(推进 provider checkpoint)
 ┌────┼───────────┬──────────────┐
 ↓    ↓           ↓              ↓
覆盖  一次性缺陷   易变状态         可能复现
关闭  代码/测试     带日期落账          ↓
                                  Observation
                                    ↓ 新独立证据
                              Candidate Asset
                                    ↓ owner 质检
                       reject / observe / promote
                                              ↓
                                    Canonical Source
                                              ↓
                                  compiler → runtime
                                              ↓
                              effective / revise / retire
```

Observation 有期限,关闭不删除 capture。Candidate Asset 是唯一正常 review 对象。

Source Signal 与 Evidence 不混用。前者来自 `monitor` 的 Memory、剪藏、投影和项目变化等来源;后者是已经进入 `capture/` 的原始材料。Run 必须覆盖两者,否则会出现“monitor 有 attention,空 Run 却成功”的假完成。由 Agent Memory 或 Web clipping provider 管理的 raw capture 只是同一来源的证据副本,不能再作为 standalone capture 重复筛选。

Source Signal 也不能直接等同于“一次要处理的全部 backlog”。CLI 从支持的 provider 取一个稳定 Source Batch,但批次里的原子对象是 Review Unit,不是 provider 文件。Codex Memory 用 `MEMORY.md` 的 Task Group,Claude Memory 用单个非索引 memory 文件;聚合索引、raw history 和 archived session 只作 evidence pointer/诊断。Agent Memory 每批最多 10 个单元且总计不超过 128 KiB,Web clipping 每批最多 5 个单元。批次 digest 不含不断变化的总数;Run 已打开后,同类新单元留给下一次 Run,不替换本轮批次。

每个 Review Unit 的非 defer disposition 必须产生 Source Settlement。Memory 把准确单元写入 semantic checkpoint;clipping 写入对应处理 marker,其中 `covered` 必须指向已有 canonical asset。多个单元不能共用一条批次 disposition;只在 Run 记录里写一句“处理过”而 provider 仍返回原单元,不算完成。

候选池为空不是全局结论。只要仍有 Source Review Unit 或 standalone capture evidence 未筛选,Selection Coverage 就是 incomplete,Candidate Conclusion 必须是 unknown;只有全部单元都已有 disposition 且没有 pending Candidate 时,才能说“没有候选”。status、持久 Run report 与 close 终态共用这一清单;Observation 已有明确去向,不属于未筛选 backlog。

## 3. 三层状态

### 3.1 Evidence

- 位置:`capture/`;
- 内容:会话、Memory、外部输入、日志等原始材料;
- 性质:可搜索、可追溯,不要求 owner 审阅;
- 不变量:未晋升不等于删除。

### 3.2 Observation

- 位置:`system/observations/`;
- 以 theme 聚合独立 evidence reference;
- 记录首次/最近出现、到期时间、状态和候选关联;
- 到期无新证据自动 `closed: expired`;
- 不是 owner 待办,不进入 Run 问单。

### 3.3 Candidate Asset

- 位置:`system/candidates/`;
- 准入依据仅 `repeated / explicit / high-risk`;
- 卡片必须含 evidence、problem、proposal、scope、exclusions、准确 patch、verification;
- 状态:`pending → promoted|rejected|observing`;
- 每轮最多展示 3 张;完整性冲突不受候选预算压缩。

## 4. 正式写入仍复用原底座

资产晋升不发明第二套写入机制:

- state/KB/project fact:Candidate 批准后走 ledger atomic apply、runtime rebuild、scoped commit;
- rule/preference/skill:批准后同步 verified snapshot,未批准内容不会进入 runtime;
- 所有写入继续保留 evidence、before/after、Ledger-Id、blame 与 revert;
- 未建 Candidate 而直接产生的 rule-zone drift 标为 `unqualified-change`,必须显式处理。

Rule Zone / State Zone 决定“批准后怎么写和怎么保护”;Observation / Candidate 决定“什么值得写”。两者职责不同。

## 5. 用户交互

```text
你:“做一次 Forge”(可附“只有 1 分钟”)
Forge:自动收集、分流、关闭到期观察
Forge:循环执行 `run next`,每次只处理合同指定的一件事
Forge:Memory 只读本批 10 条;clipping 默认只查已有 sink,不擅自启动 deep intake
Forge:来源和 capture 都干净时直接结束,不生成空提交
Forge:一次展示一张候选卡
你:“同意 / 不写 / 继续观察 / 修改 / 解释”
Forge:当场执行或重写同一张卡
Forge:原样报告 close 的 complete / batch-complete / incomplete、Run、工作树、Candidate Conclusion 和剩余可筛选单元事实
```

两次 Run 之间零主动治理打扰。状态 freshness 只在 status/portal 作为审计信号,不产生 certification-due 问项。

## 6. 指标

Forge 不以 imported、processed 或 promoted 数量为成功指标。首版记录:

- disposition 分布;
- pending/promoted/rejected/observing Candidate 数;
- open/promoted/closed Observation 数;
- Candidate 接受率与平均审查时间;
- 有真实使用反馈的正式资产数;
- effective/revise/retire 分布。

这些指标回答“候选是否值得审”和“资产是否真实有用”,不奖励系统制造更多资产。

## 7. 失败边界

| 失败 | 最坏结果 | 保护 |
|---|---|---|
| 同一事件多份摘要被当成重复证据 | 错误 candidate | repeated 强制两个独立 evidence reference;card 仍需 scope/exclusions |
| Observation 堆积 | 隐形垃圾堆 | 到期自动关闭,不进入 owner 待办 |
| Candidate 过多 | review 再次爆炸 | 默认最多三张;不展示的不称为顺延债务 |
| 错误抽象获批 | 正式资产误导 runtime | ledger/revert + verified gate + real-use feedback |
| Candidate apply 失败 | 半套状态 | ledger atomic apply;失败保持 pending |
| Agent 绕过 Candidate 改规则 | 低质量规则进入 runtime | compile gate 使用 verified snapshot,并报 unqualified-change |
| monitor 有变化但 Run 只看 capture | 空 Run 假称处理完 | Source Signal 进入 status/open;未分流拒绝 close |
| Run 中新文件改变聚合 digest | 已做 disposition 失效、交互漂移 | 固定 Source Batch;reopen 不替换本轮同类批次 |
| disposition 不推进 provider 状态 | 下轮重复出现同一批 | Memory checkpoint / clipping marker;close 校验批次已推进 |
| 同一 clipping 同时作为 signal/capture | 同一材料重复审两次 | provider-managed capture 只通过 Source Batch 进入 Run |
| Agent 临场扩大处理范围 | 一次 Run 变成高成本 intake | `run next` 返回唯一 action 与 constraints |
| 未跟踪文件不在 baseline | 旧档案被误报为“新增” | 统一称 unseen;mtime 早于 provider baseline 的文件再单列 historical backlog |

## 8. Legacy

`system/pr`、proposal schema、memory workbench 和批量 Portal review 保留兼容与历史审计,不再扩展。已存在的 workbench 不需要重新审;原始 capture 继续可搜索,只有新 evidence 再次命中相同主题时才参与 Observation。
