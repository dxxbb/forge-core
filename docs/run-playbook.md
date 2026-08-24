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
   → Agent Memory 每批最多 10 个 Review Unit/128 KiB,Web clipping 每批最多 5 个单元;
   → 重复 open 保留原批次,同类新到文件留给下一次 Run;
   → 自动关闭已到期且无新证据的观察。

   工作区边界:
   - 所有命令只使用当前任务 checkout 的 Git root;
   - detached worktree 是有效隔离根,不得切到 canonical/main;
   - CLI 会拒绝同一仓库 sibling worktree 的显式 `--root`。

3. 循环 forge run next --budget N
   → 每次只执行返回的一个 action,不自行改顺序或扩范围;
   → owner 未指定时 N=3;“只有 1 分钟”时 N=0。

   classify-source-item:
   - Agent Memory 只读 contract.review_unit 及 evidence pointer,不得扫描完整 Memory 或启动另一套 intake;
   - Web clipping 只检查已有 canonical sink,未经 owner 明确要求不得启动 deep knowledge-intake;
   - 其余来源也只执行 contract.handler / constraints 指定的工作。

   classify-source:
   - 仅用于尚无 Review Unit adapter 的单一来源合同,不得自行拆批或扩流程。

   classify-evidence / classify-source-item 的 disposition:
   covered        → 关联已有资产
   one-off        → 修代码/测试/Issue,不建长期规则
   volatile-state → ledger 写入带日期的项目状态/知识
   observe        → 仅把真实、未解决且有明确复现条件的信号聚合进 Observation
   candidate      → 生成通过准入校验的 Candidate Asset
   closed         → 写明无价值原因
   defer          → 仅 Source Signal 可用;写明本轮为何不处理,下次重新出现

   每条随后调用一次:
   forge run disposition <source> --item <unit-id> --as <kind> --sink <receipt> [--note ...]
   forge run disposition <capture-input> --as <kind> --sink <receipt> [--note ...]

4. next 返回 decide-integrity / decide-candidate 时,一次只讲一张卡
   - 为什么现在提出,来自哪些 Evidence Event;
   - evidence pointer 只是来源入口,不作为独立事件计数;
   - 现有资产覆盖了什么、真正未覆盖什么;
   - 为什么这次晋升不是 case-by-case 过拟合;
   - 建议形成什么正式资产;
   - scope 与 exclusions;
   - 准确 patch 与写入后的行为影响;
   - 如何在真实任务中验证,以及 owner 正在决定的准确问题。

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
   → 原样报告机器返回的 commit、Run 已关闭/仍打开、工作树 clean/dirty、Selection Coverage、Candidate Conclusion 与剩余 Review Unit 数;
   → backlog 未清零时只能说候选结论 unknown,不能把“本批 0 张”说成“没有候选”。
```

## 候选准入

至少满足一项:

- `repeated`:两个以上不同 `event-id` 支持;
- `owner-directed`:owner 明确要求未来长期沉淀,并保存准确原话;

`high-risk` 只改变优先级和控制路径,不单独构成 Promotion Ground。单次高风险事件若存在确定性控制缺陷,走 one-off 的代码/测试/门禁闭环;若有真实纠正/失败/冲突但尚不能晋升才进入 Observation;只有假设风险则 closed。只有 owner 明确要求未来长期沉淀时才能从一次事件建 Candidate。

并且必须完整提供 `source-context / existing-coverage / asset-fit / promotion-rationale / expected-effect / decision-question / problem / proposal / scope / exclusions / target patch / verification`。`source-context` 只能写真实发生的行为、纠正、决定或失败,不能把假设风险当事件证据;`asset-fit` 必须说明为什么 owner 管的长期资产是正确落点,而不是代码/测试、易变状态、Skill、平台通用底线或继续观察。同一会话的 Task Group、rollout summary 和 raw session 共用一个 event id;用户只要求本次认真处理不算 owner-directed;频率不能替代抽象质量。

Observation 不是“其余内容池”。新建时必须使用:

```bash
forge observation record \
  --signal-type owner-correction|observed-failure|unresolved-conflict \
  --source-context <实际发生了什么> \
  --repeat-if <另一独立事件怎样才算同一模式> \
  --route-gap <为什么不是其他 disposition> \
  --event-id <stable-event-id> --evidence <pointer>
```

单次成功调研、可复用任务知识、项目特定决定、一般专业底线或“也许以后有用”分别走 covered、正确项目/状态落点或 closed,不复制进 Observation。Owner 把已审 Candidate 退回观察时使用内部 `owner-deferred`。

分类与 Observation 是后台工作,进度只能报已处理数、剩余数和是否出现 owner 决策;不能报 source title、disposition 类型、主题、理由或 Observation 细节。只有 Candidate / conflict / unqualified change 进入前台。

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
