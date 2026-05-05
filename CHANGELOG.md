# Changelog

记录 `forge-core` 的所有显著变动。

## 0.3.1 (dogfood) — 2026-05-05

主 agent 在 ~/personalOS 真实跑了一遍 v0.3.0,暴露 13 条问题(8 bug + 5 cosmetic/spec)。本版修齐 12 条(P6 仅文档化无代码变更)。

**核心 UX 修复**:proposal.md body 自身就是 review-ready 的 §0.5 视图 — 用户在 Obsidian 里打开 `system/pr/<id>/proposal.md` 直接看到渲染结果,无需 `forge pr render | cat` 之类。

### Fixed

- **P1 · proposal.md body 现在自带 §0.5 视图 (BLOCKING UX)**: `forge proposal new` 在 body 里写 `<!-- BEGIN AUTO-RENDERED -->` ... `<!-- END AUTO-RENDERED -->` 标记块。`forge pr render` 默认行为变为**写入** body 的标记块之间(in-place,保留 frontmatter 和标记外的用户手写内容);加 `--stdout` 才输出到 stdout(原 v0.3.0 行为)。`forge proposal validate` schema 完整时**自动调 render**,让 body 与 schema 同步;加 `--no-render` 跳过。
- **P2 · stub `disposition:` 字段命名修正,enum 占位放对位置**: v0.3.0 stub 把 `<APPLY|COVERED|...>` 占位放在 `disposition_note:`(非必填字段),agent 容易误改这个 → schema validate 报 missing disposition。v0.3.1 把 enum 占位放在正确的 `disposition:` 字段,占位字符串(`<...|...>`)被 validate / schema 识别为"仍是占位,等同未填",不会乱解析。`disposition_note:` 留空。
- **P3 · stub propagation 形状对齐 validator**: v0.3.0 stub 用 `label: 监控源` / `terminal: true`,但 APPLY validator 要求 `layer:` + `modification:`,agent 不修就提交会 fail。v0.3.1 stub 默认输出符合 validator 形状的 placeholder(含 `layer: 'Layer 0 · monitor source'` + `modification: '<TODO: 改动内容>'`)。
- **P4 · ARCHIVE 不再强制要 propagation**: SKILL.md §2 disposition reference 写明 ARCHIVE 是 "Capture-only audit trail, no propagation",但 v0.3.0 validator 仍要求 ARCHIVE 至少一个 propagation branch — 文档与实现不同步。改 validator:ARCHIVE 的 `_REQUIRED_BY_DISPO` 设为空集,允许空 propagation。如果作者**显式**给了 propagation,structural sanity 检查仍会跑(path/label 必有其一,non-terminal APPLY 节点必有 modification)。
- **P5 / P13 · skill SKILL.md 同步到 user 路径**: sub-agent 改完 `forge/assets/skills/forge/SKILL.md`(forge-core repo),release 完工时显式跑 `forge self-install`,用 v0.3.1 内容覆盖 `~/.claude/skills/forge/SKILL.md`(managed marker 校验)。**注意**: 当前 Claude Code session 不会 reload skill — 主 agent 需要 spawn 新 sub-agent / 开新 session 才能用上新 skill。
- **P7 · shared_with 行尾不再重复列举所有兄弟**: v0.3.0 给 sub 3.2/3.3/3.4 的 b 节点都追加 "(b 与 sub 3.1, sub 3.2, sub 3.3, sub 3.4 共享触发)",4 次重复读着累。v0.3.1 改为:first owner (id 自然序最小,如 3.1) 显示 "(共享触发的子链路, 见 sub 3.2 / 3.3 / 3.4)",列出**其他**兄弟。
- **P8 · 共享传播,后续兄弟只显示一行 abbreviation**: 3.2/3.3/3.4 渲染时,b 节点直接是叶子 "(同 sub 3.1 共享传播)",**不再**完整重复 b → c 子链。canonical owner (3.1) 完整展开。
- **P9 · 处理结果标题始终带 ENUM_NAME + disposition_note**: v0.3.0 标题模板 `[icon] [note 或 ENUM_NAME]` 二选一 — disposition_note 非空时 ENUM_NAME 消失,reviewer 不看 frontmatter 看不出 disposition 是哪个枚举值。v0.3.1 改为 `[icon] [ENUM_NAME] · [disposition_note]`(note 非空时追加,note == ENUM_NAME 时不重复)。`rule:`(APPLY 用)继续以 `· 提炼为 §10` 形式追加。
- **P10 · 提取信息多行内容渲染成 ├─ / └─ 树形**: 多行 `extracted` 不再平铺缩进,自动按行解析:最后一行 `└─`,其余 `├─`。第一行(label 同行)不加前缀。

