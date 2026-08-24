# Forge Run 最新真实验收报告

这是一份滚动更新的最新验收结果，不是设计规范。验收方法与通过条件以
[`run-acceptance-spec.md`](run-acceptance-spec.md) 为准。

## 结论

**2026-08-24 对 `0.20.0` 的真实一句话黑盒验收未通过。**

Forge 已经能正确限制 Owner 前台、分流本批输入并诚实关闭 Run；失败集中在运行成本：
处理 10 个 Review Unit 用了 7.0 分钟、27 次模型调用和 26 次工具调用。测试通过、结果
看起来合理和没有 Candidate，都不能抵消这一项失败。

## 场景与证据

- Forge：`0.20.0`，`forge-core@7798557`
- 唯一初始提示：`forge 一下`
- Codex task：`01a0322a-04f6-7231-9d5e-a24dc0ba06ae`
- 原始 session：`/Users/dxy-air/.codex/sessions/2026/08/24/rollout-2026-08-24T13-06-49-01a0322a-04f6-7231-9d5e-a24dc0ba06ae.jsonl`
- 隔离 checkout：`/Users/dxy-air/.codex/worktrees/c7cc/personalOS`（审计后已删除临时 worktree）
- Run：`run-20260824-130726`
- Run commit：`6e1066b8dcb6`
- 冻结输入：Agent Memory 的 10 / 390 个 Review Unit；本批结束后剩余 380
- 分流结果：`covered=8`、`volatile-state=2`，无 Candidate、无 Observation、无 defer

## 八维证据表

| 维度 | 结果 | 直接证据 |
|---|---|---|
| 触发与路径 | pass | 单句进入 Forge Run，依次执行 status、open、反复 next、close，没有转入 import 或 legacy workflow。 |
| 工作区权限 | pass | 所有 Run 写入和 commit 都发生在 detached 隔离 checkout；没有切换到 canonical personalOS。 |
| 来源真实性 | pass | 10 个输入均来自合同冻结的 Codex Memory Task Review Unit；disposition 保存了具体 sink、locator 和 excerpt。 |
| 分流与观察质量 | pass | 8 条由现有资产覆盖；2 条实际更新对应项目 onepage；没有把剩余内容塞进 Observation。 |
| Owner Review Worthiness | pass | 本批没有达到 Candidate Qualification 的内容，没有制造 case-by-case 或错位的全局偏好卡；coverage 未完成时保持 Candidate Conclusion=`unknown`。 |
| 交互负担 | pass | status 后的 `classify-*` 阶段保持 Owner 静默；close 只发送机器生成的 summary，没有再次泄露单元主题。 |
| 状态真实性 | pass | 最终 Run=`closed`、工作树=`clean`、commit=`6e1066b8dcb6`、Selection Coverage=`incomplete`、Candidate Conclusion=`unknown`、剩余 380，与 Run record 一致。 |
| 成本与收口 | **fail** | session wall-clock 7.0 分钟，27 次模型调用、26 次工具调用；出现多次宽泛 `rg`，单次输出达到 30.0K、25.8K 等。 |

硬失败扫描没有发现不合格 Candidate、资产权威错位、后台语义泄露、跨 checkout 写入或
状态失真；但八维必须全部通过，因此总评仍是 **fail**。

## 复盘与处置

### 保留

- `0.20.0` 的 Owner-Facing Projection：真实对话证明它阻止了后台语义泄露和 close 后的状态改写。
- `0.13.0` 到 `0.19.0` 形成的 Review Unit、Disposition Receipt、Candidate Qualification、Observation 准入、Workspace Authority 和 Closure Snapshot 边界。
- 原始 session 与本报告，作为下一轮设计的失败证据；不把失败改写成“基本符合预期”。
- 原始 session 继续保留；已经完成且工作树干净的隔离 checkout 不再长期占用 worktree。

### 撤回

- 未提交的 `Canonical Coverage Hint` 试验及其合成测试。4 个测试虽然通过，但对本次真实
  10 单元重放时，Forge Review Unit、Agent identity、ELI5 和无痰医疗知识等关键主题的
  正确资产召回不稳定；实现还会为每个单元重复构建完整资产目录。
- 不为这次试验新增领域术语、ADR 或 `0.21.0` 版本。它是失败的探索，不是已接受设计。

## 尚未解决的唯一主问题

Forge 仍把“这个 Review Unit 是否已经被 Canonical Source 覆盖”的发现成本交给 Agent。
下次继续时应先重新定义可接受的 Run 成本和权威映射来源，再选择机制；不要继续给当前
文本排名器调权重，也不要为本次 10 个主题增加关键词特例。
