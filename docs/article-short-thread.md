# 8-条 X / 知乎想法 thread 草稿

*待发。`[LINK]` 位置 push repo 后替换。*

**发布策略见 [`launch-strategy.md`](launch-strategy.md)**——发之前过一遍，覆盖了时间、配图、链接、hashtag、follow-up、前置 checklist。

*配图建议（从 launch-strategy 提炼）：第 1、4、8 这三条配图；其他纯文字。第 1 条用"散乱工具 logo → forge 结构"对比图；第 4 条用 `sp/section/` 目录树 + `forge diff` 输出的真实截图；第 8 条用 demo gif / asciinema。*

---

**1/**

AI 工具越来越多，模型能力越来越强，工具之间的差距在快速收窄。

几年后可能大家用到的 AI 基本一样聪明。

那个体之间的差距从哪儿来？

**2/**

不是 prompt engineering（那个很快就趋同了）。

是你给 AI 看的那份 "你是谁、你怎么工作、你关心什么、你过去判断过什么" 的长期 context。

**这份 context 是你在 AI 时代的差异化形式**。

**3/**

但现在这份 context 散在一堆地方：

- Claude Code 的 CLAUDE.md
- Cursor 的 .cursorrules
- ChatGPT memory（在 OpenAI 那儿）
- Claude memory（在 Anthropic 那儿）
- 一堆聊天记录

每换一个工具，重新搓一次。**你的核心差异化资产，锁在一堆你不拥有的黑箱里。**

**4/**

代码我们用 git 管，笔记用 Obsidian 管，投资用 Excel 管——都是按 **asset** 管。

AI context 没有对应的管理层。多数人当成耗材在用。

应该像 asset 那样管：可理解、可解释、可控制。

**5/**

注意这三条不只是好工程——它们是**反同质化屏障**。

现在主流 memory 路径是"LLM 自动帮你整理"。问题：**LLM 整理出来的越像别的 LLM 整理出来的，你越没差异化**。

可理解 / 可解释 / 可控制 = 保证你的 asset 是"你的"而不是"LLM 觉得你应该是的"。

**6/**

`forge-core` 是基于这个判断的小工具。三件事：

- **Canonical source** 在本地 markdown，不在任何平台里
- **审核关口**：AI 不能绕过你改你的 asset
- **多 runtime adapter**：一份源，编译到 CLAUDE.md / AGENTS.md / .cursorrules / …

换工具不重建。反工具锁定 = asset 的基本属性。

**7/**

和相邻工具的关系老实说：

- `rulesync`（1k 星）管格式，不管 asset
- `claude-memory-compiler`（800 星）把差异化 LLM 黑箱化了
- Claude / ChatGPT memory 不是你的（锁在平台里）
- DSPy / BAML 在另一层（管 AI 怎么想，不管你给它什么 context）

forge 是 0 星 alpha，不硬比。做的是它们**刻意不做**的那半。

**8/**

v0.1 ship 了五大 pillar 各自的最小可跑版本——canonical source / 审核关口 / 编译 / 结构 bench + 行为 A/B eval / 5 个 adapter。88 单测，对真实 personal-OS vault 跑通。

如果你感受过"我的积累每换工具就归零"的痛，来试一下。

[LINK]

---

*英文版：[article-short-thread.en.md](article-short-thread.en.md)。*
