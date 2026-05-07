---
name: forge
version: 0.5.1
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
capture -> system/inbox -> system/pr -> review -> assets/context build -> runtime
```

`forge-core` CLI is only the compiler/gate executor. You, the agent, provide the LLM capability: source discovery, extraction, proposal drafting, and review presentation.

## Trigger

Use this skill when the user says things like:

- `forge建一个工作区`
- `创建 personalOS 工作区`
- `用 forge 管理 agent context`
- `导入我的 CLAUDE.md / memory`
- `review / approve / reject context`

## Flow Selection

First inspect the current working directory and user wording.

- If there is no personalOS framework, run **Initialize Workspace**.
- If the user says `import`, run **Import To Capture**.
- If there are inbox items, run **Process Inbox To Proposal**.
- If there are proposals, run **Review Proposal**.
- If the user says approve/reject while reviewing a proposal, run **Review Proposal**.
- If the user says a vague maintenance phrase such as `forge一下`, `过一下`, or `跑一下 forge`, run **Workspace Triage**.

Do not skip layers. Import never writes directly to `context build/sections`.

## Workspace Triage

This is the default "do the next sensible forge step" flow. Do not ask the user to choose from abstract commands first.

Run:

```bash
forge monitor --root <path>
```

Then choose one next action:

- If monitor says `status: clean`, say it is clean and stop. Do not suggest import.
- If monitor lists pending proposals, review the newest proposal.
- If monitor lists pending inbox and no proposal, process inbox to proposal.
- If monitor lists context source changes, run **Build And Review Runtime**.
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

This lists importable runtime context and Claude memory without reading file contents. Also check local obvious changed personalOS files with:

```bash
git status --short
```

Do not read or import `user space/private/secret config store`, `.env`, credentials, browser cookies, keychains, or token files.

### 2. Present A Default Import Plan

Use concrete candidates from detection. Prefer a short recommendation instead of a taxonomy.

Default recommendation:

- current project Claude memory, if present
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

### 4. Render For User Review

```bash
forge pr render <pr-id> --root <path>            # default: writes inline into proposal.md body
forge pr render <pr-id> --root <path> --plain    # ASCII only (still inline)
forge pr render <pr-id> --root <path> --stdout   # print to stdout, do not modify the file
forge pr render <pr-id> --root <path> --width 78 # explicit wrap width (default 78)
forge pr render <pr-id> --root <path> --no-wrap  # disable content soft-wrap (legacy v0.3.2)
```

The default behavior writes the rendered §0.5 view into the proposal body
between the `<!-- BEGIN AUTO-RENDERED -->` / `<!-- END AUTO-RENDERED -->`
markers — the reviewer opens `proposal.md` in Obsidian / editor and sees
the per-item disposition + propagation tree + merged diff + approve pipeline
directly, no redirection needed. User-authored content outside the markers
is preserved.

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
Proposal written to system/pr/<id>/proposal.md. Run `forge pr render <id>` to see the §0.5 view, then reply approve / reject / revise.
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

When presenting a proposal, `approve` means approve this `system/pr` proposal. Do not ask for a second commit/seal confirmation.

If user approves, apply the proposal:

- write reviewed asset files under `user space`, `workspace`, `assist config`, or `public knowledge base`
- update `context build/sections` only with reviewed projection content

Then run:

```bash
forge build --root <path>
forge doctor --root <path>
forge diff --root <path> --no-color --no-pager
```

If build or doctor fails, stop and show the error. Do not commit.

If build and doctor pass, commit the approved PR state:

```bash
forge approve --root <path> -m "<short message>"
```

This command is a temporary forge-core implementation detail: it rebuilds runtime, stages tracked context paths, and creates the git commit. Do not describe it to the user as a separate approve step. User-visible semantics are simply: "approved proposal applied and committed."

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

- Do not call `forge new`.
- Do not create `sp/` or `output/` during onboarding.
- Do not read private/secret paths.
- Do not import personal files before explicit permission.
- Do not write directly from import into context sections.
- Do not skip `system/inbox` and `system/pr`.
- Do not approve a proposal without explicit user confirmation.
- Do not ask for a second commit confirmation after proposal approval; approval commits if build and doctor pass.
