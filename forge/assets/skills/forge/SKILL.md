---
name: forge
version: 0.15.0
description: "Initialize and operate a personalOS workspace with forge. Use when the user says they want to create/setup/build a forge or personalOS workspace, manage agent context, import existing CLAUDE.md/AGENTS.md/memory, review context changes, or approve/reject context updates. This skill is personalOS-layout-first and must not use legacy `forge new` / `sp` onboarding."
metadata:
  requires:
    bins: ["forge"]
  cliHelp: "forge --help"
---

# forge — personalOS context asset workflow

This skill is the user-facing operator for the personalOS + forge flow.

Hard rule: do **not** use legacy `forge new`, `sp/`, or `output/` for onboarding. The default model is:

```text
source signal / capture -> disposition -> observation/candidate -> owner decision -> assets -> runtime
```

`forge-core` CLI owns durable state, admission checks, budgets, expiry, the compiler gate, ledger, and execution. You, the agent, provide the semantic capability: source discovery, evidence classification, cross-event abstraction, candidate drafting, and concise review presentation.

## Trigger

Use this skill when the user says things like:

- `做一次 forge` / `forge run` / `结算一下` / `有什么待审的`
- `安装 forge` / `install forge`
- `forge建一个工作区`
- `创建 personalOS 工作区`
- `用 forge 管理 agent context`
- `导入我的 CLAUDE.md / memory`
- `review / approve / reject context`

## Bootstrap

Before any flow, check if `forge` CLI is available:

```bash
forge --version
```

If `forge` is not found, install it automatically:

```bash
pipx install git+https://github.com/dxxbb/forge-core.git
```

If `pipx` is not found either, try `uv tool install` or fall back to `pip install --user`. After install, run `forge self-install` to bind the skill to the current runtime, then continue with the user's request.

If the user explicitly says "安装 forge" or "install forge", run the bootstrap, confirm success, and stop — do not proceed to workspace initialization unless they also asked for it.

## Flow Selection

First inspect the current working directory and user wording.

- If the user says `做一次 forge` / `forge run` / `结算`, run **Forge Run**(主工作流).
- If the user asks `有什么待审的` / `队列里有什么`, run `forge run status` and report — do not open a run unless asked.
- If there is no personalOS framework, run **Initialize Workspace**.
- If the user says `import`, run **Import To Capture**.
- If the user says a vague maintenance phrase such as `forge一下`, `过一下`, or `跑一下 forge`, run **Forge Run**.
- Legacy(workspace 尚未启用 zones/run 时才用): inbox items → **Process Inbox To Proposal**;proposals → **Review Proposal**.

Do not skip layers. Import never writes directly to `context build/sections`.

## Forge Run(主工作流)

The run is the only governance workflow once zones are initialized: an
owner-initiated settlement conversation. Between runs, never raise governance
topics proactively in work sessions.

### One-time setup(workspace 还没有 zones.yaml 时)

1. Draft `context build/zones.yaml`(rule zone = 偏好/边界/行为规则类 sections),
   present to owner for approval — zone membership is an owner decision.
2. After approval: `forge zone init`(activates the compile gate),then
   `forge migrate amnesty` to settle any historical workbench backlog.
3. Report what amnesty did; rule candidates will surface in the next run's ask list.

### The run

