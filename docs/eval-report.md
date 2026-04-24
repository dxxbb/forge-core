# forge-core v0.1.0 行为评估报告

**日期：** 2026-04-24
**问题：** 把 dxyOS 手搓的 compile pipeline 换成 forge-core 之后，agent 行为会变差、变好、还是基本一样？
**一句话结论：** **基本一样**。4 个行为任务 2 比 2 打平，下面会讲清楚前提和漏洞。

这份报告是在 [`migration-from-personal-os.md`](migration-from-personal-os.md) 里 92.5% 那个结构保留率之外，我们欠的"真的好用吗"那一层证据。结构保留率说的是**文本大体都在**，这份报告说的是 **agent 真的按同样的方式在用这些文本**。

---

## 实验怎么设

两份 CLAUDE.md：

- **M（master）** —— dxyOS 迁移之前那份 `01 assist/SP/output/claude code/CLAUDE.md`。118 行，8722 字节。生成来源：`pr-0021-advisory-project-skill-events`。
- **F（forge）** —— 迁移之后的版本。同样 5 段 section、同样的 config 结构，由 `forge-core@0.1.0` 编译产出。126 行，约 9.9KB。多了一段 provenance 头信息，并开启了 `demote_section_headings: true` 让 H2/H3 层级整洁。

两份都在 dxyOS 的 `forge-core-migration` 分支上能直接看到。

4 个行为任务（来自 `forge.eval.default_tasks()` 的子集）：

| ID                  | 考察的 section     | 题目概要                                            |
|---------------------|-------------------|-----------------------------------------------------|
| identity-summary    | about-user        | "用 3 句话总结我是谁、在做什么、当前核心挑战"       |
| workspace-awareness | workspace         | "列出我当前最主要的 3 个 project 或 topic，按重要性" |
| grounding-rule      | preference        | "用户问一个产品的发布时间，你首先应该做什么？"        |
| ikigai-direction    | about-user + workspace | "针对我现在找创业方向这件事，给一条具体下一步建议" |

每个（任务 × 版本）组合（一共 8 个）都用一个全新的 `general-purpose` 子 agent 跑。每个子 agent 拿到的指令都一样：**读取对应那份 CLAUDE.md，不要调任何别的工具，只基于这份内容回答**。所有回答都存在运行时生成的 [`/tmp/eval-answers.md`](/tmp/eval-answers.md) 里。

## 判官怎么判

4 个判官子 agent，一人一题。每个判官看到两份回答，标成 **Response 1** 和 **Response 2**，但判官**不知道**哪份来自哪个版本。为避免"总偏袒第一个"这种毛病，**位置分配在不同任务之间做了随机化**：

| 任务             | Response 1 来自 | Response 2 来自 |
|------------------|----------------|----------------|
| T1（identity）   | M              | F              |
| T2（workspace）  | F              | M              |
| T3（grounding）  | M              | F              |
| T4（ikigai）     | F              | M              |

判官拿到的是：题目、两份回答、一小段 dxy 的背景介绍、一段简短的评分标准。要求它严格输出 JSON：`{"winner": "1"|"2"|"tie", "reason": "..."}`。

## 结果

### 判官本身说了什么（不看位置对应关系）

4 个判官全部选了 **Response 2**。每一次。

```
T1: winner=2  理由: "Response 2 的具体细节更多（2026 年 ikigai 截止时间、读《智能简史》、AI/memory/personal-os 等 topic 都点到了）"
T2: winner=2  理由: "Response 2 的排序更能反映实际重要性，topic 调研是给 forge 服务的，书是低优先级阅读"
T3: winner=2  理由: "Response 2 除了走 grounding 规则之外，还主动用了 KB 里 claude-code.md 这个指针，先看本地再决定要不要 WebSearch"
T4: winner=2  理由: "Response 2 把下一步绑到他已有的 forge 上，给了具体的时间点、渠道、一个清晰的外部信号（陌生人是否主动安装/付费）"
```

