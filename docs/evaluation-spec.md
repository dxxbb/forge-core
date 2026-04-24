# Evaluation pillar 设计

Evaluation 回答 forge 五大 pillar 里最刺的那个问题——**改完之后，系统真的变好了吗？**

v0.1 的 bench 只做结构对比（byte / line / section delta）。真正的 "agent 用这份 context 行为变没变" 要跑真 agent、收集回答、打分。这份 spec 讲 v0.1 的基础 + v0.3 的目标。

---

## 为什么要自己搭 eval

用 `promptfoo` 之类的通用工具可以，但有一件事它们不做：**按 forge 的 section/config 维度聚合**。一个好的 forge eval 应该能回答：

> "这次是改了 `preference.md` 的第 3 行让 agent 回答变差，还是改了 `workspace.md` 的项目列表让 agent 选错了方向？"

这要求 eval 框架和 section 层绑定——哪些 section 影响哪些 task，改完 section 后 diff 哪些 task 的回答。这是 forge eval 不可替代的部分。

通用 LLM 质量评估（"这段代码好不好"、"这个总结准不准"）继续用 `promptfoo`、DeepEval 等工具，forge 不替代。

---

## 三层架构

```
┌─────────────────────────────────────────────────────────┐
│  Task（forge.eval.tasks.EvalTask）                      │
│  - id / prompt / exercises（标注考察哪些 section）      │
└───────────────────────┬─────────────────────────────────┘
                        │
           ┌────────────┴────────────┐
           ▼                         ▼
┌──────────────────────┐  ┌──────────────────────┐
│  Runner              │  │  Judge               │
│  给 (CLAUDE.md, prompt)│  │  给 (task, ans_a, ans_b) │
│  → 真回答           │  │  → winner + reason   │
└──────────────────────┘  └──────────────────────┘
           │                         │
           └────────────┬────────────┘
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Report（EvalReport）                                   │
│  - pairs / verdicts / summary                           │
└─────────────────────────────────────────────────────────┘
```

### Task 层

每个 Task 标注它考察哪些 section（`exercises: list[str]`）。默认 6 个 task 覆盖 identity / workspace / preference / skill / grounding / open-ended。使用者可以写自己的。

### Runner 层

抽象接口：`run(context, prompt) -> str`。v0.1 ship 三种实现：

| Runner                | 用途                                      | 依赖                  |
|-----------------------|-------------------------------------------|----------------------|
| `SimulationRunner`    | 单测用的桩，返回确定性假输出               | 无                    |
| `CallableRunner`      | 包装你自己的函数                           | 无                    |
| `AnthropicRunner`     | 走 Anthropic SDK 真跑                     | `anthropic` 包        |

另外项目里 `examples/dxyos-validation/validate.py` 展示了用 Claude Code Agent 工具（subagent）跑的模式——不作为 core runner 提供，但是 reference 实现。

### Judge 层

抽象接口：`judge(task, ans_a, ans_b) -> JudgeVerdict`。v0.1 ship：

| Judge              | 做法                                             | 代价             |
|--------------------|--------------------------------------------------|------------------|
| `sim_judge`        | 固定返回 tie（给单测用）                         | 0                |
| `AnthropicJudge`   | LLM 盲评，位置随机化；可选 counter-balance（评两遍交换位置） | 每题 1× 或 2× API |

#### 位置偏见是真的

之前在 dxyOS 上跑的一轮（见 `docs/eval-report.md`）4/4 judge 都选 Response 2——要么两组答案真的接近到判官按位置 tie-break，要么判官有 recency bias。`AnthropicJudge(counter_balance=True)` 每题跑两次、位置对调、投票，抵消偏见，代价是 2× API 调用。

---

## v0.1 ship 什么

- `forge.eval` 模块：Task / Runner / Judge / Report 四层抽象接口
- 3 种 Runner（sim / callable / anthropic）+ 2 种 Judge（sim / anthropic）
- 6 个默认 task（`default_tasks()`）
- 单测覆盖接口契约 + 桩 runner / judge
- `examples/dxyos-validation/validate.py` 作为 end-to-end 示例（用 subagent runner 跑过一次 A/B）

## v0.1 **不** ship 什么

- 不提供"标准 task 库"。每个人的需求不一样——身份识别 / 工作流路由 / 技能触发 / 偏好遵守 / 边界 ground 等等，谁关心哪些是私事。v0.3 才可能讨论 canonical task set。
- 不内置 Anthropic 的 batch API / cache 优化。v0.3 做。
- 不做 multi-seed（同一 task 跑 N 次取平均）。v0.3 做。
- 不做成本计算器。
- 不做 human-in-the-loop 审计界面。可以手动编辑 `/tmp/eval-answers.md` 类文件。

---

## v0.3 的目标（roadmap）

| 能力                               | 现状            | v0.3                                         |
|------------------------------------|-----------------|---------------------------------------------|
| 行为 A/B                            | 能跑（小 N）    | ≥ 20 task，多 seed                           |
| 位置偏见                            | counter_balance | 默认开启 + multi-judge 投票                  |
| 成本                                | 无计量          | 每 eval run 出 token 预算 + 实花报告         |
| Task 可复用                         | 每人自己写      | 标准 task 集合（identity / workflow / …）    |
| 归因                                | 看不出哪段 section 影响了哪个 task | 按 `exercises` 聚合分析      |
| Human-in-loop                       | 手动看文件      | 命令行或 web 界面审批/修正判决              |
| 和 CI 集成                          | 手动跑          | `forge eval run --fail-on-regression`        |

---

## 最简用法示例

```python
from forge.eval import default_tasks, run_eval, AnthropicRunner, AnthropicJudge

# 读两个版本的 CLAUDE.md
with open("/tmp/claude-md-before.txt") as f: ctx_before = f.read()
with open("/tmp/claude-md-after.txt") as f:  ctx_after  = f.read()

runner = AnthropicRunner(model="claude-opus-4-7", max_tokens=2000)
report = run_eval(ctx_before, ctx_after, default_tasks(), runner,
                  version_a="before", version_b="after")

# counter_balance=True 抵消位置偏见，代价是 2× API
judge = AnthropicJudge(counter_balance=True)
for pair in report.pairs:
    verdict = judge.judge(pair.task, pair.answer_a, pair.answer_b)
    report.judge_verdicts.append(verdict)

print(report.summary())
# {'tasks': 6, 'judged': 6, 'a_wins': 2, 'b_wins': 2, 'ties': 2}
```

跑这个需要 `pip install anthropic` 和 `ANTHROPIC_API_KEY`。成本大约 $0.05–$0.20 per run（6 task × 2 答案 × ~1000 token + 6 judge × 2 pass × ~500 token，按 Opus 4.7 价格）。

---

## 设计决定解释

**为什么不内置标准 task 集？** 因为 context 是个人化的。一个做研究的人和一个做运营的人对 "好 agent 行为" 的定义不一样。v0.1 只保证接口稳定，task 自定义。

**为什么 Judge 也要通过接口抽象？** 因为 "LLM 当判官" 本身有争议——位置偏见、对齐偏见、风格偏好。抽象接口让你可以插入自己的判官（人工、规则打分、另一个模型）。

**为什么 counter_balance 不是默认开启？** 因为成本 2× 翻倍。在 CI 场景里大量跑 eval 时，默认单次。要发 paper / 对外做严肃对比再开 counter_balance。

**为什么 runner 的 context 参数传整个 CLAUDE.md 内容而不是 file path？** 因为 eval 流程上游经常是"两个字符串"（v1 / v2），读文件是 caller 的事。runner 只管 stateless string-in / string-out。