```
1. forge run status          → 开场白:距上次 N 天、来源 attention、待问几条、状态新鲜度
2. forge run open            → 固定本轮 Source Batch 与新 capture 指纹;自动续接未关闭 run且不替换原批次
3. 循环 `forge run next --budget N`,每次只执行返回的一个 action,直到 action=close:
   - `decide-integrity` → 一次只呈现这一项,等待 owner approve/reject
   - `classify-source-item` → 只处理 contract 指定的一个 Review Unit/handler/constraints
   - `classify-source` → 只处理没有 Review Unit adapter 的单一来源合同,不得自行拆批或扩流程
   - `classify-evidence` → 只处理 contract 指定的一条 capture evidence
   - `decide-candidate` → 一次只呈现这一张卡,等待 owner 裁决
   - `close` → 立即执行 `forge run close`
4. classify action 必须且只能给当前 Review Unit 记录一个 disposition；来源批次使用 `forge run disposition <source> --item <unit-id> ...`，禁止整批共用一个判断:
   - 已覆盖 → `forge run disposition <input> --as covered --sink <existing-asset>`
   - 一次性缺陷 → 修代码/测试/Issue 后记 `one-off --sink <receipt>`;不建长期规则
   - 易变项目事实 → ledger 写入带日期状态后记 `volatile-state --sink <path>`
   - 证据不足但可能复现 → `forge observation record ... --event-id <stable-event-id>`,再记 `observe --sink <obs-id>`
   - 满足晋升依据 → `forge candidate create ... --event-id <stable-event-id>`,再记 `candidate --sink <cand-id>`
   - 无价值 → `closed --note <reason>`;raw evidence 仍保留
   - 本批确实无法处理 → `defer --note <reason>`;最终状态必须是 incomplete
5. `decide-candidate` 不是只报一条建议。用简单自然语言完整讲清:为什么现在提出、来自哪些真实经历、现有资产已覆盖什么/还缺什么、为什么这项变化值得成为 owner 管的长期资产而不是代码/测试/状态/Skill/平台通用底线或继续观察、为什么达到晋升门槛、准确写入内容、以后会改变什么,最后问卡片里的准确裁决问题。结构完整即可,不要求固定措辞;不得把卡片压缩成一句“正确的规则”。owner 一句话裁决 →
   - 同意:`forge run decide <id> --approve [--note]`
   - 不写:`forge run decide <id> --reject [--note]`
   - 继续观察:`forge run decide <id> --observe [--note]`
   “修改范围/解释/举例”不是裁决;解释不写盘,修改用 `forge candidate revise <id> ...` 更新同一张卡后再呈现,不要创建第二张卡。
6. close 后原样报告 CLI 的最终机器事实:`complete|batch-complete|incomplete`、Run 已关闭/仍打开、工作树 clean/dirty、commit、Selection Coverage、Candidate Conclusion 与剩余可筛选单元。不得把 batch-complete 或本批候选 0 说成全部处理完/没有候选。
```

`N` 默认 3。owner 说“只有 1 分钟”时,本轮所有 `run next` 都使用 `--budget 0`;仍须处理完整性问题和 Source Batch,但不展示 Candidate。

Source-specific hard bounds:

- Agent Memory:只读 contract 当前列出的一个 Review Unit。Codex 的单元是 `MEMORY.md` 中一个 Task Group,Claude 的单元是一个非索引 memory 文件；聚合索引、raw history、archived sessions 只作 evidence pointer/诊断,不得扫描。批次同时受最多 10 单元与 128 KiB 限制。Review Unit 和 evidence 文件都不是“独立经历”的计数单位;按底层 thread/session/source event 生成稳定 `event-id`，同一次经历的多个摘要/指针共用一个 id。
- Web clipping:只读 contract 列出的最多 5 个文件。默认只搜索已有 canonical asset 作为 sink;未经 owner 明确要求,禁止启动 deep `knowledge-intake`、外部调研或逐篇全文走读。
- Web clipping 已由 Source Batch 独占,不要再把同一路径当普通 capture evidence 分流。
- Agent Memory 的 provider-managed raw capture 同样只是 evidence 副本,不要再作为 standalone capture 重复分流。
- `classify-*` 是后台工作。进度只报告已处理/剩余数量和当前是否出现 owner 决策,不得主动念出 covered/closed/Observation 的主题或内容;owner 明确询问观察池时才展开。只有 `decide-integrity` / `decide-candidate` 进入前台。

### Run 铁律

