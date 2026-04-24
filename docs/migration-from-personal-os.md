# 把一个 personal-OS vault 迁移到 forge-core

如果你已经有一个 "personal OS" 风格的工作区——markdown 文件按 section / topic 组织、手维护或脚本生成的 `CLAUDE.md` / `AGENTS.md`——本指南告诉你怎么迁到 forge-core、**得到什么**、以及（诚实地说）**什么对不上**。

示例基础：[`dxy_OS`](https://github.com/dxxbb/dxy_OS)。[`examples/dxyos-validation/validate.py`](../examples/dxyos-validation/validate.py) 脚本自动跑端到端迁移。

---

## 1. 目标目录结构

forge-core 预期：

```
<你的根>/
    sp/
        section/
            <一个概念>.md      # 每个都带 YAML frontmatter
            <另一个概念>.md
            ...
        config/
            <config-名>.md     # 一个 config 对应一个编译 target
```

`forge init` 之后：

```
    .forge/
        approved/sp/…          # 上一次 approved 的 source 快照
        output/CLAUDE.md       # compiled 产物
        output/AGENTS.md
        changelog.md
        manifest.json
        bench/<snapshot-名>/…
```

---

## 2. 映射一个典型 personal-OS vault

多数 personal-OS setup 大致有：

- 一个 `me.md` / `about-me.md` 身份文件
- 一组 "preference" / "working style" 笔记
- 工作区 / 项目概览
- 知识库索引
- 技能目录
- 某种 "CLAUDE.md" 或 "AGENTS.md"（粘贴到 agent setup）

迁移：

**对每个长期内容文件：** 抽出核心内容（丢掉宿主特有的杂项）到 `sp/section/<name>.md`，加一段 YAML frontmatter。最小 frontmatter：

```yaml
---
name: about-me
type: identity
---
```

支持的可选字段（都会保留在 provenance 里）：

```yaml
name: about-me
type: identity
kind: canonical          # 或：derived
updated_at: 2026-04-24
source: 02 user/me/me.md
upstream:                # 这个 section 是从哪里 derive 的
  - 02 user/me/me.md
  - 02 user/life/seeking/self understand/PAI Telos.md
generated_by: feishu-ingest-pipeline
```

**对每个编译 target：** 写一个 config：

```yaml
---
name: master
target: claude-code                  # 或：agents-md
sections:
  - _preface                         # 前言也是一个 section（见下）
  - about-me
  - preferences
  - workspace
  - knowledge-base
  - skills
required_sections:                   # schema 约束，`forge doctor` 会强制
  - about-me
  - preferences
demote_section_headings: true        # section body 自带 H1/H2 标题时开启
output_frontmatter:                  # 编译产物顶部要 emit 的 YAML
  kind: derived
  target_tool: claude-code
---
```

> **重要：Config 不接 `preamble` / `postamble` / `body` 字段。** Config 在 forge-core 里是 MVC 的 Controller，只负责"怎么编"，不装内容。v0.1 版本里这三个字段会直接报错，告诉你搬到 section 去。

如果你要在产物开头加一段介绍文字，写一个 wrapper section：

```yaml
---
name: _preface
type: wrapper
---

这是给 Claude Code 的个人 context。由 sp/section/ 自动编译。
```

放在 `sp/section/_preface.md`，然后在 config 的 `sections:` 列表里排在第一个。`type: wrapper` 告诉 adapter：body 原样输出，不加 `## _Preface` 这种标题、不参与 heading 降级。

---

## 3. 具体在 dxy_OS 上验证过的数字

dxy_OS 迁移结果（可复现：`python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS`）：

| 检查                                             | 结果                              |
|-------------------------------------------------|-----------------------------------|
| Section 加载（文件名带空格 + 1 个 wrapper）     | 6 / 6 ✅                          |
| Config 带 `required_sections`                   | 2 / 2 ✅                          |
| `forge doctor`                                   | 0 errors ✅                       |
| 编译确定性（两次跑同 bytes）                    | ✅                                |
| Line recall vs dxyOS 自己 SP 编译的 CLAUDE.md   | **91.5%**                         |
| Per-section body 完整性                          | 6 / 6 ✅                          |
| Gate + bench 循环（diff/approve/snapshot/compare）| ✅                               |
| 行为 A/B eval（见 eval-report）                  | 2–2 split，无回退 ✅              |

**那 8.5% 没对上的是什么？**

是 dxyOS 原来那段"本文由 `01 assist/SP/config/master.md` 自动生成"的说明文字，它以前是硬编码在 dxyOS compile 模板里的 wrapper。forge-core 把它搬成了一个 `_preface` wrapper section——内容基本相同但不是逐字一致。所有**主体内容**（identity / preferences / knowledge-base / skills）全部保留。如果你需要 byte 级别对齐原来的 wrapper，把 `_preface` section 的 body 原样拷过来就行。

---

## 4. forge-core vs 手搓脚本

| 手搓                                        | forge-core                              |
|---------------------------------------------|-----------------------------------------|
| 改 → 重跑你自己的 compile 脚本              | 改 → `forge diff` **同时**展示 source 和每个 target 的 compiled diff |
| "希望没出问题"                               | 每次改动都走 `forge approve`；`forge reject` 便宜回滚 |
| 你自己写的 changelog                        | `.forge/changelog.md` append-only，带 hash |
| 你自己写的 "还是那个吗" 检查                | `forge bench snapshot` + `compare` per-section bytes |
| 没 schema                                   | `required_sections` + `forge doctor` 健康检查 |
| "这行从哪来的？"                             | 每个 compiled output 的 provenance header，per-section `upstream` chain |
| 换 runtime 难                               | 加新 target = 写一个 `TargetAdapter` 子类 |

---

## 5. forge-core 明确**不**解决的（诚实地）

这些是 v0.1 的真实限制，不是 "roadmap 假话"：

1. **不做 `@file` 包含解析。** Claude Code 的 `@README.md` 透传是 runtime 层的事；forge-core 在编译时内联 section。如果你现在的 CLAUDE.md 依赖 `@` imports，你有两条路：
    - 把 @-imported 的内容搬进 section（成为 canonical），或
    - 留一个瘦根 CLAUDE.md 用 `@` imports，用 forge-core 生成被 import 的文件。
2. **没有 ingest / watcher。** section 是手动编辑的（或你自己的脚本编辑）。forge-core 不监听你的 vault。那是 v0.2。
3. **不处理非 forge schema 的内容级迁移。** 如果你的 section 有奇特 YAML 字段，它们保留在 `section.meta` 里，但 forge-core 不做任何语义处理。需要就自己写 loader。
4. **Section 是文件，不是数据库记录。** 如果你有 500 个微事实要做 retrieval，forge-core 是错工具。用 vector store + retrieval sidecar；forge-core 在那一层之上，不在那一层里。
5. **Bench 是结构性的。** v0.1 告诉你 "这次编译 preference section 多了 45 bytes"。**不**告诉你 "你的 agent 变聪明了"。LLM-based eval 是 v0.3。
6. **一次一个 workspace。** 不做多 vault 联合、不做团队共享契约。v0.4+。

---

## 6. 迁移清单

- [ ] 识别你 3-10 个核心长期内容文件。别冲动迁 50 个。
- [ ] 创建 `<根>/sp/section/`，把这些文件搬过去，加 YAML frontmatter。
- [ ] 创建 `<根>/sp/config/`，至少一个 config（一般叫 `master.md`，target 是 `claude-code`）。
- [ ] 跑 `forge init`。读 `.forge/output/CLAUDE.md`。看起来对吗？
- [ ] 跑 `forge doctor`。修所有 error。
- [ ] 基线：`forge bench snapshot baseline`。
- [ ] 做一次真实 edit。`forge diff`。`forge approve`。`forge bench snapshot next`。`forge bench compare baseline next`。
- [ ] 如果这 4 步都顺手，把剩下的内容也迁过来。不顺手：alpha 版，开 issue。

---

## 7. 保留原 vault

forge-core 是 additive 的。迁移不要求你删掉原 personal-OS vault、删掉现有脚本、或承诺长期用 forge-core。[`examples/dxyos-validation/validate.py`](../examples/dxyos-validation/validate.py) 的做法——把 section 拉到一个 side 目录、在那里跑 forge-core——是在不动主线的前提下评估。

在 dxy_OS 的例子里，真实 vault 留在 `~/dxy_OS`、保留现有 `01 assist/SP/output/` pipeline；forge-core 在 `_staging/` 或 `forge-core-migration` 分支上跑，用来验证概念。**是否合并到主线**是独立决策。

---

*英文版见 [`migration-from-personal-os.en.md`](migration-from-personal-os.en.md)。*