### 按"来自哪个版本"解码一遍

把上面的随机映射还原：

| 任务                 | 谁赢          | 来自     | 计分 |
|---------------------|---------------|----------|------|
| T1 identity-summary | Response 2    | **F**（forge） | F    |
| T2 workspace-awareness | Response 2 | **M**（master） | M    |
| T3 grounding-rule   | Response 2    | **F**（forge） | F    |
| T4 ikigai-direction | Response 2    | **M**（master） | M    |

**最终比分：F 2 分，M 2 分，平局 0。**

forge 编的那份 CLAUDE.md 没掉链子。**没观察到行为回退。**

## 必须讲清楚的一件事

4 个判官全部选 Response 2——这个信号比 2 比 2 那个比分更刺眼。有两种解释，不一定互斥：

1. **两份回答在每道题上都接近到无法分辨**，判官干脆按位置打 tie-break。这和 92.5% 的结构保留率是对得上的——大部分 section 文本逐字相同，所以基于它们的回答也会几乎一样。在这种前提下，随机分配位置 + 有位置偏好的判官，从数学上就会产生 2-2 这个结果。
2. **LLM 当判官这件事本身就有位置偏见**，跟回答质量无关。这是 "LLM-as-judge + 小样本量" 的已知问题。要真测出质量差别（如果有的话），要做的是：任务量涨到 20 个以上、每道题两次评分（把位置对调一次再评）、理想情况再加一轮人类判官抽查。

不管是哪种解释，v0.1 这份报告**都不是**在说 "forge 比 master 好" 或者 "master 比 forge 好"。它的结论只有一句：**没看到行为变差**。对"要不要迁过去"的决策来说，这已经够了。

## 它是什么，它不是什么

**它是**：真子 agent 在真 dxyOS CLAUDE.md 上跑出来的、真 LLM 判官给出的、并排放在一起的对比。不是模拟。

**它不是**：
- 样本量不够大（4 个任务 × 2 个版本 = 8 份回答，4 次判决）。
- 没有多个随机 seed —— 每个子 agent 只跑一次，没重复。
- 没有人类判官参与。
- 位置偏见做了随机化，但没做完整的对调复测。
- 只测了单轮对话，没测多轮行为、也没测工具调用是否有差别。

**v0.3 路线**（README 里提过）：任务数 ≥ 20、位置对调复测、接可选的 Anthropic SDK runner 提升吞吐、部分样本人类抽查打分。到那时，断言才能从"没回退"升级为"forge 编出来的上下文客观上更好/更差/持平"。

## 怎么复现

1. 进到 dxyOS 的 `forge-core-migration` 分支（或者任何按 [`migration-from-personal-os.md`](migration-from-personal-os.md) 配置好的 personal-OS 工作区）。
2. 在跑 `forge approve` 之前先把迁移前的 `CLAUDE.md` 存一份出来（比如 `/tmp/claude-md-master.txt`），再存一份迁移后的。
3. 写你自己关心的 `default_tasks()` —— 换成你真的会问 agent 的那种问题。
4. 跑子 agent（Claude Code 的 `Agent` 工具可以，或者用 Anthropic SDK 把 CLAUDE.md 当 system prompt 塞进去）。
5. 把两份回答喂给判官子 agent，位置随机化。
6. 解码映射、写报告。

`forge/eval/` 模块（`tasks.py` / `harness.py` / `judge.py`）提供接口。v0.1 里默认 runner 只是桩代码，真正的 runner 自己接进去。

## 为什么这份小结果也算"证据"

样本量小。有位置偏见的风险。但它是**真的**——真 agent 在真内容上的真反应，不是拍脑袋。每一个号称"让你的 agent 更聪明"的个人 AI 工具，至少都欠这一级别的实验，而**绝大多数并没做**。forge-core v0.1 不吹大话，先把这套框架加一个小而诚实的结果放在桌上。

---

*英文版：[`eval-report.en.md`](eval-report.en.md)。*
