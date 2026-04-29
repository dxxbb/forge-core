---
name: forge
version: 0.1.0
description: "Drive the forge-core review-gated context compile flow end-to-end. Auto-invoke when the user wants to (a) onboard onto forge for the first time — phrases: 'set up forge', 'help me start with forge', '管理我的 context', '把我的 CLAUDE.md 用 forge 管', '帮我搭一个 forge 工作区'; or (b) review changes to an existing forge workspace — 'approve my changes', 'review my context', 'forge diff', '过一下', '审一下', 'discard'. Also auto-invoke after the agent has just edited any file under `sp/section/` during this conversation."
metadata:
  requires:
    bins: ["forge"]
  cliHelp: "forge --help"
---

# forge — review-gated context compile

This skill drives `forge-core` end-to-end through natural language. The user shouldn't have to remember CLI commands; this skill picks them.

## Two main flows

1. **Onboarding** — user has no forge workspace yet, or has one but hasn't connected their existing `~/.claude/CLAUDE.md` / `.cursorrules`. Run §Onboarding flow.
2. **Review** — user has an established forge workspace and just edited something, or wants to inspect / approve / reject pending changes. Run §Review flow.

Pick which based on user phrase + workspace state. If unclear, ask once.

## Onboarding flow (8 steps)

This is the "demo the project's point" flow. Run when user says "set up forge", "help me start", "管理我的 context", or similar.

### Step 1 — Resolve the workspace path first

Before any scaffolding, resolve the target directory. Path correctness beats the default.

Say:

> "I'll set up a forge workspace, then import your existing AI context (CLAUDE.md, .cursorrules etc.) into structured sections. You'll see what got classified into what, edit anything wrong, then approve to ship. About 3 minutes."

Then ask:

> "Where should the workspace live? Reply with a path, or say **this directory** to use the current directory."

Wait for the answer. Do not choose a default while waiting.

Path resolution rules:

- If the user says "this directory", "这个目录", "当前目录", "here", or ".", run `pwd` and use that exact directory.
- If the user gives an absolute or relative path, resolve it normally.
- Only if the user explicitly says "default" should you use `~/personalOS`.
- Repeat the resolved absolute path once before modifying files.

Never interpret "这个目录" as `~/personalOS`.

### Step 2 — Scaffold the workspace

Default onboarding is v0428 personalOS. Do **not** call `forge new` for this flow; `forge new` is the old legacy scaffold and creates only `sp/` + `output/`.

If the target path does not exist, create it. If it exists and is empty, use it. If it exists and has user files, ask once before adding the framework.

Create this directory framework in the target path:

```text
capture/{agent history & memory,web clipping,external updates,import}
user space/{daily,profile,goals,notes,private,secret config store}
workspace/{project,topic,writing,whiteboard}
assist config/{collaboration preference,work preference,skill}
public knowledge base/{entity,topic,source}
context build/{sections,config,runtime}
system/{rules,eval,inbox,pr,approve log}
```

Then create the initial context source files under `context build/sections`:

```text
_preface.md
about user.md
workspace.md
knowledge base.md
preference.md
skill.md
```

Use frontmatter names exactly as shown above (`about user`, `knowledge base`, `preference`, `skill`). These are runtime-facing projections, not the user's asset taxonomy.

Create target configs:

```text
context build/config/claude-code.md
context build/config/agents-md.md
```

Both configs include sections in this order: `_preface`, `about user`, `workspace`, `knowledge base`, `preference`, `skill`.

Minimum section templates:

```markdown
<!-- context build/sections/_preface.md -->
---
name: _preface
type: wrapper
---

This file provides guidance to agents when working in this environment.
It is generated from `context build/sections` and `context build/config`; do not edit runtime files by hand.
```

```markdown
<!-- context build/sections/about user.md -->
---
name: about user
type: identity
---

[TODO: import or write the reviewed projection of who the user is, current goals, long-term preferences, and stable background.]
```

```markdown
<!-- context build/sections/workspace.md -->
---
name: workspace
type: workspace
---

[TODO: import or write the reviewed projection of active projects, topics, writing, and current focus.]
```

```markdown
<!-- context build/sections/knowledge base.md -->
---
name: knowledge base
type: knowledge-base
---

[TODO: import or write indexes and pointers to source-grounded knowledge.]
```

