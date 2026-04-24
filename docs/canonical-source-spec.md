# Canonical Source pillar 设计

Canonical Source 是五大 pillar 里最"显然"的一个——它的实现就是 `sp/section/` 下一堆 markdown 文件。但它作为**独立 pillar** 的意义远大于它的代码量，所以单独写一份 doc。

## 把它当数据 asset 来想

Canonical Source 在 forge 里承担的是"**你的 AI context asset**"的载体。这不是一个随便的词选择——它决定了这一层的全部设计。

代码有 git，笔记有 Obsidian / Notion，投资组合有 Excel——都有对应的 **asset 管理层**。asset 管理层的共性是三条：

1. **可理解** —— 人能直接读懂，不是二进制、不是向量、不是黑箱
2. **可解释** —— 每一段能追溯来源、历史、为什么在这里
3. **可控制** —— 所有者说删就删、说改就改、说回滚就回滚

个人 AI context 直到今天还没有一个干净的 asset 管理层。Claude memory、ChatGPT memory、LLM-based memory compiler 都违反这三条中的至少一条——要么锁在平台服务器上（违反可控制），要么 LLM 黑箱整理（违反可理解+可解释），要么是单向自动化写入（违反可控制）。

forge 的 canonical source 层就是要把这个缺失补上。`sp/section/*.md` 是本地的、人类可读的、git-versioned 的、带 frontmatter 可溯源的。三条全达标。

---

## 为什么值得单拎出来

forge 的根本主张是 **canonical source ≠ compiled view**。这一层分离如果塌了，其他四个 pillar 的价值全都连带塌了，asset 也就退化回"耗材"：

- 没有 canonical source → **没有东西可以 review**。governance 审谁？
- 没有 canonical source → **编译没有输入**。compiler 编什么？
- 没有 canonical source → **bench 没有稳定比较对象**。evaluation 对比啥？
- 没有 canonical source → **adapter 也只是格式转换**。没有分层就没有价值。

所以 Canonical Source 虽然代码最少，但定位上是**承重墙**。砍掉这一层，forge 的故事就不成立了。

---

## 契约

| 约束 | 规则 |
|---|---|
| 存储位置 | `<workspace>/sp/section/` 下每个 `.md` 文件是一个 section |
| 格式 | YAML frontmatter（可选）+ markdown body |
| frontmatter 字段 | `name` / `type` / `kind` / `updated_at` / `source` / `upstream` / `generated_by` + 任意额外字段进 `meta` |
| 存储介质 | 纯文件系统。不是数据库、不是 vector store、不是 API |
| 编辑入口 | 人手改，或脚本改。forge-core 本身**不**自动改 canonical source |
| 修改 | 必须走 `forge diff / approve / reject` 走审核，才会重编译 output |
| 删除 / 重命名 | 走 git。forge-core 不提供"重命名 section"命令，因为 section 名就是文件名 |

### 约定优于配置

- 下划线开头（`_preface.md`）表示 wrapper section——不是主体内容，给 adapter 提示"原样输出 body，不加 `## <name>` 标题"
- `kind: derived` 的 section：`watcher` 会自动跳过（不会拉进 inbox triage），因为它是别的流程生成的
- `source` / `upstream` 字段：provenance 溯源链。在 compiled output 的 header 里会 emit 出来，让 agent 或 review 者能知道每段内容最早来自哪里

---

## 为什么是 plain markdown 而不是数据库

几个刻意的决定：

**1. 你可以删掉 forge-core，保留内容。**（这是 asset 的基本特性——asset 不能被工具绑架）

`sp/section/*.md` 是正常的 markdown 文件。你可以：
- 用任何编辑器改（VS Code / Obsidian / vim / notepad）
- 用 `grep` 搜
- 用 `git` 管版本
- 发到别人电脑上继续用
- 打印出来

forge-core 只是"管流程"的工具，不是"持有内容"的服务。如果 forge-core 明天不维护了，你的内容不会因此受损。**Claude memory / ChatGPT memory 做不到这点**——它们的数据在平台服务器里，平台消失你就没了。

**2. 人类可读 = agent 可读。**

markdown 是 LLM 最原生的格式。把 canonical source 存成 markdown = 把内容放在 agent 能直接消化的形态。不需要 schema transformation 层。

**3. 和 git 天然对齐。**

section 改动就是 git commit。forge 的 governance 层可以完全建立在 git 之上（watcher 扫 git log、provenance 带 commit hash、rollback 用 git）。不需要重新发明一套版本系统。

**4. 不对长期内容做"结构化入侵"。**