### Documented (P6)

- **MIXED 父项的 capture 整体归档不计入 disposition 分布**: v0.3.0 的 dogfood 在总分布显示 `📦 × 7` (含 ITEM 2 + 6 dxy_OS legacy sub-items),但 ITEM 3 的 capture 整体也归档了,没单独计数 — 这是**故意**的,v0.3.1 在 SKILL.md 显式写明:"counting rule for MIXED:disposition distribution counts 仅 sub-items, 不算 MIXED 父项"。父项的 archive trail 在 `disposition_note` 文字里说,不作单独 ARCHIVE 行。新增 test 锁定该不变量。

### Changed

- **`forge` skill doc (`forge/assets/skills/forge/SKILL.md`) v0.3.0 → v0.3.1**: "Process Inbox To Proposal" 流程 step 1/3/4 改写以反映新 stub 形状、validate 自动 render、`pr render` 默认 inline 行为。Disposition reference 表 ARCHIVE 行改为 "Propagation is **optional**"。新增 "Counting rule for MIXED" 段。

### Internal

- 新增 `tests/test_v031_dogfood.py`(15 tests),按 P1 / P2 / P3 / P4 / P6 / P7 / P8 / P9 / P10 / P11 一一锁定回归。**关键 e2e**: `test_p11_pure_stub_fill_validates_clean` 模拟"纯净 agent 第一次跑 `forge proposal new` → 用 sed 替换 stub 占位 → `forge proposal validate` 一遍过",作为下次回归的最强保护。
- `test_proposal_cli.py::test_render_cli_outputs_view` 拆分为 `test_render_cli_writes_inline_by_default` + `test_render_cli_stdout_flag`,分别锁住默认 inline 行为和 `--stdout` 行为。
- 全套 `pytest`: **281 passed / 3 skipped** (265 baseline + 1 拆分测试 + 15 dogfood tests)。

### Compat

- v0.3.0 已生成的 proposal.md(body 没有 BEGIN/END 标记)首次跑 `forge pr render` 时,新版本会**追加** BEGIN/END 块到 body 末尾,后续 render 走 in-place 替换。Frontmatter 不动。
- `forge pr render --stdout` 行为与 v0.3.0 默认行为完全相同(向后兼容旧脚本/automation)。
- 旧手写 markdown proposal 不受影响:`forge pr render` 仍报 schema-opt-out 并 exit 2,`forge proposal validate` 仍报"schema not opted in",`forge pr done` / `forge approve` 行为不变。

## 0.3.0 (proposal-render) — 2026-05-05

把 review-gated PR 的"§0.5 监控 item 视图"机制化:agent 不再手写 markdown,改为填一份 schema-aware 的 YAML frontmatter,再用 `forge pr render` 渲染出与手写版形态等价的 §0.5 输出。完全 opt-in,旧的 hand-written proposal 仍兼容。

### Added