- 预算神圣:`run next --budget N` 固定问序和候选上限;未展示候选留在系统状态,不称为 owner 欠下的待办。
- Run Contract 是唯一下一步;不并行处理后续 input,不跳过,不自行重排。
- 不硬凑:来源与 capture 都干净时说“没有”,空 Run 不生成审计文件或 Git 提交。
- 全局候选结论:仍有 Source Review Unit 或 standalone capture evidence 未筛选时必须说 `unknown`;只有 Selection Coverage=complete 且 pending Candidate=0 时才能说“没有候选”。Observation 已分流,不算未筛选 backlog。
- 裁决即执行,立刻报结果,不留"稍后处理"。
- 候选准入只允许:`repeated` = 两个以上不同 `event-id`；`owner-directed` = owner 明确要求**未来长期沉淀**并在卡片保存准确原话。`high-risk` 只是优先处理信号,不能替代长期资产证据:单次高风险事件若有确定性控制缺陷,走 one-off 的代码/测试/门禁闭环；否则进 Observation；只有 owner 明确要求长期沉淀时才可由单次事件建 Candidate。用户只要求“这次认真做/先判断/给教程”不等于 owner-directed。拿不准是否能长期一般化时必须进 Observation,不能先建 Candidate 再建议“继续观察”。
- evidence path 只是证据指针,不能充当独立事件。同一 thread 的 Task Group、rollout summary、raw session 即使是三个文件也只算一个 event。不要用会漂移的 `MEMORY.md#Lx-Ly` 作为唯一来源;保留稳定 event id、具体来源情境和稳定 summary/session 指针。
- `source-context` 只能描述真实发生的行为、纠正、决定或失败；“如果犯错可能有严重后果”不是事件证据,不能凭假设风险制造 Candidate。
- Candidate 创建前必须读取目标及直接相关的 canonical asset,写清 `existing-coverage` 与未覆盖的 durable delta,并用 `asset-fit` 说明为什么 owner 管的长期资产是正确落点,而不是代码/测试、易变状态、可复用 Skill、平台/模型通用底线或 Observation。无法说明时用 covered/one-off/closed/observe,不要把比较工作留给 owner。
- Candidate 卡除原有 problem/proposal/scope/exclusions/patch/verification 外,必须给出 `source-context`、`existing-coverage`、`asset-fit`、`promotion-rationale`、`expected-effect`、`decision-question`。CLI 缺任何一项会拒绝创建。
- 候选目标在 approve 前不得写入 canonical asset;规则区脱离候选卡的直接改动属于 unqualified-change。
- close 前每条 Source Batch/capture input 必须有 disposition;非 defer 必须推进 provider checkpoint;观察池有期限,不是永久 backlog。
- decide 报 stale/failed → 如实报错,标记下次重备,再调用 `run next`;run 中断 → 下次 open 自动续接原批次。

### 随时可答的只读问题(不需要 run)

- "这条规则哪来的" → `forge ledger blame <path> --line N`
- "这个文件最近改了什么" → `forge state show <path>`
- "上次结算是什么时候" → `forge run status`
- "观察池里有什么" → `forge observation list`
- "这张候选是什么" → `forge candidate show <id>`
- "这条资产还有效吗" → `forge candidate list --all` + `forge run status`;真实使用后用 `forge candidate feedback <id> --outcome effective|revise|retire --evidence <receipt>` 留痕

## Workspace Triage

This is the default "do the next sensible forge step" flow. Do not ask the user to choose from abstract commands first.

Run:

```bash
forge monitor --root <path>
```

Then choose one next action:

- If monitor says `status: clean`, say it is clean and stop. Do not suggest import.
- If monitor lists pending proposals, review the newest proposal through the Portal-first review flow.
- If monitor lists pending inbox and no proposal, process inbox to proposal.
- If monitor lists context source changes, run **Build And Review Runtime** and generate the Portal diff.
- If monitor lists import source updates, run **Import To Capture** with those concrete updates as the recommended plan.
- If monitor lists `workspace-project changed: <name> · ...` lines, run **Workspace-Project Sync** for that project.
- If monitor ends with a `note: N project onepage(s) ... on legacy schema` hint, run `forge migrate-onepage --root <path>` (a pure schema backfill, no review needed) and stop. Use `--dry-run` first if you want a preview.
- If monitor/doctor fails, show the failing lines and offer to fix.

## Workspace-Project Sync

Some `workspace/project/<name>/onepage.md` files declare an external working directory via frontmatter:

```yaml
---
kind: project
name: <name>
upstream:
  local_dir: ~/workspace/projects/<name>/
  status_sources:
    - REPORT.md
last_synced:
  commit: <git HEAD at last sync>
  at: <ISO timestamp>
---
```

When `forge monitor` reports a `workspace-project changed` line, capture the upstream state and let the user decide what to propagate into the onepage body:

```bash
forge capture --root <path> --workspace-project <name>
```

This synthesizes a capture file from `git log <last_synced>..HEAD --oneline`, `git diff --stat`, `git status --short`, and the head of each `status_sources` file, then creates an inbox item of type `workspace-project-update`. Process it through the normal inbox → proposal → review flow.

When the resulting PR is approved (`forge pr done`), forge automatically injects `last_synced.commit` (taken from upstream HEAD) and `last_synced.at` into the onepage frontmatter. The user's git commit picks them up alongside the body change.

`--reject` does not update `last_synced` — the PR did not represent a real sync.

## Initialize Workspace

### 1. Resolve Path

If the user started Claude Code in the intended directory and says `这个目录`, `当前目录`, `here`, or `.`, run `pwd` and use that exact directory.

If the user gives a path, resolve it. If they explicitly say default, use `~/personalOS`.

Before modifying files, state the resolved path in one sentence.

### 2. Check Forge

Run:

```bash
forge --version
```

If `forge` is missing, ask for the forge-core checkout path or suggest:

```bash
cd /path/to/forge-core
python3 -m pip install -e .
```

Do not continue until `forge --version` works, unless the user explicitly asks for a dry scaffold without build.

### 3. Scaffold Directories

Create this framework:

```text
capture/
  agent history & memory/
  web clipping/
  external updates/
  import/

user space/
  daily/
  profile/
  goals/
  notes/
  private/
    secret config store/

workspace/
  project/
  topic/
  writing/
  whiteboard/

assist config/
  collaboration preference/
  work preference/
  skill/

public knowledge base/
  entity/
  topic/
  source/

context build/
  sections/
  config/
  runtime/

system/
  rules/
  eval/
  inbox/
  pr/
  approve log/
```

If the directory already has user files, ask once before adding the framework. If it is empty or already has partial personalOS directories, continue.

### 4. Create Initial Context Build Source

Create `context build/sections/_preface.md`:

```markdown
---
name: _preface
type: wrapper
---

This file provides guidance to agents when working in this environment.
It is generated from reviewed personalOS context projections. Do not edit runtime files by hand.
```

Create `context build/sections/about user.md`:

```markdown
---
name: about user
type: identity
---

[TODO: reviewed projection of who the user is, current goals, long-term preferences, and stable background.]
```

Create `context build/sections/workspace.md`:

```markdown
---
name: workspace
type: workspace
---

[TODO: reviewed projection of active projects, topics, writing, and current focus.]
```

Create `context build/sections/knowledge base.md`:

```markdown
---
name: knowledge base
type: knowledge-base
---

[TODO: reviewed index of source-grounded knowledge assets.]
```

Create `context build/sections/preference.md`:

```markdown
---
name: preference
type: preference
---

[TODO: reviewed collaboration preferences and operating boundaries.]
```

Create `context build/sections/skill.md`:

```markdown
---
name: skill
type: skill
---

[TODO: reviewed skill indexes and reusable workflows agents should know.]
```

Create `context build/config/claude-code.md`:

```markdown
---
name: CLAUDE
target: claude-code
sections:
  - _preface
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
required_sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
demote_section_headings: true
---
```

Create `context build/config/agents-md.md`:

```markdown
---
name: AGENTS
target: agents-md
sections:
  - _preface
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
required_sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
demote_section_headings: true
---
```

Create `README.md` if missing:

```markdown
# personalOS

This workspace follows the current personalOS layout.

- `capture/`: raw imported evidence.
- `user space/`: personal material; private/secret config stays no-agent by default.
- `workspace/`: active projects, topics, writing, and whiteboards.
- `assist config/`: collaboration preferences, work preferences, and skills.
- `public knowledge base/`: source-grounded external knowledge.
- `context build/`: reviewed context projections, target configs, and generated runtime.
- `system/`: rules, eval, inbox, PR state, and approve log.
```

Initialize git if needed:

```bash
git init
```

Then run:

```bash
forge build --root <path>
forge doctor --root <path>
```

Report only:

```text
Workspace ready at <path>. personalOS framework and context build are initialized.

Want me to import existing context/memory now? Reply: import / write / explore
```

Stop after this. Do not read personal files until the user says `import` or gives explicit paths.

