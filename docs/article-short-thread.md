# 短版（X / 知乎想法 / 小红书 thread，8 条）

*草拟为 8 条推。发之前把 [LINK] 换成真实 repo URL。3/4 条之间和 7/8 之间留截图位。*

---

**1/**
你有没有让 AI "整理一下"它的 `CLAUDE.md` / `AGENTS.md`，结果它悄悄把你真正需要的那段删了？

我有过。这就是我做 `forge-core` 的原因。

**2/**
2026 年的 agent 工具生态分三层很成熟：

- rules sync（rulesync、ai-rules-sync）
- memory 编译器（claude-memory-compiler）
- prompt 编译器（DSPy、BAML）

**没有一个**在你的长期内容和 agent 真的读的 compiled context 之间放 **review gate**。

**3/**
`forge-core` 用 build system 对待代码的方式对待你的个人 context：

- `sp/section/` = canonical source（你改的）
- `sp/config/` = 配方（哪些 section、投给哪个 runtime）
- `.forge/output/` = compiled artifact（从不手改）
- `forge diff / approve / reject` = gate

**4/**
文本 diff 工具不给你的关键东西：**compiled-output diff**。

你编辑 `sp/section/preferences.md` 时，`forge diff` 展示：
(a) source 变了什么，AND
(b) **每个** compiled target（`CLAUDE.md`、`AGENTS.md`、…）会变什么。

如果 output diff 不对，`forge reject` 让你回退。

**5/**
"`make` + `git` 不就够了吗？"

某种程度上够。但你在重新发明：跨多 target 的语义 diff、source tree 上的完整性 hash、结构 bench、append-only changelog、可复现 adapter 契约。

forge-core 就是把这些打包进 ~1k 行 Python。

**6/**
v0.1 的 bench 是**结构**的，不是 LLM eval。

但 v0.1 还 ship 了**真 A/B 行为 eval 的结果**：4 任务 × 2 版本 × 8 subagent 生成 + 4 blind judge。**2-2 打平。没有行为回退**。

小 N、诚实讲局限。见 eval-report。

**7/**
两个 fixture 上端到端验证：

- 最小玩具（`examples/basic/`）
- 真 personal-OS vault，5 个 section、每段 3.3KB+、文件名带空格（`examples/dxyos-validation/`）
- **93.5%** 语义 line recall vs 目标 vault 自己 SP-compiled CLAUDE.md

60 单测。MIT。零托管服务。离线可用。

**8/**
v0.1 是 alpha，breaking change 欢迎反馈。如果你感受过 "我的 CLAUDE.md 悄悄坏了" 的痛，试一下，拆台。

特别希望看到：
- 非 Claude runtime 的 adapter（Cursor、Aider）
- 你觉得 bench 哪些 metric 真的有用

[LINK]

---

*英文版见 [`article-short-thread.en.md`](article-short-thread.en.md)。*
