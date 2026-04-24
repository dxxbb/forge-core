# Changelog

记录 `forge-core` 的所有显著变动。

## [0.1.0] — 2026-04-24

首次发布。带 schema 检查和 provenance 的 review-gated context compiler。

### 新增
- **Compiler core** — `Section` + `Config` + `Renderer`。YAML frontmatter + markdown body。确定性编译。
- **Section provenance** — frontmatter 字段：`kind`、`upstream`、`generated_by`；`last_rebuild_at` 作为 `updated_at` 的 fallback（兼容 dxyOS 风格 schema）。
- **Config schema** — `required_sections` 由 `forge doctor` 强制。
- **Output frontmatter** — 可选 `output_frontmatter: {...}` 字段，在 compiled 产出顶部 emit 用户指定的 YAML；`generated_by: forge-core@<ver>` 和 `last_rebuild_at` 自动注入（不覆盖用户已提供的字段）。
- **Demote section headings** — 可选 `demote_section_headings: true`，给自带 leading H1/H2 的 section 提供干净层级（strip 首 heading + 其余 demote 一级）。
- **Compiled output provenance** — 每个 CLAUDE.md / AGENTS.md 都带机读 header：config 名、target、SHA256 digest (12 hex)、编译时间、per-section type / kind / upstream / generated_by / bytes。
- **Target adapters** — `claude-code`（→ CLAUDE.md）和 `agents-md`（→ AGENTS.md）。带 `register_adapter()` 用于自定义 runtime。
- **Review gate CLI** — `forge init / status / doctor / build / diff / approve / reject`。
- **结构 bench** — `forge bench snapshot / list / compare`。per-file + per-section byte / line delta、新增 / 删除 section。
- **Schema 健康检查** — `forge doctor` 验证 section 引用、required-section 覆盖、adapter 注册、orphan section、kind=derived 但 upstream 为空。
- **Eval 框架 stub** — `forge.eval` 模块：`EvalTask`、`Runner` ABC、`SimulationRunner`、`EvalReport`、`JudgeVerdict`。6 个默认行为任务。v0.1 是 interface + 参考实现；LLM runner 自己挂。
- **Examples**
  - `examples/basic/` — 最小 4-section 工作区 + 2 个 config。
  - `examples/dxyos-validation/` — 对真实 personal-OS vault 的完整硬核验证：语义等价性（vs vault 自己 SP-compiled CLAUDE.md 的 line recall）、completeness、doctor、gate + bench 循环。还会自动产出 `diff-vs-dxyos.txt` 供人类对比。
- **迁移指南** — `docs/migration-from-personal-os.md`。
- **Eval 报告** — `docs/eval-report.md`，真实 4 任务 × 2 版本 subagent A/B + 4 blind judge，位置随机化，2-2 打平。
- **单测** — 60 个 pytest（section parser、loader、两个 adapter、所有 gate action、bench、provenance、doctor、heading demotion、adapter 扩展、eval 接口）。

### 已验证
- 结构 line recall vs dxyOS 自己 SP-compiled CLAUDE.md：**93.5%**（6.5% gap 是 dxyOS wrapper 前置文本，不是内容）。
- 编译确定性：同输入两次跑输出 bytes 完全相同。
- Gate 循环（diff → approve → rollback）在真实 vault 内容上通过。
- 行为 A/B eval：4 任务 × 2 版本 subagent + 4 blind judge，位置随机化，2-2 打平，**无行为回退**。

### 已知限制（诚实版）
- 没有 watcher / inbox / auto-ingest。section 手动编辑或脚本编辑。（v0.2）
- 不做 `@file` 包含解析——Claude Code 的 `@README.md` 透传在 runtime 层。要把 @-imported 内容搬进 section，或留一个瘦根 CLAUDE.md 用 `@` import 一个 forge 生成的文件。
- 没有外部 memory provider 的 adapter（Mem0 / Letta / Zep）。（v0.4，症状驱动）
- Bench 是**结构的**，不是 LLM-based。v0.3 加真实 LLM-graded eval harness。
- 没有跨工具 rules sync（超出 claude-code + agents-md）。加一个 adapter 就能扩。

---

*英文版见 [`CHANGELOG.en.md`](CHANGELOG.en.md)。*
