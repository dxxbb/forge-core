# 为什么我做了一个 agent context 的 asset 管理器

*草稿——还没发。*

---

## 模型能力正在被拉平

AI 工具最近几年冒出得太快了。Claude Code、Cursor、Codex、Windsurf、Aider、ChatGPT、Claude.ai、还有一堆 memory 插件、rules 同步器。每个工具的卖点都是"我比别的聪明一点 / 快一点 / 便宜一点"。

但往长时间尺度看，这种"工具之间的差距"一直在收窄。Claude 出了新能力，几周后 Cursor 跟上，几个月后 Codex 也有。模型层的差距缩得比想象得快。

**结果是：你用哪个工具的上限越来越被你手里的 AI 本身决定**。工具带来的差距在变小。

那个体差异化的空间在哪？

## 差异化在于你给 AI 的 context

我有个朋友做独立开发，另一个在大厂做 staff，第三个是律师。三个人用的都是 Claude Opus。模型一样、API 一样、价格一样。

但他们让 AI 干出来的东西完全不一样。差别不在 prompt engineering（那个其实很快趋同），**差别在他们各自给 AI 看的那份 "你是谁 / 你在做什么 / 你关心什么 / 你过去判断过什么" 的长期 context**。

独立开发的朋友在 CLAUDE.md 里积累了两年的技术品味、对 framework 的偏见、"这种情况下我不要 TS" 的硬约束。staff 朋友积累了她的职级预期、她对 code review 的标准、她怎么给新人讲解架构。律师朋友积累了他处理过的合同模式、他的 citation 规范、他怎么翻译客户的口语要求。

**这些东西是 AI 推不出来的。只能从他们自己那里来。它是他们在 AI 时代的真正差异化**。

## 但这份 context 现在在哪？

散落在：

- Claude Code 的 `CLAUDE.md`
- Cursor 的 `.cursorrules`
- ChatGPT 的 memory（在 OpenAI 服务器上）
- Claude 自带的 memory 工具（在 Anthropic 服务器上）
- 几十个聊天记录截图
- "我上次跟 AI 说过什么来着" 的脑内回忆
- 某个 agent 自动抓取并"帮你整理"的神秘黑箱

每换一个工具，重配一次。每一份都是手工搓的，没结构、没版本、没历史。去年 Claude 价格翻倍的时候，一批用户搬到 Cursor，迁移成本全在"我的身份 / 偏好 / 工作方式要怎么带过去"这件事上。

这是工具层的失败模式——**你的核心差异化资产，被锁在一堆你不拥有的黑箱里**。平台改协议、涨价、停服，或者你只是想换个工具，都会让你的积累归零。

## 把 context 当数据 asset 来管

同样是"我关心的长期内容"，代码我们用 git 管——commit、diff、review、branch、rollback 一整套。笔记我们用 Obsidian / Notion 管。投资组合我们用 Excel / Notion 管。

但 AI context 没有对应的 asset 管理层。多数人的做法是"手工搓 CLAUDE.md 然后复制粘贴到别的工具"。这是**把 asset 当耗材**。

把 context 当 asset 管意味着三件事：

**1. 可理解** —— 打开就能看懂。不是向量，不是 embedding，不是 LLM 整理出来的"关键决策摘要"。是你能用人类语言读的东西。

**2. 可解释** —— 每一段能追溯来源。这段是哪天加的？从哪次会话来的？上次改它是为什么？如果你连自己 CLAUDE.md 里的一段话从哪来的都说不清，那段话其实不算你的 asset，它只是"现在在那里的字符"。

**3. 可控制** —— 你说删就删，说改就改，说回滚就回滚。**AI 不能绕过你修改自己的身份叙事**。

这三条看起来是工程实践，但它们其实是**反同质化的屏障**。

## 黑箱 memory 的隐形代价

现在主流的"AI memory"路径是让 LLM 自己抓你的会话、自己整理成 memory 文件。Anthropic 和 OpenAI 都有这个，社区也有 `claude-memory-compiler` 这类工具。

这个路径有个隐形代价，大家不太谈：**LLM 整理出来的东西越像别的 LLM 整理出来的东西，你越没差异化**。LLM 的结构偏好、语言选择、摘要风格都有强烈的基模型痕迹。让它代你管 memory，你的 asset 会逐渐趋同到模型的"平均审美"。

真正的差异化来自**你自己的判断、你自己的语言、你自己决定留什么丢什么**。一段亲手打磨的 about-me，会带着你独特的语气、你关心的顺序、你对自己身份的当下叙述——这个东西 LLM 模仿不出来。

所以"可理解 / 可解释 / 可控制"这三条，不是锦上添花的工程特性。它们是你的 asset 为什么是"你的"的前提。

## forge 做什么

`forge-core` 是在这个判断上做的小工具。三件事：

**1. Canonical source 在本地。** 你的长期 context 活在 `sp/section/` 下的 markdown 文件里，不活在任何平台服务里。你的 git，你的硬盘，你的 asset。平台涨价、停服、换协议，asset 不受影响。