## Import To Capture

Import is evidence intake. It must not directly update `context build/sections`.

### 1. Detect Concrete Sources First

If the user said bare `import`, that is enough permission to run metadata-only detection. Do not ask a broad "which category?" question first.

Run:

```bash
forge ingest --detect --root <path>
```

This lists importable runtime context plus agent memory/history (Claude Code and Codex) without reading file contents. Also check local obvious changed personalOS files with:

```bash
git status --short
```

Do not read or import `user space/private/secret config store`, `.env`, credentials, browser cookies, keychains, or token files.

### 2. Present A Default Import Plan

Use concrete candidates from detection. Prefer a short recommendation instead of a taxonomy.

Default recommendation:

- current project Claude memory, if present
- Codex memory/history, if present (`~/.codex/memories`, rollout summaries, and history/archived-session jsonl; live sessions are intentionally skipped)
- changed non-private personalOS notes shown by `git status`, if relevant
- global runtime context only if the user is onboarding or explicitly asks to refresh runtime context

Say:

```text
Found <n> concrete import candidates. Recommended: <specific source(s)>.
Reply `go` to capture those, `all memory`, a number/path, or `skip`.
```

Then stop. This is the one useful confirmation point: capture reads personal files.

### 3. Capture Raw Evidence

After the user picks a concrete source, use `forge capture` so the CLI owns the capture/inbox file format.

Examples:

```bash
forge capture --root <path> --from <file>
forge capture --root <path> --from-claude-memory
forge capture --root <path> --from-claude-memory --claude-project <slug>
forge capture --root <path> --from-codex-memory
```

For pasted material:

```bash
forge capture --root <path> --from-stdin
```

After import, stop and say:

```text
Imported raw material into capture and created an inbox item. Reply "process inbox" to generate a proposal.
```

## Process Inbox To Proposal

Read pending inbox items and their capture sources, then turn them into
a schema-aware proposal under `system/pr/<id>/proposal.md`.

For large imports, especially agent memory/history, do **not** go straight to
`forge proposal new`. Start with a staged workbench:

```bash
forge proposal workbench --root <path> --inbox <id-prefix>
```

The workbench is not an approval PR. It creates
`system/pr/<id>/workbench.md` with:

- an item list extracted from the inbox/capture evidence;
- a batch plan for small-step triage;
- required fields such as `canonical_sink_status`, `fact_volatility`,
  `live_verify_required`, `privacy_level`, `apply_scope`, and `covered_by`;
- a cross-review checkpoint before canonical-source edits;
- a rule that final `proposal.md` is created only after item-level user review.

Use the workbench when a single inbox item contains many facts, many projects,
or a long memory/history corpus. The normal proposal flow below is for small
or already-triaged imports.

The schema-driven flow (default for v0.3+):

### 1. Scaffold The Proposal Stub

```bash
forge proposal new --root <path>                       # all pending inbox
forge proposal new --root <path> --inbox <id-prefix>   # one inbox item
```

This creates `system/pr/<YYYYMMDD-HHMMSS>-context-import/proposal.md` with
v0.3 YAML schema frontmatter pre-populated:

- `inbox_sources`, `capture_sources` derived from the inbox files
- `items[]` skeleton — one item per inbox source, with `monitor_info` and
  `extracted` pre-filled from inbox + capture frontmatter
- Each item's `disposition` carries an enum-hint placeholder
  `'<APPLY|COVERED|ARCHIVE|DECIDE|NA|MIXED>'` — replace the placeholder
  with the actual enum value (`APPLY`, `ARCHIVE`, etc.); `disposition_note`
  is left empty for an optional one-line tagline.
- The `propagation:` placeholder includes `layer:` and `modification:`
  fields so the validator's "non-terminal node missing modification" check
  doesn't fire on a fresh stub.
- The proposal body carries `<!-- BEGIN AUTO-RENDERED -->` /
  `<!-- END AUTO-RENDERED -->` markers; `forge pr render` writes the §0.5
  view between them so reviewers see the rendered tree directly when they
  open `proposal.md`.

### 2. Fill The Schema

Edit the proposal frontmatter. For each item, set:

```yaml
items:
  - id: '1'
    monitor_info: <path + size + nature>
    extracted: |
      capture/.../<file>
      <key facts, dates, quotes>
    disposition: APPLY | COVERED | ARCHIVE | DECIDE | NA | MIXED
    disposition_note: <one-line tag, e.g. "提炼为新规则 §10">
    rationale: |
      <why this disposition? cite covering asset / new content / boundary>
    propagation:
      - branch: a
        node:
          path: feedback-log.md
          layer: "Layer 1 · asset"
          modification: |
            末尾追加 §10 ...
          children:
            - branch: b
              shared_with: [3.2, 3.3]   # optional, if this branch is shared with other sub-items
              node:
                path: preference.md
                layer: "Layer 2 · section"
                modification: ...
                children: []   # leaf
```

For `MIXED` items (e.g. an auto-memory dump with N files), use `sub_items[]`
where each sub-item has its own disposition + propagation.

For `DECIDE` items, use `options[]` (each option has its own propagation
tree); set `recommendation` to the preferred option id.

`COVERED` items need `covered_by` (where the content already lives).
`NA` items need `reason` (e.g. "auto-memory index, not asset content").

#### v0.7 alternative: `modified_files` (let forge derive propagation)

Hand-drawing `propagation:` is tedious and error-prone — the rules are
mechanical (KB topic / asset → reverse-lookup `sections.upstream` → section
→ runtime; sections file → runtime; KB index/log/raw clipping → terminal).
v0.7 lets you list the files you touched and have forge build the tree for
you:

```yaml
items:
  - id: '1'
    monitor_info: ...
    extracted: ...
    disposition: APPLY
    rationale: ...
    modified_files:
      - public knowledge base/topic/tech/ai/compute/ai-compute.md  # main: asset → section → runtime
      - public knowledge base/topic/index.md                        # terminal hint
      - public knowledge base/topic/log.md                          # terminal hint
    modifications:
      'public knowledge base/topic/tech/ai/compute/ai-compute.md': |
        新建文件, frontmatter + summary + 子主题
      'public knowledge base/topic/index.md': 'tech/ai/ 段加 ai/compute/ sub-section'
      'public knowledge base/topic/log.md': '+ ai-compute.md created'
    propagation_hints:
      'public knowledge base/topic/index.md': terminal
      'public knowledge base/topic/log.md': terminal
    # propagation: (omitted — `forge proposal validate` will fill it)
```

`forge proposal validate` will reverse-look up `context build/sections/*.md`
upstreams + `context build/config/*.md` targets and write a populated
`propagation:` tree into the same file. Hints: `terminal` (single node, no
downstream), `light` (terminal + label), default `full` = auto.

Already filled `propagation` always wins — the resolver skips with a
warning. Pass `--no-resolve` to disable v0.7 entirely.

### 3. Validate

```bash
forge proposal validate <pr-id> --root <path>
```

Reports schema violations in `forge doctor` style. Fix until the validator
returns `OK`. On success the validator auto-renders the §0.5 view into the
proposal body's BEGIN/END block (same as `forge pr render`); pass
`--no-render` to skip that step.

v0.3.2+: validate also auto-reformats the YAML frontmatter so multi-line
strings (`extracted`, `rationale`, `covered_by`, …) are emitted as YAML
literal block scalars (`|`) instead of single-line `\n`-escaped flow scalars
or folded `'…'` scalars. The proposal body — including the BEGIN/END
auto-rendered §0.5 view — is left untouched. Pass `--no-reformat` to skip,
or run `forge proposal reformat <pr-id> --root <path>` standalone to fix
existing v0.3.1 PRs without re-validating.

v0.3.3+: reformat additionally breaks any single-line plain scalar > 90
display cols at CJK / ASCII punctuation, inserting `\n` so the output goes
to block-scalar (`|`) form. This keeps Obsidian / terminal viewers from
folding plain scalars at unpredictable widths. Pass `--no-break-lines` to
skip the break-long-lines pass and keep the v0.3.2 YAML-style-only
normalization.

