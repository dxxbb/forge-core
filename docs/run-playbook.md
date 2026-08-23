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
   → 收集 monitor 的聚合 Source Signal 和未见过的 capture 指纹;
   → Source Signal 只含摘要/计数/指针,不自动复制整个外部语料库;
   → 自动关闭已到期且无新证据的观察。

3. Agent 分流每一条 input
   covered        → 关联已有资产
   one-off        → 修代码/测试/Issue,不建长期规则
   volatile-state → ledger 写入带日期的项目状态/知识
   observe        → 聚合进有期限的 Observation
   candidate      → 生成通过准入校验的 Candidate Asset
   closed         → 写明无价值原因
   defer          → 仅 Source Signal 可用;写明本轮为何不处理,下次重新出现

   每条随后调用:
   forge run disposition <input> --as <kind> --sink <receipt> [--note ...]

4. forge run ask --budget 3
   → conflict / unqualified-change 全量置顶;
   → 其后最多三张 Candidate Asset;
   → certification freshness 不进入问单。

5. 一次只讲一张卡
   - 为什么这是跨场景问题;
   - 独立 evidence;
   - 建议形成什么正式资产;
   - scope 与 exclusions;
   - 准确 patch;
   - 如何在真实任务中验证。

6. owner 一句话裁决
   同意     → forge run decide <id> --approve
   不写     → forge run decide <id> --reject --note <reason>
   继续观察 → forge run decide <id> --observe --note <reason>

   “修改范围 / 我没看懂 / 举例”不产生正式资产写入。解释只在对话中完成;修改用 `forge candidate revise <id> ...` 重写同一张卡,再等待裁决。

7. forge run close
   → 有 unclassified input 时拒绝关闭;
   → 来源仍 actionable 且未 defer 时拒绝关闭;
   → 有 defer 时写“本轮未完成”并报告顺延来源数;
   → 真正干净的空 Run 不写 run 文件、不生成 Git commit;
   → 其余情况报告 dispositions、观察到期、候选裁决、晋升和仍 pending 的候选。
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
- Run 中断:下次 `open` 恢复同一 Run,已经记录的 disposition 不重做。
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