```markdown
<!-- context build/sections/preference.md -->
---
name: preference
type: preference
---

[TODO: import or write reviewed collaboration preferences and operating boundaries.]
```

```markdown
<!-- context build/sections/skill.md -->
---
name: skill
type: skill
---

[TODO: import or write skill indexes and reusable workflows agents should know.]
```

Minimum config templates:

```markdown
<!-- context build/config/claude-code.md -->
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

```markdown
<!-- context build/config/agents-md.md -->
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

If git is not initialized, run `git init`. Then run `forge build --root <path>` and `forge doctor --root <path>`.

(Mental note for you, **don't dump on the user**: workspace is a git repo, has structured source sections + cross-runtime configs, generated runtime output, `.forge/` is gitignored runtime state, history lives in git log. You'll surface these facts as the user encounters them, not all at once.)

### Step 3 — One short question, wait for answer

After scaffold + build + doctor succeeds, send exactly this (don't add structure descriptions, don't list commands, don't paraphrase):

> Workspace ready at `<path>`. personalOS framework and context build are initialized.
>
> Want me to import your existing CLAUDE.md / .cursorrules to fill them, or will you write fresh? Reply: **import** / **write** / **explore**

**Then stop.** No tool calls until the user replies. Specifically: **do not** read `~/.claude/CLAUDE.md` or any other personal file, **do not** run `forge ingest`, **do not** preview structure with Read/ls. The workspace exists; that's enough for them to decide.

After reply:
- **import** → Step 4 (detect, confirm sources, ingest)
- **write** → tell them which file to open first (`$EDITOR "context build/sections/about user.md"`), then they call you back when ready to review.
- **explore** → run `cat "context build/sections/about user.md"` so they see the placeholder format, then say "edit any section, then say 'review' or 'over'."

### Step 4 — (only after user said "import") Detect → Emit → Classify → Write

User said "import". forge does NOT call an LLM — **you** do. The flow:

1. **Detect** what's importable
2. **Emit** the source text from forge to your context
3. **Classify** in your own context into 5 sections
4. **Write** each section file via Write tool

#### 4a. Detect

Don't ls / Read / stat yourself. Run:

```bash
forge ingest --detect
```

Paste stdout verbatim. The output lists three families: static files (`CLAUDE.md`, `.cursorrules`, etc.), Claude Code auto-memory (`~/.claude/projects/*/memory/*.md`, often the richest single source), transcripts (counted, v0.4-only).

Ask user:

> "Found N sources. Which to import? Reply:
> - **all** → all Claude memory across projects
> - **<project-slug>** → just one project's memory
> - **<n>** → numbered file from the list
> - **<path>** → some other file you have
> - **skip** → start fresh"

#### 4b. Emit (forge prints source text to stdout)

Once user picks, run with `--emit`:

```bash
# numbered file or arbitrary path
forge ingest --from <path> --emit

# all Claude memory
forge ingest --from-claude-memory --emit

# one project's memory
forge ingest --from-claude-memory --claude-project <slug> --emit
```

stdout is the raw concatenated source with `--- from: <name> ---` provenance headers between files. Workspace is **not** modified by emit. forge has recorded a "pending" origin event.

#### 4c. Classify (you do this in your own context)

Read the emit stdout. Split into 5 sections per this schema:

| Section | What goes here |
|---|---|
| `about user` | identity. Who they are, role, work style. |
| `preference` | agent rules. Boundaries, output style, "don't / always". |
| `workspace` | current active projects, focus areas. |
| `knowledge base` | long-term topic indexes, domain references. |
| `skill` | reusable craft / workflows / procedures. |

Preserve user's actual words. Don't paraphrase. Empty section is fine. For multi-source ingests (Claude memory across projects), use the `--- from: ... ---` headers as provenance — keep them or summarize, your call.

#### 4d. Write (per-section files via Write tool)

For each non-empty section, use Write to create `<workspace>/context build/sections/<name>.md` with this frontmatter:

```yaml
---
name: <name>
type: <identity|preference|workspace|knowledge-base|skill>
---

<body>
```

Type mapping: `about user`→identity, `preference`→preference, `workspace`→workspace, `knowledge base`→knowledge-base, `skill`→skill.

If a section file already exists with non-template content (no `[TODO:` marker), warn the user before overwriting.

After writing, go to Step 5 (`forge review`). The Origin panel will show your `--emit` event; review will show what each section now contains and how output/ will change.

#### Fallback: dump mode (no agent classification)

If you're in a non-agent context, do not pretend forge can classify. Put raw imports under `capture/import/` and ask the user to review before promoting anything into `context build/sections`.

### Step 5 — Write the review as a markdown file the user opens in Obsidian

**Don't try to render the full review in chat.** Long diffs get folded by Claude Code, and tables-with-diffs don't survive the round-trip well. Instead: forge writes a markdown file at `<workspace>/REVIEW.md`, the user opens it in Obsidian / VS Code / any markdown viewer where it renders fully (tables, code-fenced diffs with +/-, headings).

```bash
cd <workspace>
forge review --md
```

This writes `<workspace>/REVIEW.md` and adds it to `.gitignore`. The file contains:

- Header + workspace path
- Origin (where the change came from)
- Summary table (section · Δ bytes · lines · note)
- **Detailed changes**: per-section diff in `diff` code block — actual added/removed lines
- Outputs (rebuild on approve)
- Sync target status
- Action footer (a/r/e/q + how to reply)

Tell the user **two short sentences**:

> "Wrote review to `<workspace>/REVIEW.md` — open it in Obsidian (or `cat` it). Reply here with **a** / **r** / **e** `<section>` / **q** when ready."

Don't paste the file contents. Don't summarize it. The whole point is the user reads it in their own editor where folding doesn't apply.

**Fallback (chat-only)**: if user replies "show it here" / "贴出来" / "我没装 Obsidian", parse the JSON from `forge review --json` and render an inline markdown summary (table only, no per-section diff — that's what would fold). Tell them they can also `cat REVIEW.md` if they want the full diff.

### Legacy: parse JSON and render in chat

(Kept for cases where the user explicitly wants the review in chat. For most cases use `--md` above.)

```bash
forge review --json
```

Parse the JSON. Each `section_changes[]` entry has a `diff` field (unified diff of that section's source file vs HEAD). Use it.

Compose your message in **this exact shape**:

```markdown
## Review · `<workspace path>`

**Origin**: `<origin[0].summary>` _<format origin[0].at as "YYYY-MM-DD HH:MM UTC">_
(if multiple origin events, list each on its own line)

### Summary

| Section | Δ bytes | Lines | Note |
|---|---|---|---|
| `about-me` | -71B | +4 / -10 | filled 2 TODO placeholders, −3 bullets |
| `knowledge-base` | **+376B** ⚠ +137% | +11 / -7 | filled 1 TODO, +4 bullets |
| `preferences` | **-223B** ⚠ -71% | +3 / -16 | filled 1 TODO, −7 bullets |
| `workspace` | **+894B** ⚠ +385% | +18 / -5 | filled 4 TODO, +6 bullets |

### Detailed changes

#### `about-me.md` (-71B)

```diff
<paste section_changes[0].diff verbatim>
```

#### `knowledge-base.md` (+376B ⚠ +137%)

```diff
<paste section_changes[1].diff verbatim>
```

#### `preferences.md` (-223B ⚠ -71%)

```diff
<paste section_changes[2].diff verbatim>
```

#### `workspace.md` (+894B ⚠ +385%)

```diff
<paste section_changes[3].diff verbatim>
```

### Outputs (rebuild on approve)

- `output/CLAUDE.md` **+925B** ← Claude Code (every session)
- `output/AGENTS.md` **+925B** ← Codex / OpenCode / any AGENTS.md-aware tool

> **No external target bound.** `forge approve` only updates `output/`. Bind one with `forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink` for auto-sync.

---

Reply: **a**pprove · **r**eject · **e**dit `<section>` · **q**uit (no `d` here — the diff IS shown above)
```

**Render rules**:

- The summary table comes first so the user gets the shape at a glance.
- Each section's actual diff (added/removed lines) goes into a `diff` code block under "Detailed changes". Markdown renders +/- lines with color in chat.
- ⚠ marker on bytes column when `section.warn === true`. Bold the bytes value when warned.
- "Note" column = `section.summary` from JSON.
- If `targets` non-empty: replace the `> No external target bound...` blockquote with `**Sync target**: \`<targets[0].path>\` \`[<mode>]\``.
- Each `diff` field is already a unified diff (`--- approved/sp/section/...` / `+++ current/sp/section/...` / `@@ ... @@` / +/- lines). Paste verbatim into the code fence; don't truncate (the user wants to see actual changes).
- Don't wrap the whole markdown message in a fence (only the per-section diffs are fenced). Tables / headings need to render.

This is the review the user actually wants — concrete added/removed lines per section, not just "+377B".

#### When user replies

- **"a"** or **"a: <message>"** → `forge approve -m "<message>"` (if no message, ask once for one)
- **"r"** → confirm "discard all working-tree changes? (y/n)", then `yes | forge reject`
- **"e"** or **"e <section>"** → tell user to edit `context build/sections/<name>.md` (v0428) or `sp/section/<name>.md` (legacy) in their terminal, wait for "done", then re-run `forge review --json` and re-render
- **"d"** → user wants the diff. Run `forge review` (no flags), paste relevant excerpts in a fenced block. Warn it's long; offer `--config <name>` or `--source-only` scoping.
- **"q"** → "leaving working tree as-is — say 'review' when ready"

Free-form replies still work ("approve with 'add 8 prefs'", "let me edit preferences"). Single letters are just the shortcut path.

For users who want a real keyboard-driven TUI (live editing, instant feedback): `forge review --tui` in their **own terminal**. Tell them once if they iterate through review repeatedly.

(`forge review --compact` exists too — 4-line CLI summary, useful for non-agent contexts. Skill flow always uses `--json` because that's what lets you render rich markdown.)

### Step 6 — Cross-runtime: show one source, two outputs

The Affects panel in Step 5 already showed both `output/CLAUDE.md` and `output/AGENTS.md` will rebuild. Reinforce the point briefly:

> "Notice the Affects panel listed both `output/CLAUDE.md` and `output/AGENTS.md` rebuilding from the same source change. **One markdown edit, two runtime views.** Add a `cursor` adapter config and you'd see a third line — no source duplication."

Skip a separate `forge build` demo unless the user explicitly asks. The review panel already conveyed the point.

### Step 7 — Approve

Suggest a commit message based on the import (e.g. `import existing CLAUDE.md as initial 5 sections`). Show three options:

```
1. Approve with: "<suggested message>"  (or override)
2. Reject — discard everything just imported
3. Wait — leave it in working tree, decide later
```

Wait for choice. Don't pick for them.

If approve:

```bash
forge approve -m "<message>"
```

v0.2: this is **literally a `git commit`** — the workspace is a git repo, and approve adds a `forge-provenance: version=0.2.0 source=forge-approve` trailer to the commit. So `git log -- sp/` shows the audit trail; `forge changelog` is just a friendlier renderer of the same data; lazygit / VS Code source control / GitHub PRs all work natively.

Show output (paste verbatim into your message — long output collapses otherwise). Then:

```bash
forge changelog -n 3
```

> "This audit trail lives in git history. `forge changelog` renders it; `git log -- sp/` shows the same thing. In 3 months, when you wonder 'when did I add the no-emoji rule?', either command grep-able. **That's the provenance point** — and because the workspace is a real git repo, you can rollback to any commit with `forge rollback <hash>`, push to GitHub, or open PRs against your context."

### Step 8 — Wire output to live Claude Code (no symlink ceremony)

Ask the user **once**:

> "Want me to install `output/CLAUDE.md` to `~/.claude/CLAUDE.md` so future approves automatically refresh what Claude Code reads? (Recommended: yes, in symlink mode — every approve takes effect with no extra step.)"

If yes, run:

```bash
forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink
```

(If `~/.claude/CLAUDE.md` already exists with their old content, the command refuses. Either:
1. Move it aside first: `mv ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak` — then re-run install.
2. Pass `--force` if user explicitly OKs overwrite.)

Tell them what `install` does:

> "Recorded the binding in `.forge/manifest.json`. From now on, every `forge approve` automatically refreshes `~/.claude/CLAUDE.md`. To unbind later: `forge target remove claude-code`."

If the user says "not now," show the equivalent manual command and stop:

> "Run `forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink` whenever you're ready. Until then, your output lives at `output/CLAUDE.md` and Claude Code reads `~/.claude/CLAUDE.md` — they're disconnected."

**Don't auto-install without asking.** `~/.claude/CLAUDE.md` is global config; overwriting it silently is a trust violation.

End the onboarding with: "You're set up. Edit `context build/sections/<name>.md` when context changes, say 'approve' or '过一下', and I'll run the review flow."

## Review flow (when user already has a workspace)

Triggered by phrases like "approve", "过一下", "review my context", or auto-invoked after the agent edited `sp/section/*.md`.

### Step R1 — Locate workspace

Try cwd. If `sp/section/` exists, you're in. Else walk up parents. Else ask user.

### Step R2 — Health check

```bash
forge doctor
```

If errors: stop, show them, ask user to fix or offer to fix together (only edit `sp/config/*.md` after explicit OK).

### Step R3 — Show diff

```bash
forge review --md
```

If output says "no changes": tell user "nothing to review", stop.

Else: tell the user "wrote `<workspace>/REVIEW.md` — open in Obsidian / `cat` it. Reply here with **a** / **r** / **e** `<section>` / **q**." Don't paste the file. The point is they read it in their editor where folding doesn't apply.

If user pushes back ("贴出来" / "no Obsidian"), fall back to `forge review --json` + chat-rendered table (no per-section diff in chat — too long, will fold).

### Step R4 — Suggest message

Read the **What changed** panel from Step R3 (or rerun `forge review --summary-only`), propose a short imperative-mood message (≤ 60 chars). Examples:

| Diff content | Suggested |
|---|---|
| Added a "no emoji" rule to preferences.md | `add no-emoji preference` |
| Updated workspace's project list | `update workspace projects` |
| New _preface wrapper | `add preface wrapper` |
| Removed obsolete preference | `remove stale Python-3.7 note` |

### Step R5 — Decision prompt

```
1. ✅ Approve with: "<suggested>"   (or override)
2. ❌ Reject — discard all sp/ changes
3. ⏸  Wait — leave changes uncommitted
```

Wait for user.

### Step R6 — Execute

#### Approve

```bash
forge approve -m "<final message>"
```

Show approved hash, `wrote` lines, and `synced →` lines (any configured `forge target` bindings auto-pushed in this same approve).

If `forge target list` is empty and the user is on a personal workstation, mention once: "You don't have a target binding. Want me to install one so future approves auto-refresh `~/.claude/CLAUDE.md`? (`forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink`)" Don't repeat this hint after they decline.

v0.2: workspace IS a git repo (onboarding git-inits if needed, every `forge approve` = `git commit`). So you don't need to ask the user "should we git commit?" — that already happened. Instead, ask once: "Want me to `git push` to a remote?" Only push if user explicitly says yes. Don't push to main/master without user explicitly naming the branch.

#### Reject

```bash
yes | forge reject
```

Show result. Mention "sp/ now back to last-approved state."

#### Wait

Do nothing. Tell user "leaving sp/ as-is — say 'approve' or 'reject' when ready."

## Auto-invoke heuristic

If during this conversation the agent (you) has just used Edit/Write on any file matching `sp/section/*.md`, **after the action returns**, proactively run R2 + R3 (doctor + diff) and present the decision prompt. Don't wait for the user to say "approve" — they expect review to happen automatically once they see "Edit succeeded."

Exception: if you're mid-task on a longer multi-edit (e.g. user said "rewrite my whole preferences"), wait until the multi-edit is logically complete.

## Don'ts

- ❌ **Don't auto-import after scaffold.** Step 3 must end with the user saying "A" / "B" / "import <path>". Reading `~/.claude/CLAUDE.md` or running `forge ingest` before they reply is a trust violation — those are personal files, you don't get to scan them just because the workspace exists.
- ❌ Don't auto-approve without showing diff (R3 must run first)
- ❌ Don't run `forge approve` if `forge doctor` returned errors
- ❌ Don't `git push` without explicit user request
- ❌ Don't run `forge target install` without asking the user first — it touches `~/.claude/` (or wherever they install to), which is global config
- ❌ Don't edit `02 user/**` or `06 system/**` in dxyOS-style vaults — those have separate write rules
- ❌ Don't propose changes to `sp/config/master.md` schema unless user asked

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `forge: command not found` | not installed in this env | `pip install -e <forge-core-repo>` |
| `forge not initialized at <path>` | first-time use of this workspace | `forge init` |
| `unknown section X` from doctor | config references missing section | edit `sp/config/*.md` |
| `output_frontmatter must be a mapping` | YAML typo in config | fix the YAML |
| `forge diff` shows `no changes` but user just edited | file is outside `sp/section/` | check path |
| `ANTHROPIC_API_KEY not set` (during ingest) | ingest LLM path needs API key | run with `--no-llm` or set the env var |
