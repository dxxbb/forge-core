# 为什么我又写了一个和 `rulesync` 类似的小工具

*草稿——还没发。*

---

## 一个没人在做的小缝隙

2026 年和 agent 打交道的工具已经不少了，但它们基本只在三类事上做功：

**第一类是把规则同步过去**。`rulesync` 这类（GitHub 有 1k 星，真的在被人用）——你写一份规则，它帮你投给 Cursor、Claude Code、Copilot、Gemini 这些 20 多个工具。**但它改了就直接推**，没有一道让你看一眼再决定的关口。

**第二类是把会话抓回来**。`claude-memory-compiler` 这类——它 hook 你和 Claude 的对话，让 LLM 自己整理出 memory 文章。**也是没人审核**的：LLM 直接往你的 memory 文件里写。

**第三类是编译 prompt 本身**。DSPy、BAML 这种。它们管的是"agent 怎么思考"，不是"agent 读哪份上下文"。完全不同的一层。

这三类之间，缺了一个很小但很具体的东西：**在你改长期内容、和 agent 真的读到那份编译产物之间，放一道你能看见的关口**。

我不是想做又一个会自动改我 memory 的工具。也不是想做又一个把我输入的任何东西推去 8 个 runtime 的 sync 工具。我想要的就是 build system 给源代码的那一套：**我改我的源文件，产物永远从源文件编译出来，中间有一道 diff + approve + rollback 让我看清楚每次变化**。

这就是 `forge-core`。

## 这件事今天的三个具体问题

**第一，长期内容和运行时上下文混在一起。** 你的笔记、偏好、学到的规则、生成的 `CLAUDE.md`、对话的草稿空间，都堆在一起。没有清晰的"这是我积累的真相"和"这是 agent 每次启动读的那份东西"的分界。`CLAUDE.md` 里某一行看着不对，你追不回这行是从哪来的。

**第二，改动进入系统时没审计。** agent 在会话里改了你的 memory 文件，谁改的、什么时候改的、为什么改、能不能回滚？多数工具答不出来——"改完了就是你的 memory 了"。

**第三，你没法判断这套东西有没有变好。** 大部分 personal OS 的博文止步于"感觉更顺了"。没 bench、没前后对比、没结构检查。你做了一次改动，真的只让你想改的那一段变了吗？还是顺带把其他什么东西一起撑大了？

三件事里每一件单独都有工具能解。但没有一个工具三件事一起解。

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

## 关口比编译本身更重要

编译的部分其实很笨。Section 是带 frontmatter 的 markdown，Config 是一列 section 名字，adapter 负责把它们按顺序拼成目标格式。一个人一个下午写得完。你甚至可以说，`rulesync` 在"规则"这个子集上已经把这步做了。

**关口才是这个工具的灵魂**。没有它，forge-core 就只是"又一个 markdown 模板引擎"。有了它，它就成了两件事：一道阻止 agent 上下文被某次坏改动悄悄破坏的屏障；一个能把产物任何一行追回到某次具体 approve 点的机制。

打个比方：git 能做而 rsync 做不到的事情是什么？都搬字节，区别是 git 多了"这次改动是经过审查提交的"这个概念，和一条可以走回去的完整历史。forge-core 给 agent 配置文件这层补的，就是这种概念和历史。

## Bench 也不能省——但得先说清楚它是什么不是什么

任何看到 personal AI 工具的人都会先问一个问题：**它真的有用吗？** 多数答案是拍脑袋："感觉更好了"、"agent 变锋利了"。

`forge-core` v0.1 自带一个结构 bench：

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

**讲清楚它是什么不是什么**：v0.1 的 bench 只衡量**结构变化**——字节数、行数、每段 section 大小、新增 / 删除的 section。它**不**衡量"agent 用了新 context 之后是不是变聪明了"。它做不到。那个断言需要拿真 agent 在固定问题集上跑 + 有打分系统，那是 v0.3 的事。

我故意先 ship 弱版。我宁愿给你一个能讲清楚"它做什么、不做什么"的小 bench，也不想 ship 一个其实就是拍脑袋的"LLM eval"。就算只做结构对比，至少能抓住一个大家都撞过的坑：*改了一次，没注意上下文翻倍了*。

