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

### Step 1 — Show what forge is doing for them

Before any commands, give a one-line framing:

> "I'll set up a forge workspace, then import your existing AI context (CLAUDE.md, .cursorrules etc.) into structured sections. You'll see what got classified into what, edit anything wrong, then approve to ship. About 3 minutes."

Then ask: **"Where should the workspace live? (default: `~/forge-context`)"** Wait for answer or default.

### Step 2 — Scaffold the workspace

```bash
forge new <path>
cd <path>
```

v0.2: `forge new` does **everything** — scaffolds files, runs `git init`, builds output, makes the first commit. No separate `forge init` needed. The workspace is a git repo from minute zero (any approve = a real git commit, viewable in `git log`, lazygit, GitHub PRs).

After it runs, **briefly** describe the structure:

> "Scaffolded:
>   - `sp/section/` — 5 source sections (about-me, preferences, workspace, knowledge-base, skills) + 1 wrapper. Markdown files you own.
>   - `sp/config/` — 2 configs: one outputs `CLAUDE.md` (Claude Code), one outputs `AGENTS.md` (Codex / OpenCode / etc.). Same 5 sections, two views.
>   - `output/` — compiled views (rebuilt on every approve, git-tracked).
>   - `.git/` — your audit trail. `git log -- sp/` is `forge changelog`.
>   - `.forge/` — runtime state (target bindings + origin tracking). Gitignored.
>
> Each section has a TODO placeholder. We'll fill them by importing your existing context next."

### Step 3 — Show the empty workspace, ask permission to import

**STOP HERE before doing anything else.** After `forge new` finishes, the user has an empty 5-section workspace with TODO placeholders. **Show them what they have**, then **ask** whether to import existing context. Don't move on without an explicit yes.

First, summarize what they actually got. Read enough of `sp/section/*.md` to confirm structure (or use `ls`); then output a message like:

> "Workspace scaffolded at `~/forge-context/`. Here's the frame:
>
> ```
> sp/section/
>   about-me.md       — identity (TODO placeholder)
>   preferences.md    — agent rules (TODO placeholder)
>   workspace.md      — current projects (TODO placeholder)
>   knowledge-base.md — long-term topics (TODO placeholder)
>   skills.md         — reusable craft (TODO placeholder)
>   _preface.md       — wrapper, prepends to compiled output
> sp/config/
>   claude-code.md    — compiles to output/CLAUDE.md
>   agents-md.md      — compiles to output/AGENTS.md
> output/             — already built (placeholders rendered)
> ```
>
> The workspace is also a git repo (initial commit `<short-hash>`).
>
> Two ways to fill the placeholders:
>
> **A. Import what you have already.** I can scan `~/.claude/CLAUDE.md`, project-level `./CLAUDE.md`, `.cursorrules`, etc. and split them into the 5 sections. You review the split, edit anything wrong, then approve. **This is the fastest path if you've been hand-maintaining `CLAUDE.md`.**
>
> **B. Write fresh.** Open each section yourself in $EDITOR.
>
> Which? Reply with **A** (and I'll detect what's importable first), **B** (you'll edit), or tell me a specific path you want to import (e.g. 'import ~/notes/preferences.md')."

**Then wait for the user's reply.** Don't run `forge ingest`, don't read existing CLAUDE.md / .cursorrules, don't preview anything beyond what you've already shown. The user is in control of whether import happens at all.

### Step 4 — (only if user said A or named a file) Detect + ingest

This step **only runs** after the user agreed to import. If they said B or stayed silent, skip to Step 5 (let them edit).

#### 4a. Detect what's importable

Now scan for sources (only after user consent):
- `~/.claude/CLAUDE.md`
- `<cwd>/CLAUDE.md` (project-level if user is in a repo)
- `~/.cursor/rules/` (or `.cursor/rules/` in cwd)
- `<workspace>/AGENTS.md` and similar

Show what you found and **ask one more time** if there's anything sensitive:

> "Found:
>   - `~/.claude/CLAUDE.md` (8.2 KB) — your global Claude Code instructions
>   - `./CLAUDE.md` (1.4 KB) — this project's CLAUDE.md
>   - No .cursorrules
>
> I'll send each through `forge ingest` (which calls Claude API to classify into 5 sections). Anything you don't want imported? Reply 'skip <name>' or 'all good'."

Wait for their reply. Default to "all good" only if the user explicitly says go.

#### 4b. Run ingest

For each approved file, run:

```bash
cd <workspace>
forge ingest --from <path>
```

(If user has no `ANTHROPIC_API_KEY` and `forge ingest` errors out, fall back to `--no-llm` and tell them "I'll dump everything into workspace.md, you'll split it manually." Wait for OK on this fallback before running it.)

If you (the agent) prefer to do classification yourself instead of calling the API, you may — read the source with Read tool, classify mentally per the schema in `forge/ingest/classifier.py`, write to `<workspace>/sp/section/<name>.md` directly. Do **not** use the Read tool to read source files until the user has consented to import.

After ingest, summarize what landed where:

> "Imported:
>   - `about-me.md` (340 lines from `~/.claude/CLAUDE.md` § About User)
>   - `preferences.md` (180 lines from § Preference)
>   - `workspace.md` (90 lines from § Workspace)
>   - `knowledge-base.md` (60 lines from § Knowledge Base)
>   - `skills.md` (20 lines from § Skills)"

### Step 5 — Show the review screen

```bash
forge review --summary-only
```

**CRITICAL — display behavior**: Claude Code collapses long Bash tool output into `+N lines (ctrl+o to expand)`. The user **will not see** the review panels if you only run the command. You MUST take the stdout and paste it into your **message text** (inside a fenced code block) so it renders inline. Don't paraphrase the panels, don't truncate them — paste the full panel text verbatim. The panels are already structured for human reading; rewriting them defeats the design.

If the user later asks "show diff" or "show the raw diff," run `forge review` (without `--summary-only`) AND again paste the entire output into your message text. Same rule: tool output is invisible until you echo it as a message.

`forge review` is the **primary review surface**, not `forge diff`. It shows in one screen: where the change came from (Origin panel — picks up the ingest event from Step 4 automatically), what it does semantically (filled N TODO placeholders, +/- bullet rules), which agents will read it (CLAUDE.md → Claude Code, AGENTS.md → Codex), and per-section bench.

After the user reads the panels, ask: **"Approve / Reject / Edit a section / See raw diff?"**

- **"show diff" or "raw diff"**: run `forge review` (no `--summary-only`), paste the full output verbatim, including the diff section at the bottom.
- **"edit first"**: tell them which file to edit; they edit; you re-run `forge review` and paste again.
- **"approve"**: jump to Step 7.

(`forge diff` still exists as a thinner command for users who only want the raw diff with no panel context — but skill flows always go through `forge review` because Origin / Affects / Bench are exactly the missing context.)

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

End the onboarding with: "You're set up. Edit `sp/section/<name>.md` when context changes, say 'approve' or '过一下', and I'll run the review flow."

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
forge review --summary-only
```

If `no changes since last approve`: tell user "nothing to review", stop.

Else: **paste the full stdout into your message text inside a fenced code block** — Claude Code collapses long bash output and the user can't see it otherwise. The Origin panel will say `hand edit (no recorded ingest/event)` for typical edit-then-review cycles, which is correct. The Bench panel will flag any section with ≥50% byte change with ⚠ — call that out explicitly if any: "the workspace section grew 76% — sure that's intended?"

If user asks to see raw diff: re-run `forge review` (no `--summary-only`) and again paste the full stdout into your message text.

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

v0.2: workspace IS a git repo (`forge new` git-inits, every `forge approve` = `git commit`). So you don't need to ask the user "should we git commit?" — that already happened. Instead, ask once: "Want me to `git push` to a remote?" Only push if user explicitly says yes. Don't push to main/master without user explicitly naming the branch.

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

- ❌ **Don't auto-import after `forge new`.** Step 3 must end with the user saying "A" / "B" / "import <path>". Reading `~/.claude/CLAUDE.md` or running `forge ingest` before they reply is a trust violation — those are personal files, you don't get to scan them just because the workspace exists.
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