- **新模块 `forge.proposal`**: 4 子模块 — `schema` (dataclass + YAML I/O)、`validate` (per-disposition 完整性检查)、`renderer` (确定性模板渲染,box-drawing + ASCII fallback)、`scaffold` (`forge proposal new` 骨架生成)。
- **`forge proposal new --root <root> [--inbox <id-prefix>]`**: 从 pending inbox 文件 + capture frontmatter 生成 `system/pr/<id>/proposal.md` stub,自动预填 inbox_sources / capture_sources / items[] 骨架(每条 inbox 一个 item, monitor_info / extracted 自动填,disposition 留空待 agent 决定)。
- **`forge proposal validate <pr-id> --root <root>`**: 检查 schema 完整性 — 必填字段、disposition 枚举、APPLY 必有 propagation tree(非叶节点必有 modification)、DECIDE 必有 options[]、COVERED 必有 covered_by、NA 必有 reason、MIXED 必有 sub_items[]、shared_with 引用真实存在的兄弟 id。`forge doctor` 风格输出,违规时 exit code 1。
- **`forge pr render <pr-id> --root <root> [--plain]`**: 把 proposal frontmatter 渲染成 §0.5 监控 item 视图 — per-item / per-sub-item disposition + propagation 树 + 合并改动汇总 + approve 流水线 + 一句话总结。`--plain` 切到 ASCII。
- **`forge doctor` 新增 schema 扫描**: 跑完原有检查后,扫 `system/pr/*/proposal.md`,对每个 PR 报告 schema=ok / N issue(s) / opt-out (legacy hand-written)。Info-only,不阻挡 doctor。
- **Disposition 枚举**: `APPLY ✅` `COVERED ⏭` `ARCHIVE 📦` `DECIDE ❓` `NA ➖` `MIXED 🔀`,parser 接受 `ARCHIVE-ONLY` / `N/A` 等友好别名。

### Changed

- **`forge` skill doc (`forge/assets/skills/forge/SKILL.md`) v0.2.2 → v0.3.0**: "Process Inbox To Proposal" 流程改写为 5 步:`forge proposal new` 生成 stub → 填字段 → `forge proposal validate` → `forge pr render` 给用户看 → `forge inbox done`。不再让 agent 手写 markdown proposal。保留 "Fallback: hand-written markdown proposal" 段说明 opt-out 路径。
- **proposal frontmatter schema 扩展**: 在原有 `kind / type / status / created_at / inbox_sources / capture_sources` 之上新增 `revised_at / items[] / summary{}`。Items 嵌套 sub_items[](MIXED)、options[](DECIDE)、propagation[]→PropagationBranch→PropagationNode→children[]。

### Compat

- 旧的手写 markdown proposal 完全兼容 — 没有 `items:` 块的 proposal 走 `forge pr done` / `forge approve` 与 v0.2.x 一样。`forge pr render` 拒绝渲染 schema-opt-out proposal 并给 hint(exit code 2),不会破坏其他流程。
- `forge doctor` 对 schema-opt-out proposal 报 `schema=opt-out (legacy hand-written)` info-only,不视为错误。

### Internal

- 48 条新增测试 (`tests/test_proposal_*.py` × 5 + `tests/test_doctor_proposal.py`):schema round-trip / disposition parse / 完整 §0.5 形态等价(以 dogfood PR `20260505-183300-context-import` 为基准)/ CLI exit code / doctor 集成。全套 `pytest`: 265 passed / 3 skipped (217 baseline + 48 new)。
- §0.5 形态等价测试覆盖:3 items + 28 sub-items 的完整 disposition 分布(4 ✅ + 18 ⏭ + 2 📦 + 1 ❓ + 5 ➖)、所有 propagation path 出现、所有 modification 摘要出现、合并视图正确嵌套(feedback-log → preference → runtime)、approve 流水线 + 一句话总结。

## 0.2.3 (dogfood) — 2026-05-05

dogfood pass 修了 7 条 dxyOS 真实使用中暴露的问题。**纯 bug 修复 + 新架构对齐**, 不引入新功能。

### Fixed

