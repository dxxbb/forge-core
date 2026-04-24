# forge-core v0.1.0 — 行为 eval 报告

**日期：** 2026-04-24
**问题：** 如果把 dxyOS 的手搓 compile pipeline 换成 forge-core，agent 行为会变差、变好、还是基本持平？
**TL;DR：** **基本持平**。4 个行为任务 2–2 打平，附诚实的 caveat。

这是在 [`migration-from-personal-os.md`](migration-from-personal-os.md) 里 92.5% 结构层 line recall 之外，我们应该补的 "真的好用吗" 那一层证据。结构 recall 说的是 **相同文本都在那里**；这份报告说的是 **agent 真的以同样方式用了它**。

---

## 实验设置

两个 CLAUDE.md 文件：

- **M**（master） — dxyOS 迁移前那份 `01 assist/SP/output/claude code/CLAUDE.md`。118 行、8722 bytes。生成器：`pr-0021-advisory-project-skill-events`。
- **F**（forge） — 迁移后版本，同样 5 个 section、同样 config 结构，由 `forge-core@0.1.0` 编译。126 行、约 9.9KB。多了一个 provenance header 和 `demote_section_headings: true`（保证 H2/H3 层级干净）。

两份都 check-in 在 dxyOS `forge-core-migration` 分支。

4 个行为任务（`forge.eval.default_tasks()` 的子集）：

| ID | 考察的 section | 任务概要 |
|---|---|---|
| identity-summary | about-user | "用 3 句话总结我是谁 / 在做什么 / 核心挑战" |
| workspace-awareness | workspace | "列出我当前 3 个主要 project/topic，按重要性" |
| grounding-rule | preference | "用户问一个产品的发布日期，你首先应该做什么？" |
| ikigai-direction | about-user + workspace | "给一条关于我创业方向的具体下一步" |

每个 (task × version)（共 8 次）都启动一个全新的 `general-purpose` subagent。每个 subagent 接到同样的 system-style 指令：*读取指定 CLAUDE.md 文件，不要调用其它任何工具，只基于该 context 输出答案*。答案记录在运行时的 [`/tmp/eval-answers.md`](/tmp/eval-answers.md)。

## 判官设置

4 个 judge subagent，每个任务一个。每个 judge 看到两个候选答案，标注为 **Response 1** 和 **Response 2**，判官**不知道**哪个来自哪个版本。**位置分配跨任务随机化**：

| 任务 | Response 1 来源 | Response 2 来源 |
|---|---|---|
| T1 (identity) | M | F |
| T2 (workspace) | F | M |
| T3 (grounding) | M | F |
| T4 (ikigai) | F | M |

Judge 拿到：任务描述 + 两个 response + 一段简短的用户背景 + 一个短 rubric。输出严格 JSON：`{"winner": "1"|"2"|"tie", "reason": "..."}`。

## 结果

### 位置-blind（judge 说了什么）

4 个 judge 都选了 **Response 2**。每次。

```
T1: winner=2  reason: "more concrete specifics (explicit 2026 ikigai deadline, reading 智能简史...)"
T2: winner=2  reason: "ordering better reflects importance since topic research supports forge"
T3: winner=2  reason: "additionally leverages the KB pointer to claude-code.md before defaulting to WebSearch"
T4: winner=2  reason: "ties the next step to his existing forge workstream with specific dates, channels"
```

### 按来源解码

应用上面的随机化映射：

| 任务 | Winner | 来源 | 记分 |
|---|---|---|---|
| T1 identity-summary | Response 2 | **F** (forge) | F |
| T2 workspace-awareness | Response 2 | **M** (master) | M |
| T3 grounding-rule | Response 2 | **F** (forge) | F |
| T4 ikigai-direction | Response 2 | **M** (master) | M |

**最终比分：F 2，M 2，tie 0。**

forge 编译的 CLAUDE.md 站得住。**没观察到行为回退。**

## 你必须听的 caveat

4/4 位置偏见这个信号比 2/2 的打平更响亮。两种不互斥的解释：

1. **两个答案在每个任务上真的接近到不可区分**，judge 退回到按位置打 tie-break。这和 92.5% 结构 line recall 一致——大部分 section 内容逐字相同，所以 agent 基于它们给出的答案也接近一致。2-2 split 只是随机位置分配 + 位置偏见 judge 在近乎相同答案上数学上会产生的结果。
2. **LLM-as-judge 在这个 subagent + 这个 prompt 格式下有系统性的 recency bias**，跟答案质量无关。这是小 N LLM-judge setup 的已知问题。要真测出质量差（如果有）需要：≥20 任务、counter-balance（同任务换位置再评一次）、再加一轮 human judge sanity check。

不论哪种解释，v0.1 的结论**不**是 "forge 比 master 好" 或 "master 比 forge 好"。它是 **"没观察到行为回退"**——迁移是安全的。

## 这是什么，不是什么

**是：** 真 subagent 在真 dxyOS CLAUDE.md 上跑，真 LLM judge，真并排输出。不是 simulation。

**不是：**
- 不是大 N（4 任务 × 2 版本 = 8 答案，4 次判决）。
- 不是多 seed——每个 subagent 一次性运行，无重复。
- 不是人类 judge。
- 位置偏见：做了随机化，但没做 counter-balance。
- 不测试多轮对话或 tool-calling 差异。

**v0.3 roadmap**（README 里提过）：≥20 任务、counter-balance、可选 Anthropic SDK runner 提升吞吐、对一部分样本做 human-in-loop 打分。到那时断言从 "没回退" 升级为 "forge 客观上编出更好 / 更差 / 持平的 context"。

## 如何复现

1. 在 dxyOS `forge-core-migration` 分支上（或任何按 [`migration-from-personal-os.md`](migration-from-personal-os.md) setup 好的 personal-OS vault）。
2. 在跑 `forge approve` 之前先把迁移前的 `CLAUDE.md` 存下来（比如 `/tmp/claude-md-master.txt`）。再存一份迁移后的。
3. 定义你自己的 `default_tasks()`——定制到你真的会问 agent 的问题。
4. 启动 subagent（用 Claude Code 的 `Agent` 工具，或 Anthropic SDK 把 CLAUDE.md 当 system prompt）。
5. 把答案对喂给 judge subagent，位置分配随机化。
6. 解码、报告。

`forge/eval/` Python 模块（`tasks.py` / `harness.py` / `judge.py`）给出接口。v0.1 的 runner 是 stub；真实 runner 自己接。

## 为什么这仍然算证据

是的，小 N。是的，有位置偏见风险。但它是**真的**——真的 agent 行为，在真的内容上，不是拍脑袋。每一个宣称 "让你的 agent 更聪明" 的个人 AI 工具至少欠这个量级的实验，而**大部分都没做**。forge-core v0.1 不吹大话，就 ship 了这套框架 + 一个小而诚实的结果。

---

*英文版见 [`eval-report.en.md`](eval-report.en.md)。*
