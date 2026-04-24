# 短版（X / 知乎想法 / 小红书 thread，8 条）

*草拟为 8 条推。发之前把 [LINK] 换成真实 repo URL。3/4 条之间和 7/8 之间留截图位。*

---

**1/**
上周你告诉 agent "用 Python，不要 TypeScript"。今天它给你 TypeScript。

你打开 `CLAUDE.md`，preference 那段少了一行。你没 commit 过这个文件，git blame 查不到是谁改的。

不是 agent 缺 memory。是它的 memory 没人管。

**2/**
agent 配置文件 (`CLAUDE.md` / `AGENTS.md`) 你管它用什么？

多数人的答案是"手改，改完祈祷没出事"——等于生产环境裸改代码还不 commit。

**3/**
今天 agent 工具生态三类都不少：

- 规则同步（rulesync，1k 星）——**改了就推，没人审核**
- memory 编译器（claude-memory-compiler，800 星）——**LLM 直接写进你 memory，没 review step**
- prompt 编译器（DSPy / BAML）——**管的是另一层**（agent 怎么想），不是（agent 读哪份上下文）

没有一个在"你改长期内容"和"agent 读到编译产物"之间放一道关口。

**4/**
`forge-core` 做的就一件事：在"你改"和"agent 读"之间加一道关口。

改源文件 → `forge diff` → 同时看到：源文件变了什么，**每一个**编译产物（CLAUDE.md / AGENTS.md）会变成什么 → 满意了 `forge approve`，不满意 `forge reject` 回滚。

**5/**
"`make` + `git` 不就够了？"

某种程度上够。但你自己要实现：跨多目标的语义 diff、整棵源文件树的完整性 hash、结构 bench、只追加的 changelog、可复现的适配器契约。

forge-core 把这些打包成 ~1k 行 Python，就这。

**6/**
v0.1 的 bench 只做结构对比，不是 LLM eval。

但 v0.1 同时跑了一轮**真 A/B 行为评估**：4 任务 × 2 版本 = 8 个子 agent 回答 + 4 个盲评判官。**2 比 2 打平，没有行为回退**。

样本量小、位置偏见风险讲清楚。见 eval-report。

**7/**
两个示例场景上都跑通完整流程：

- 最小玩具（`examples/basic/`）
- 一份真实 personal-OS 工作区，5 段 section、每段 3.3KB+、文件名带空格（`examples/dxyos-validation/`）
- 逐行保留率 **91.5%** vs 目标工作区自己 SP 编译出的 CLAUDE.md

65 单测。MIT。零托管服务，纯本地跑。

**8/**
v0.1 是 alpha，欢迎破坏性反馈。如果你有过"我的 CLAUDE.md 被悄悄搞坏"的感受，来试一下、拆台。

特别想看到：
- 非 Claude 生态的适配器（Cursor、Aider）
- 你觉得 bench 里真的有用的 metric 是什么

[LINK]

---

*英文版见 [`article-short-thread.en.md`](article-short-thread.en.md)。*