Section 的 body 是**自由 markdown**。forge 不要求你写 schema、不要求你分章节、不要求你填字段。它只在 frontmatter 层做轻量元数据。

用户想怎么写就怎么写——forge 的价值是在"这段内容怎么进系统、怎么变成 agent 读的东西"的流程上，不是"这段内容应该长什么样"的格式上。

---

## 不做什么

以下是 forge v0.1 **刻意不做**的事，即使看起来自然：

### 不做自动结构化（这是 asset 差异化的前提）

不会"自动把用户的日记提炼成 preference"。那是内容层的事，应该交给用户自己（或用户自己写的脚本 / agent）。forge 只管"你产出一段 section 之后怎么进系统"。

这不是懒。**自动结构化会系统性地抹去差异化**——LLM 整理出来的结构、语言、语气都会收敛到模型的"平均审美"。让它代你管你的 about-me、preference、workspace，你的 asset 会逐步变得和所有其他让 LLM 代管的人一样。差异化只能来自**你自己的判断、你自己的语言、你自己决定留什么丢什么**。canonical source 层不自动帮你做这些决定——这是它作为"你的" asset 的前提。

### 不做 embedding / vector 搜索

canonical source 是"长期、稳定、有限量"的内容。不是"海量、需要 RAG 检索"的知识库。如果你有 10000 条微事实要做 retrieval，forge 是错工具——用 vector store + RAG sidecar，把 forge 的 section 当你的"索引层"。

### 不做跨 section 的引用解析

section 里可以写 `见 preference.md 第 3 段`，但 forge 不会自动 resolve 这个引用。引用解析是运行时（agent 读的时候）的事，不是编译时的事。

### 不做 section schema 验证

frontmatter 里写什么字段由你决定。forge 只识别自己知道的几个（`name` / `type` / `kind` / `upstream` / `generated_by` / `source` / `updated_at`），其他字段进 `meta`。想要强 schema 的人可以在自己的 CI 里加校验——不进 core。

---

## 关于 memory sidecar（v0.4 的议题）

未来可能加 `Mem0` / `Letta` / `Zep` 等外部 memory backend 的接入——**但它们是 sidecar，不是 canonical source**。

意思是：

- 你的长期、稳定、人管的 content 仍然在 `sp/section/`
- 外部 memory 服务放那些**不适合人管、不需要 review、随时可以丢**的东西（会话缓存、retrieval 加速、LRU 淘汰的细节 fact）
- 两层不混。外部 memory 服务**不能**替代 canonical source，也**不能**被编译进 CLAUDE.md

这条边界守住，才有意义。一旦你允许 "外部 memory 自动写进 section / 自动生成 CLAUDE.md"，你就失去了 review gate，五大 pillar 就塌了。

---

## 检查清单：你的 Canonical Source 健康吗

按"asset 的三个属性" 自检：

**可理解**
- [ ] 随便打开一份 section，你自己能直接读懂
- [ ] 没有 "AI 整理风"——没有大段过度概括、没有工整到像 LLM 输出的列表结构
- [ ] `sp/section/` 下的文件数量在**合理范围**（经验值：个人使用 5-20 个，团队 20-50 个）。超过 50 个往往说明你在把"知识库"往里塞，应该拆出去用别的工具

**可解释**
- [ ] 每个 section 都有清晰的**单一主题**（name 能用一个词概括）
- [ ] 带 `kind: derived` 的 section 都能说清楚它从哪里 derive（`upstream` 字段有值）
- [ ] 你能对每一段说出"这段为什么在这里、上次改它是为什么"

**可控制**
- [ ] `sp/section/*.md` 能在 git 里被正常 diff / blame（如果不能，说明有什么脚本在不 commit 地改它，违反 review gate）
- [ ] 不存在"长期没人改但还被 config 引用的"死 section（跑 `forge doctor` 看 orphan warning）
- [ ] 你敢把整个 `sp/` 目录删一半，因为你知道哪些是真需要的、哪些是累赘

---

## v0.2 想加的

| 能力 | 理由 |
|---|---|
| `section.freeze_at` 字段 | 标记"这段内容在某时间点后不应该再被自动改"——防止自动化工具越权 |
| Section 级别的权限提示（frontmatter 里写 `sensitive: true`） | compile 时 compiler 可以决定这段要不要进某些 target（比如分享出去的 AGENTS.md 里不要包含 PII section） |
| Upstream 链的闭环检查 | 如果 `preference.md` 的 `upstream: [raw/journal.md]`，forge doctor 可以验证 `raw/journal.md` 真的存在 |

这些都属于"更硬的 schema 约束"，v0.1 不做，等有真实使用数据再决定形态。
