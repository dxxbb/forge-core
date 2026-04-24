# 为什么我做了一个 review-gated context compiler（以及 `rulesync` 为什么不够）

*草稿——还未发布。*

---

## 这件事没人在做

2026 年的 agent 工具生态分三层成熟，少了一层。

**第一层：rules sync。** `rulesync`、`ai-rules-sync` 这类工具拿你的 agent 指令，在 Cursor、Claude Code、Copilot、Codex、Gemini、Windsurf 之间镜像。一份真相，八份生成的配置。挺好。

**第二层：memory 编译器。** `claude-memory-compiler` 这类工具 hook 你的会话，抽取"关键决策"，用 LLM 把结果组织成结构化的 memory 文章。也挺好。

**第三层：prompt 编译器。** DSPy、BAML 把你的 prompt 逻辑编译成优化过的调用 pattern。它们在另一层——编译 **程序**，不是 **内容**。

缺的那层夹在这三者中间：**一个给你长期内容做的 review-gated 编译器**。

我不想要又一个自动往我 memory 文件里写的工具。也不想要又一个把我输入的任何东西塞进八个 runtime 的 sync 工具。我想要 build system 给代码的那种东西：**我编辑的 canonical source、从不编辑的 compiled artifact、中间有一道 gate 在 ship 之前告诉我 *这次改动会变成什么***。

这就是 `forge-core`。

## 三个问题

1. **长期内容和运行时 context 混在一起。** 你的笔记、偏好、学到的规则、生成的 `CLAUDE.md`、实际对话的草稿空间，全堆在一起。没有清楚的 "这是真相" vs "这是衍生产物"。当 `CLAUDE.md` 里某一行看着不对，你追溯不到一个具体来源。

2. **变动进入系统时没有可追溯性。** agent 在会话里改了你的 memory 文件。谁批准的？为什么？能 rollback 吗？多数工具的答案是 "不——现在那就是你的 memory 了"。

3. **你没法判断系统是不是变好了。** 多数 "personal OS" 流程止步于 "感觉更顺"。没有 bench，没有前后对比，没有结构检查。你做了改动——它真的让你想要的 section 改了吗，还是扩了、丢了、搞乱了 ordering？

每一个都可以单独解。现有工具没有一个同时解三个。

## forge-core 怎么工作

三个目录、三个概念：

```
sp/
  section/          # canonical source：一个概念一个 markdown 文件
    about-me.md
    preferences.md
    workspace.md
    skills.md
  config/           # 配方：给 target X，包含这些 section
    personal.md     # → CLAUDE.md
    codex.md        # → AGENTS.md
.forge/
  approved/         # 上次 approved 的 sp/ 快照
  output/           # compiled 产物（CLAUDE.md、AGENTS.md、…）
  changelog.md      # append-only 审计
  manifest.json     # approved hash、时间戳
```

循环：

```bash
# 你改
$ vim sp/section/preferences.md

# 你看会变成什么
$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - 外部事实 ground 在 live source。
 - 不要加 emoji。
+
+- 改公共配置前，先开 PR。

======== output diff ========
--- personal ---
+++ proposed/personal
@@ -19,6 +19,8 @@
 - 不要加 emoji。
 
+- 改公共配置前，先开 PR。
+

# 你 commit（或丢弃）
$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .forge/output/CLAUDE.md
  wrote .forge/output/AGENTS.md
```

核心概念就这一个：**每次 canonical source 的变动，同时以 source diff 和 compiled-output diff 的形式出现，都在 ship 之前**。如果你不喜欢它会怎么变 `CLAUDE.md`，`forge reject` 让你回到上次 approved。

## 为什么 gate 比编译器更重要

编译器部分很直白。Section 是带 frontmatter 的 markdown，Config 是 section 名字的列表，Adapter 把有序 section 渲染成 target 格式。任何人下午写得完。你完全可以说 `rulesync` 在 rules 这个子集上已经做了有意思的编译部分。

**Gate 才是关键。** 没有它，forge-core 就是"又一个 markdown templater"。有了它，forge-core 就变成：阻止你的 agent context 被一次坏 edit 悄悄破坏的东西，能把 compiled output 任何一行追回到具体 approved source 快照的东西。

这和 git 能做但 rsync 不完全能做的原因是一样的。两者都在状态间搬字节。只有一个带着 "这次变动经过 review 并提交了" 的概念和可走回去的完整历史。

## Bench 也不能省——但让我说清楚它做的是什么

任何人看到 personal AI 系统第一个问题是：**它真的有用吗？** 多数答案是拍脑袋。"感觉更好了"、"觉得 agent 更锋利了"。

`forge-core` v0.1 ship 一个结构 bench：