v0.3.4+: punctuation set is split — CJK fullwidth `，。；：、！？）】」』→`
break IMMEDIATELY (no trailing space needed), but ASCII `,;.!?)` are break
candidates ONLY when followed by space or end-of-string. This guards file
extensions (`CLAUDE.md`), IPs (`192.168.1.1`), domains (`example.com`),
and version strings (`v0.3.3`) from being split mid-token. **For Chinese
sentence breaks, write the fullwidth `，` — ASCII `,` between CJK chars
is no longer a break candidate.**

### 4. Prepare Portal Review Surface

The default review surface is the audit Portal, not the text §0.5 block.
Portal review only becomes meaningful after the proposed source/context edits
exist in the working tree, because `forge audit portal --diff` compares the
working tree against the base ref and then expands source -> section -> runtime
lineage.

For an inbox-derived proposal, after filling the schema:

1. Apply the proposal's proposed asset/context edits to the working tree without
   approving or committing.
2. Run `forge proposal validate`.
3. Run `forge build` and `forge doctor`.
4. Run `forge audit portal --diff --base HEAD`.
5. Present the Portal path as the primary review surface, with `proposal.md` as
   the audit record.

Use `HEAD` as the base unless the user explicitly asks to review against a
different commit/ref.

```bash
forge proposal validate <pr-id> --root <path>
forge build --root <path>
forge doctor --root <path>
forge audit portal --root <path> --diff --base HEAD
```

If `forge build`, `forge doctor`, or Portal generation fails, stop and show the
error. Do not approve.

### 4.5 Text Fallback: Render §0.5

```bash
forge pr render <pr-id> --root <path>            # default: writes inline into proposal.md body
forge pr render <pr-id> --root <path> --plain    # ASCII only (still inline)
forge pr render <pr-id> --root <path> --stdout   # print to stdout, do not modify the file
forge pr render <pr-id> --root <path> --width 78 # explicit wrap width (default 78)
forge pr render <pr-id> --root <path> --no-wrap  # disable content soft-wrap (legacy v0.3.2)
```

This is the fallback review surface when the Portal is unavailable, too noisy
for the specific change, or the user explicitly requests a text-only review.
The default behavior writes the rendered §0.5 view into the proposal body
between the `<!-- BEGIN AUTO-RENDERED -->` / `<!-- END AUTO-RENDERED -->`
markers — the reviewer opens `proposal.md` in Obsidian / editor and sees
the per-item disposition + propagation tree + merged diff + approve pipeline
directly. User-authored content outside the markers is preserved.

v0.3.3+: render and reformat default to wrap content at 78 display cols
(CJK = 2 cols), preferring CJK fullwidth punctuation (`，。、；：！？）】」』→`)
or ASCII punct + space or ASCII whitespace as break points; box rules /
sub-item title bars length-equalize to the same width. Use `--width N` to
change the wrap / border target, or `--no-wrap` to revert to the v0.3.2
unwrapped output (box rules still respect `--width`).

v0.3.4+: tree-form `提取信息` continuation prefix is corrected — `├─ X`
paragraph wraps to `│  X` (3 cols) and `└─ X` last paragraph wraps to
`   X` (3 spaces, no `│`). The wrapped content column now strictly aligns
with the paragraph's first content char, eliminating the v0.3.3 1-column
visual offset.

Use `--stdout` only when you specifically need the text in the terminal
(e.g. piping through grep). Do NOT hand-write a parallel markdown view.

### 5. Process Inbox

After proposing, close the inbox items the proposal represents:

```bash
forge inbox done --root <path> <inbox-file-path>
```

The capture under `capture/import/` keeps the original raw evidence; the
proposal under `system/pr/` is the new state of record.

Then tell the user:

```text
Proposal written to system/pr/<id>/proposal.md. I will prepare the working-tree review state and open/generate `forge audit portal --diff`; reply approve / reject / revise after reviewing the Portal. §0.5 is available as text fallback via `forge pr render <id>`.
```

### Disposition reference

Every monitored item / sub-item MUST be classified into exactly one of:

| Icon | Disposition | When to use                                                      |
|------|-------------|------------------------------------------------------------------|
| ✅   | APPLY       | Distill into a new asset/section change. Requires propagation tree with modifications. |
| ⏭   | COVERED     | Already covered by an existing asset → skip. Requires `covered_by`. |
| 📦   | ARCHIVE     | Capture-only audit trail. Propagation is **optional** — leave empty for "no propagation, only the capture file is the trail". |
| ❓   | DECIDE      | Needs user decision. Multiple propagation options; user picks one. |
| ➖   | NA          | Index file / not asset content. Requires `reason`.               |
| 🔀   | MIXED       | Composite item — `sub_items[]` each get their own disposition.   |