**2. 确定性编译 + 审核关口。** 源文件编译成各个工具要读的 view（CLAUDE.md / AGENTS.md / .cursorrules / …）。每次改源文件要经过 `forge diff` 看编译后长啥样，`forge approve` 才推给工具，不行 `forge reject` 回滚。AI 不能绕过你修改你的 asset。

**3. 跨工具。** 一份源内容，编译成多个 runtime 的 view——换工具不重建。反工具锁定是 asset 的基本属性之一。

```
         你改这里              forge 编译            agent 读这里
┌────────────────────┐    ┌─────────────┐    ┌──────────────────┐
│  sp/section/       │──▶│ sp/config/   │──▶│  CLAUDE.md        │
│ （asset 本体，本地、│    │（选哪几段、  │    │  AGENTS.md        │
│  版本化、你拥有）  │    │  投给谁）    │    │  .cursorrules     │
└────────────────────┘    └─────────────┘    └──────────────────┘
                                                      ▲
                                                      │
                                           关口：发布之前看一眼
```

## 不是关口才重要——但关口是你主权的证据

这听起来像是个"加了 git workflow 的 CLAUDE.md 生成器"。实际上它更大一点。区别在这：

一个纯 generator（`agents-md-generator` 之类）的潜台词是 "你告诉我怎么生成，我就生成"。它做的是**格式转换**。

一个 review-gated asset manager 的潜台词是 "你来决定什么进 asset，我负责把它可靠地送到各个 runtime"。它做的是**权威性分发**。

两者的差别在于：前者是工具，后者是**一个小型的、以你为中心的 context 权威源**。

v0.1 的审核关口（`forge diff / approve / reject`）在这个叙事里是**你拥有 asset 的证据**。没有关口，就没有"AI 不能绕过你改 asset"的保证；没有这个保证，asset 就不真是你的。

## 为什么不是 rulesync / memory compiler

对标几个真实存在的工具：

| 工具 | 它做什么 | 哪里不对 |
|---|---|---|
| `rulesync`（1k 星） | 规则同步到 20+ 工具 | **管格式，不管 asset**。没有 canonical source，没有审核，没有来源追溯 |
| `claude-memory-compiler`（800 星） | LLM 抓会话整理成 memory | **把差异化黑箱化**。自动化 = LLM 替你决定你的身份叙事 |
| Claude memory / ChatGPT memory | 平台自带 | **不是你的**。平台锁定，换工具就没 |
| DSPy / BAML（33.6k 星） | 编译 prompt 逻辑 | **另一层**。它们管 AI 怎么想，不管你给 AI 什么 context |

实诚地说规模：forge-core 是 0 星 alpha，DSPy 是 33.6k 星大项目。不是硬比。最近的对标是 `rulesync` 和 `claude-memory-compiler`——但我做的是它们**刻意不做**的那半（审核、canonical source、人决定而非 LLM 决定）。

## v0.1 里具体有什么

五大 pillar 各有最小可跑版本：

| Pillar | v0.1 程度 |
|---|---|
| **Canonical Source** | markdown section + frontmatter + MVC 分层 |
| **Governance**（审核关口） | diff/approve/reject/doctor 完整；watcher/inbox/rollback 是 stub |
| **Context Compiler** | 2 core adapter（Claude Code、AGENTS.md）+ provenance + 确定性 |
| **Evaluation** | 结构 bench 完整，行为 eval 框架 + Anthropic SDK runner/judge |
| **Adapters** | 2 core + 3 contrib（Cursor、Codex CLI、rulesync bridge） |

88 个单测，对真实 personal-OS vault（一个跑了几个月的实际工作区）端到端跑通，91.5% 逐行保留率，行为 A/B 2 比 2 打平（没回退）。

每个 pillar 都有独立 spec，明说 v0.1 做到什么、刻意不做什么、v0.2/0.3/0.4 要补什么——不是 roadmap 空头支票。

## 什么时候用 forge、什么时候不用

**适合你的情况：**

- 你已经有一份长期演进的 CLAUDE.md / .cursorrules / memory，想好好管
- 你用不止一个 AI 工具（或者预感以后会换），不想重建
- 你在意"这些内容是从哪里来的"可追溯性
- 你不希望 AI 自动往你的 context 里写东西

**不适合的情况：**

- 你的 context 就是几行 "be concise"——没必要 over-engineer
- 你有上千条微事实要做 retrieval——那是 vector store 的事，不是 forge 的
- 你想要"AI 自己帮我整理 memory"——那你想要 `claude-memory-compiler`，不是 forge

## 想请你做的

如果这些话中了你的感受——"每换一个工具我的积累就没了"、"我不知道我 CLAUDE.md 里的那段到底从哪来的"、"我不想 LLM 自己整理我"——你是我想要的用户。

试一下、拆台、告诉我哪里不对。特别希望：

- 第二个非 Claude 生态的适配器真跑起来（Aider、其他 agent runtime）
- 更好的 diff UX
- 真实使用场景下的 asset 演进模式报告——大家到底怎么积累自己的 context，我想学

Repo：*（还没 push 到 GitHub）*。

---

*草稿作者：dxy，2026-04-24。v0.1.0 alpha。*

*英文版：[article-draft.en.md](article-draft.en.md)。*