```bash
$ forge bench snapshot before
$ # (改 sp/，approve)
$ forge bench snapshot after
$ forge bench compare before after
compare before -> after

# outputs
  AGENTS.md: 952B -> 1023B (+71B, +2L)
  CLAUDE.md: 1212B -> 1283B (+71B, +2L)

# section size deltas
  skills: 203B -> 274B (+71B)
```

**清楚讲这是什么不是什么。** v0.1 的 bench 衡量**结构** delta——byte 数、行数、section size、新增/删除 section。它**不**衡量 "agent 在新 context 下真的变聪明了吗"。它做不到。那个断言需要真 agent 在固定问题集上跑、带打分 harness，那是 v0.3。

我故意 ship 弱版。我宁愿 ship 一个我能指着说 "它做什么、不做什么" 的小 bench，也不 ship 一个其实只是拍脑袋的假 LLM eval。结构版本至少能抓住一个大家都撞过的 failure：*我做了一次改动，没注意 context size 翻倍了*。

所以这工具叫 `forge-core` 而不是 `forge-eval` 或 `forge-bench-pro`。v0.1 的核心卖点是 gate + compile 契约。bench 在那里是为了给 v0.3 的真 eval 留一个干净的插入点。

## 但我也真跑了 A/B eval

v0.1 还 ship 了一个**真实行为 A/B eval 的结果**。不是模拟。

4 个任务（identity、workspace、grounding、ikigai-direction）× 2 个 CLAUDE.md 版本（dxyOS 迁移前 vs forge-core 编译）= 8 次真实 subagent 生成 + 4 个 blind LLM 判官。位置随机化。

**结果：2-2 打平。** 两个版本行为表现持平。详细方法论、位置偏见的诚实 caveat、原始判决，都在 [`docs/eval-report.md`](eval-report.md)。

是小 N。是 positional-bias-vulnerable。但它**是真的**——真 agent 行为，在真内容上，不是拍脑袋。每一个宣称 "让你的 agent 更聪明" 的 personal AI 工具至少欠这个量级的实验，**而多数没做**。forge-core v0.1 ship 了这套框架 + 一个小而诚实的结果，不是 ship 一个没法 back up 的大 claim。

## `rulesync` 怎么办？`claude-memory-compiler` 呢？`skills-to-agents` 呢？

它们各自解决一块，都解得挺好。`forge-core` 不跟它们竞争——它在一个它们都不占的层上。

| 工具                    | 它占什么                                       | 它不占什么                                   |
|-------------------------|------------------------------------------------|----------------------------------------------|
| rulesync, ai-rules-sync | 8+ runtime 间的格式翻译                        | 没 review gate、没 canonical source 层       |
| claude-memory-compiler  | 自动抓取 + LLM 整理会话 memory                 | 没人类 checkpoint、没多 runtime target       |
| agents-md-generator     | 从代码库生成 AGENTS.md                         | source 是代码，不是长期内容                  |
| skills-to-agents        | 编译 SKILL.md → AGENTS.md                      | 只 skill，没 identity / preferences 等       |

没什么阻止你组合用。未来的 forge-core watcher 可以把 claude-memory-compiler 捕获的内容作为 proposed input（要求 review 才能进 canonical source）。未来的 adapter 可以 emit Cursor `.cursorrules`。这就是一个干净分层的意义。

## v0.1 里有什么、没有什么

**现在 ship 的：** compiler core、Claude Code + AGENTS.md adapter、review gate（init/diff/approve/reject/status/build/doctor）、结构 bench、60 单测、端到端 dxyOS 验证（93.5% 语义 line recall + 真 A/B eval 2-2 打平）。

**还没 ship：**
- 没 watcher / inbox / auto-ingest。你手动编辑 `sp/section/`。（v0.2）
- 没 LLM-based eval。Bench 是结构的。（v0.3）
- 没 Mem0 / Letta / Zep adapter。Canonical source 就是 markdown。（v0.4，症状驱动）
- 没 CI 集成、没托管版、没 Web UI。

这是刻意的。整个论点是 **真正难的问题是 gate + 分层 + bench 契约——不是编译本身**。v0.1 最小版 ship 论点，让我（以及任何觉得这有意思的人）先验证概念，再加表面。

## 我想从你这里得到什么

如果这个方向打中你——如果你感受过 "我的 CLAUDE.md 悄悄坏了" 或 "我不知道上一次 edit 是帮了还是坏了" 的那种痛——试一下，拆台，告诉我模型哪里断。Issue 和 PR 都欢迎。特别希望看到：

- 第二个 target adapter，不在 Claude 生态内（Cursor、Aider、别的）。
- 更好的 diff UX（当前文本 diff 能用但不精致）。
- 真实世界的 bench 场景，结构对比真正有用的地方、vs 结构对比失效的地方。

Repo：*(链接待定——还未 push 到 public GitHub)*.

---

*由 dxy 于 2026-04-24 编写。状态：v0.1.0 alpha。*

*英文版见 [`article-draft.en.md`](article-draft.en.md)。*