Counting rule for MIXED: the disposition distribution counts **only
sub-items**, not the MIXED parent itself. If you note "the parent capture
is also archived as a trail" that goes in the parent's `disposition_note`
(string text), not as an extra ARCHIVE entry — the schema would
double-count the trail otherwise.

`forge doctor` will report per-asset-dir bridge coverage after the proposal
applies — use it as a sanity check, not a gate. It also reports each PR's
schema completeness alongside (info-only).

### Fallback: hand-written markdown proposal

If the schema is too rigid for a particular case (rare), you may still write
the proposal body as plain markdown without an `items:` block. `forge pr
done` / `forge approve` continue to work on hand-written proposals. But
`forge pr render` and `forge proposal validate` only operate on schema-
opted-in proposals; the validator/doctor will report the proposal as
`schema=opt-out` and skip schema checks. Default to schema-driven.

## Review Proposal

When presenting a proposal, `approve` means approve this `system/pr` proposal
and the current working-tree review state shown in the Portal. Do not ask for a
second commit/seal confirmation.

Before asking for approval, the proposal's asset/context changes must already
be present in the working tree and reviewed through the Portal-first flow:

- write reviewed asset files under `user space`, `workspace`, `assist config`, or `public knowledge base`
- update `context build/sections` only with reviewed projection content

Then run or confirm:

```bash
forge build --root <path>
forge doctor --root <path>
forge diff --root <path> --no-color --no-pager
forge audit portal --root <path> --diff --base HEAD
```

If build, doctor, or Portal generation fails, stop and show the error. Do not
commit.

Only after the user explicitly approves the Portal/proposal review state, commit
the approved PR state:

```bash
forge approve --root <path> -m "<short message>"
```

This command is a temporary forge-core implementation detail: it rebuilds runtime, stages tracked context paths, and creates the git commit. Do not describe it to the user as a separate approve step. User-visible semantics are simply: "approved Portal/proposal state applied and committed."

Finally, close the PR — appends a one-line summary to `system/approve log/<date>.md`
and removes the PR directory:

```bash
forge pr done --root <path> -m "<short message>" <pr-id>
```

If user rejects, close as rejected (logged under `system/reject log/`) and do
not touch assets/context:

```bash
forge pr done --root <path> --reject -m "<reason>" <pr-id>
```

If user asks revise, update only the proposal and do not build or commit.

## Build And Review Runtime

Use this only when context source changed outside a proposal and the user asks to inspect the runtime effect.

```bash
forge build --root <path>
forge doctor --root <path>
forge diff --root <path> --no-color --no-pager
```

Show the high-signal summary. Do not paste enormous diffs unless user asks.

Runtime files are generated only:

```text
context build/runtime/claude-code/CLAUDE.md
context build/runtime/agents-md/AGENTS.md
```

## Reject Applied Runtime Changes

If context source was changed outside the proposal flow and user asks to reject/discard:

```bash
forge reject --root <path>
```

Only approve a proposal after the user explicitly says approve/同意/可以/确认 while reviewing that proposal.

## Safety Rules

- Never raise governance topics proactively in a work session; the forge run is owner-initiated only.
- Never expect rule-zone edits to take effect without an owner decision — the compile gate holds them, by design.
- Do not call `forge new`.
- Do not create `sp/` or `output/` during onboarding.
- Do not read private/secret paths.
- Do not import personal files before explicit permission.
- Do not write directly from import into context sections.
- Once zones/run are active, do not route new intake through legacy `system/pr`; inbox/proposal remain compatibility-only for workspaces not yet migrated.
- Do not hand-edit `system/observations` or `system/candidates`; use their CLI commands so admission, expiry, and metrics stay valid.
- Do not promote any candidate without an explicit owner decision.
- Do not approve a proposal without explicit user confirmation.
- Do not ask for a second commit confirmation after proposal approval; approval commits if build and doctor pass.
