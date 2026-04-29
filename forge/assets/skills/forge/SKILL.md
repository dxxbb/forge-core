---
name: forge
version: 0.2.0
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
- If monitor/doctor fails, show the failing lines and offer to fix.

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

Read pending inbox items and their capture sources.

Create:

```text
system/pr/<YYYYMMDD-HHMMSS>-context-import/proposal.md
```

Proposal must separate:

```text
1. candidate assets
   - user space
   - workspace
   - assist config
   - public knowledge base

2. candidate context projections
   - about user
   - workspace
   - knowledge base
   - preference
   - skill

3. risks
   - privacy
   - overgeneralization
   - stale facts
   - uncertain claims

4. proposed file changes

5. section integration  (REQUIRED — this is what bridges asset → agent)
```

For step 5, every asset file the proposal writes or modifies MUST be
classified by **how the agent will reach it**. Pick exactly one form per
file:

| Form         | When to use                                                        | Effect on section                              |
|--------------|--------------------------------------------------------------------|------------------------------------------------|
| inline       | Short, high-frequency, must be in working context every session.   | Section body summarizes / paraphrases content. |
| L1 pointer   | Medium length; agent reads on demand.                              | Section body says `详见 <path>`.               |
| L2 index     | Many files under one topic; agent navigates via index.             | Section points to an index file; index lists assets. |
| summary      | Long content but TLDR is enough for routing.                       | Section has TLDR; full text stays in asset.    |
| archive-only | Capture/raw evidence, private, or working draft not for agent yet. | Section does NOT reference it. Justify why.    |

For every non-archive form, the proposal must list the section name(s) and
how the upstream / body changes. Example table:

```markdown
| Asset file                                                  | Form        | Target section | How                          |
|-------------------------------------------------------------|-------------|----------------|------------------------------|
| assist config/collaboration preference/feedback-log.md       | L1 pointer  | preference     | upstream + 1-line ref in body |
| capture/import/20260429-152310/raw.md                        | archive-only| —              | raw evidence, kept for trail |
| public knowledge base/topic/tech/ai/memory-patterns.md       | L2 index    | knowledge base | already covered by topic/index.md |
```

`forge doctor` will report per-asset-dir bridge coverage after the proposal
applies — use it as a sanity check, not a gate.

Do not edit asset files or context sections yet.

After writing the proposal, mark the inbox item as processed (it is now
represented by the proposal under `system/pr/`):

```bash
forge inbox done --root <path> <inbox-file-path>
```

The capture under `capture/import/` keeps the original raw evidence; the
proposal under `system/pr/` is the new state of record.

Then tell the user:

```text
Proposal written to system/pr/<id>/proposal.md. Review it and reply approve / reject / revise.
```

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
