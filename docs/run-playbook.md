# Forge Run Playbook(agent 会话协议)

这是 Evidence-to-Asset Promotion 时代的一场 Forge Run。CLI 提供确定性状态、准入、预算、expiry、ledger 与 gate;agent 只承担必须由语义判断完成的分流和抽象。

## 触发与用户负担

只有 owner 说“做一次 forge / forge run / 结算一下”才开始。两次 Run 之间不主动要求 owner 管理观察池、候选或认证队列。

owner 只有两个主动动作:

1. 发起 Run,可同时给预算(如“只有 1 分钟”);
2. 对一次展示的一张候选卡说“同意 / 不写 / 继续观察 / 修改范围 / 解释”。

## 流程

```text
1. forge run status
   → 报距上次 Run、Source Signal attention、完整性问题、pending candidate 数和观察池概况。

2. forge run open
   → 固定本轮 Source Batch 和未见过的 capture 指纹;
   → Agent Memory 每批最多 10 个文件,Web clipping 每批最多 5 个文件;
   → 重复 open 保留原批次,同类新到文件留给下一次 Run;
   → 自动关闭已到期且无新证据的观察。

3. 循环 forge run next --budget N
   → 每次只执行返回的一个 action,不自行改顺序或扩范围;
   → owner 未指定时 N=3;“只有 1 分钟”时 N=0。

   classify-source:
   - Agent Memory 只读 contract.batch_items,不得扫描完整 Memory 或启动另一套 intake;
   - Web clipping 只检查已有 canonical sink,未经 owner 明确要求不得启动 deep knowledge-intake;
   - 其余来源也只执行 contract.handler / constraints 指定的工作。

   classify-evidence / classify-source 的 disposition:
   covered        → 关联已有资产
   one-off        → 修代码/测试/Issue,不建长期规则
   volatile-state → ledger 写入带日期的项目状态/知识
   observe        → 聚合进有期限的 Observation
   candidate      → 生成通过准入校验的 Candidate Asset
   closed         → 写明无价值原因
   defer          → 仅 Source Signal 可用;写明本轮为何不处理,下次重新出现

   每条随后调用一次:
   forge run disposition <input> --as <kind> --sink <receipt> [--note ...]

4. next 返回 decide-integrity / decide-candidate 时,一次只讲一张卡
   - 为什么这是跨场景问题;
   - 独立 evidence;
   - 建议形成什么正式资产;
   - scope 与 exclusions;
   - 准确 patch;
   - 如何在真实任务中验证。

5. owner 一句话裁决
   同意     → forge run decide <id> --approve
   不写     → forge run decide <id> --reject --note <reason>
   继续观察 → forge run decide <id> --observe --note <reason>

   “修改范围 / 我没看懂 / 举例”不产生正式资产写入。解释只在对话中完成;修改用 `forge candidate revise <id> ...` 重写同一张卡,再等待裁决。

6. next 返回 close 时运行 forge run close
   → 有 unclassified input 时拒绝关闭;
   → 来源仍 actionable 且未 defer 时拒绝关闭;
   → 有 defer 时最终状态 `incomplete`;
   → 本批完成但仍有下一批时最终状态 `batch-complete`;
   → 无剩余时最终状态 `complete`;
   → 真正干净的空 Run 不写 run 文件、不生成 Git commit;
   → 原样报告机器返回的 Run 已关闭/仍打开、工作树 clean/dirty、剩余来源数。
```

## 候选准入

至少满足一项:

- `repeated`:两个以上独立事件支持;
- `explicit`:owner 明确要求长期遵守;
- `high-risk`:高风险且能确定性验证的不变量。

并且必须完整提供 `problem / proposal / scope / exclusions / target patch / verification`。同一会话的重复摘要不算独立事件;频率不能替代抽象质量。

## 失败语义

- candidate patch stale / apply failed:保持 pending,报告准确错误,不标 promoted;
- state write 与 certified truth 冲突:保持 held,下一张完整性卡处理;
- 规则区出现未建候选卡的 drift:标记 unqualified-change,不得静默编译;
- 观察到期:只关闭 Observation,不删除 capture evidence;
- Run 中断:下次 `open` 恢复同一 Run,不替换已固定批次,已经记录的 disposition 不重做。
- 未跟踪文件在 provider baseline 之外:显示 `unseen`;可判定早于 baseline 的另标 `historical backlog`,不猜测是否最近产生。

## 真实使用反馈

正式资产在真实任务中使用后记录:

```bash
forge candidate feedback <candidate-id> \
  --outcome effective|revise|retire \
  --evidence <run-or-task-receipt> \
  --note <what-happened>
```

Forge 统计接受率、平均审查时间、有真实反馈的资产数和 effective/revise/retire 分布。资产数量不是成功指标。