- **Bug 1 · `forge ingest --detect` 推荐改用 `forge capture`**: `--detect` 输出末尾的 "to ingest:" 段过去推荐 legacy `forge ingest --from <path>` / `forge ingest --from-claude-memory`,在 personalOS root 下会把 agent 引到 Bug 2 的死路。改为 "to capture:" 段,推荐 `forge capture --from / --from-claude-memory`,与 SKILL.md 的 import 流程一致。
- **Bug 2 · `forge ingest` 在 personalOS root 不再要求 `forge new`**: legacy `forge ingest` 只检查 `sp/section/` 目录,在 v0428 layout 下报 "not a forge workspace. Run `forge new <root>` first." —— 而 skill 明令禁止 `forge new` 用于 personalOS onboarding。改为检测到 personalOS layout (capture/ / system/inbox/ / context build/) 时,直接以 deprecation-style 警告指向 `forge capture`,exit code 2。Legacy SP root 下 `forge ingest` 行为不变。
- **Bug 3 · monitor 与 detect 对 symlink 源路径报告口径一致**: `forge monitor` 过去显示符号链接 resolve 后的 target (`/Users/.../dxy_OS/01 assist/SP/output/codex/AGENTS.md`),`forge ingest --detect` 显示用户配置的符号链接路径 (`~/.codex/AGENTS.md`)。两者口径不一致。统一为符号链接路径 (即用户/工具实际配置的路径); resolved 路径仅用于内部 digest 比对和向后兼容查找。
- **Bug 4 · skill doc ↔ CLI 命令名对齐 (回归测试)**: 新增 `tests/test_bug_4_skill_cli_alignment.py` pin 住 SKILL.md 中的 `forge capture --from / --from-claude-memory` 与 CLI `--help` 输出一致, 以及 `forge ingest --detect` tail 推荐与 SKILL.md 一致 (Bug 1 修完后自然成立)。
- **Bug 5 · BLOCKER · `forge capture` 同秒并发不再崩溃**: `batch_dir.mkdir(parents=True, exist_ok=False)` 在两条 capture 命令落到同一秒时会让第二条抛 `FileExistsError`。改为冲突时追加 `-1` / `-2` ... 序号后缀 (推荐方案 b),保留 `YYYYMMDD-HHMMSS` 主时间戳的可读性,同时 audit trail 仍清晰可分辨。
- **Bug 6 · `forge inbox list` 数据源与 `forge monitor` 一致**: `inbox list` 过去读 `.forge/governance/inbox/` (legacy),`monitor` 读 `system/inbox/` (personalOS),导致同一 root 下 `monitor` 报 3 个 pending、`inbox list` 输出 "(inbox is empty)"。改为优先列 `system/inbox/*.md`,无 personalOS 文件时回退到 legacy queue。
- **Bug 7 · `forge inbox` group 接受 `--root`**: `forge inbox --root <path> list` / `done` / `skip` 过去全部报 `No such option: --root`。在 inbox group 上加了 `--root`,通过 click context 传给 subcommand;subcommand 自身的 `--root` 仍优先生效 (back-compat)。

### Internal

- 新增工具函数 `_looks_like_personal_os(workspace)` 用于 ingest 路径分流。
- 新增 `_inbox_root(ctx, sub_root)` / `_list_personal_os_inbox(workspace)` 用于 inbox 子命令的 root 解析与 source 选择。
- 13 条新增/更新的回归测试 (`tests/test_bug_*.py`),全套 pytest 217 passed / 3 skipped。

## [0.1.0] — 2026-04-24

首次发布。带 schema 检查、provenance、MVC 分层的 review-gated context compiler。

### MVC 分层（这次最重要的架构修正）

- `Section` = Model，装内容。
- `Config` = Controller，**只装控制信息**。v0.1 第一版把 `preamble` / `postamble` / `body` 放在 Config 里是错的——那是内容，现在全部砍掉，强制走 section。v0.1 直接拒绝这三个字段并给出明确迁移指引，不做向后兼容（alpha 阶段，破坏面可控）。
- `Output` = View，编译产物，不手改。
- **Wrapper section（`type: wrapper`）**：用来承载前言 / 结语这种"不是主体 section"的文字。body 原样输出，不 emit `## <name>` 标题、不参与 heading 降级。约定以 `_` 开头命名。

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
- **单测** — 65 个 pytest（section parser、loader、两个 adapter、所有 gate action、bench、provenance、doctor、heading demotion、adapter 扩展、eval 接口、MVC / wrapper）。

### 已验证
- 结构 line recall vs dxyOS 自己 SP-compiled CLAUDE.md：**91.5%**（8.5% gap 是 wrapper 说明文字的措辞差异，不是内容丢失）。
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