所以这个工具叫 `forge-core`，不叫 `forge-eval` 或 `forge-bench-pro`。v0.1 的主卖点是"关口 + 编译契约"。bench 放在这里，是给 v0.3 的真 eval 留一个干净的接口。

## 但我也真跑了一轮 A/B 行为评估

v0.1 除了结构 bench 之外，还跑了一次**真实的行为 A/B 评估**。不是模拟。

4 个任务（identity、workspace、grounding、ikigai-direction）× 2 个 CLAUDE.md 版本（dxyOS 迁移前 vs forge-core 编译）= 8 次真实的子 agent 回答 + 4 个盲评的 LLM 判官。位置随机化。

**结果：2 比 2 打平。** 两个版本行为表现基本一致。完整方法、位置偏见这个坑的诚实讨论、原始判决，都在 [`docs/eval-report.md`](eval-report.md) 里。

样本量小。有位置偏见的风险。但它**是真的**——真 agent 行为，在真内容上，不是拍脑袋。每一个号称"让你的 agent 更聪明"的个人 AI 工具，都至少欠一次这个量级的实验，**而多数没跑**。forge-core v0.1 先把这套框架加一个小而诚实的结果放在桌上，不吹它 back 不起的大话。

## `rulesync` 怎么办？`claude-memory-compiler` 呢？`skills-to-agents` 呢？

它们各自解决一块，都解得挺好。`forge-core` 不跟它们竞争——它在一个它们都不占的层上。

| 工具                    | 它占什么                                       | 它不占什么                                   |
|-------------------------|------------------------------------------------|----------------------------------------------|
| rulesync, ai-rules-sync | 8+ runtime 间的格式翻译                        | 没 review gate、没 canonical source 层       |
| claude-memory-compiler  | 自动抓取 + LLM 整理会话 memory                 | 没人类 checkpoint、没多 runtime target       |
| agents-md-generator     | 从代码库生成 AGENTS.md                         | source 是代码，不是长期内容                  |
| skills-to-agents        | 编译 SKILL.md → AGENTS.md                      | 只 skill，没 identity / preferences 等       |

没什么阻止你组合用。未来的 forge-core watcher 可以把 claude-memory-compiler 捕获的内容作为 proposed input（要求 review 才能进 canonical source）。未来的 adapter 可以 emit Cursor `.cursorrules`。这就是一个干净分层的意义。

## v0.1 有什么，没什么

**现在 ship 的**：编译器核心、Claude Code + AGENTS.md 两个适配器、审核关口 CLI（init / diff / approve / reject / status / build / doctor）、结构 bench、65 个单测、对 dxyOS 端到端的验证（91.5% 逐行保留率 + 真 A/B 2-2 打平）。

**还没做的**：
- 没有 watcher / inbox / 自动抓取。`sp/section/` 都是你自己改。（v0.2）
- 没有 LLM 打分的 eval。现在 bench 是结构的。（v0.3）
- 没有 Mem0 / Letta / Zep 的适配器。源头就是 markdown 文件。（v0.4，按需接）
- 没有 CI 集成、没有托管版、没有 Web UI。

这些都是故意不做的。整件事的论点是：**真正难的是关口 + 分层 + bench 契约，不是编译本身**。v0.1 先把论点以最小版本 ship 出来，让我（以及任何觉得这个方向有意思的人）先验证概念，再往上加。

## 想请你做什么

如果这个方向打中你——如果你有过"我的 `CLAUDE.md` 被悄悄搞坏了"或者"我上一次改到底帮了还是坏了都分不清"这种感受——试一下、拆台、告诉我我的模型哪里塌了。Issue 和 PR 都欢迎。我特别希望看到：

- 第二个非 Claude 生态的适配器（Cursor、Aider 之类）。
- 更顺手的 diff 体验（当前的文本 diff 能用但不精致）。
- 真实场景下"结构对比够用"和"结构对比不够用"各是什么时候。

Repo：*（还没 push 到 GitHub）*。

---

*由 dxy 于 2026-04-24 编写。状态：v0.1.0 alpha。*

*英文版见 [`article-draft.en.md`](article-draft.en.md)。*
