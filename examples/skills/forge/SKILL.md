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
forge init
```

`forge new` lays out files; `forge init` creates `.forge/` (the approved baseline + first compiled output). Without `init`, the next `forge diff` errors out with "not initialized." Run both before moving on.

After both complete, **briefly** describe the structure (don't dump full content):

> "Scaffolded:
>   - `sp/section/` — 5 source sections (about-me, preferences, workspace, knowledge-base, skills) + 1 wrapper. These are markdown files you own.
>   - `sp/config/` — 2 configs: one outputs `CLAUDE.md` (Claude Code), one outputs `AGENTS.md` (Codex / OpenCode / etc.). Same 5 sections, two view formats.
>   - `.forge/` — runtime state (changelog, approved snapshot, compiled outputs). Gitignored.
>
> Each section has a TODO placeholder right now. We'll fill them by importing your existing context next."

### Step 3 — Detect existing context

Check for these files (in order):
- `~/.claude/CLAUDE.md`
- `<cwd>/CLAUDE.md` (project-level if user is in a repo)
- `~/.cursor/rules/` (or `.cursor/rules/` in cwd)
- `<workspace>/AGENTS.md` and similar

Tell the user what you found:

> "Found:
>   - `~/.claude/CLAUDE.md` (8.2 KB) — your global Claude Code instructions
>   - `./CLAUDE.md` (1.4 KB) — this project's CLAUDE.md
>   - No .cursorrules
>
> I'll import each into the workspace. The classification (which paragraph goes to which section) is automatic — if anything lands wrong you can edit it before approving."

### Step 4 — Ingest

For each found file, run:

```bash
cd <workspace>
forge ingest --from <path>
```

(If user has no `ANTHROPIC_API_KEY` and `forge ingest` errors out, fall back to `--no-llm` and tell user "I'll dump everything into one section, you'll need to split manually after.")

If you (the agent) prefer to do classification yourself instead of calling the API via `forge ingest`, that's fine — read the source file with the Read tool, classify into the 5 sections in your head following the schema in `forge/ingest/classifier.py`, write to `<workspace>/sp/section/<name>.md` directly. The user just needs the result; doesn't matter who classified.

After ingest, briefly summarize what landed where:

> "Imported:
>   - `about-me.md` (340 lines from `~/.claude/CLAUDE.md` § About User)
>   - `preferences.md` (180 lines from § Preference)
>   - `workspace.md` (90 lines from § Workspace)
>   - `knowledge-base.md` (60 lines from § Knowledge Base)
>   - `skills.md` (20 lines from § Skills)"

### Step 5 — Show diff

```bash
forge diff
```

The output is long. Don't dump verbatim. Instead:

1. Run the command and capture output.
2. Summarize: "X sections changed. Y bytes total. The biggest changes are in `<section>` (...)."
3. Ask: **"Want to see the full source/output diff before deciding? Or jump to approve?"**
4. If "show diff": echo the full output.
5. If "let me edit first": tell them which file to edit; they edit; you re-run `forge diff`.

### Step 6 — Cross-runtime: show one source, two outputs

Before approve, demo the cross-runtime point. Run:

```bash
forge build
ls output/
```

Show:

> "Same source compiled into two runtime views:
>   - `output/CLAUDE.md` — what Claude Code reads
>   - `output/AGENTS.md` — what Codex / OpenCode / etc. read
>
> If you change `sp/section/preferences.md`, both outputs update on the next approve. **You're not maintaining two parallel files.** That's the cross-runtime point of forge."

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

Show output. Then:

```bash
cat CHANGELOG.md
```

> "This changelog is your audit trail. In 3 months, when you wonder 'when did I add the no-emoji rule?', `grep CHANGELOG.md`. **That's the provenance point.** It lives at the workspace root so PRs reviewing your context show this changelog inline."

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
forge diff
```

If `no changes since last approve`: tell user "nothing to review", stop.

Else: see Onboarding §Step 5 for handling.

### Step R4 — Suggest message

Read source diff, propose a short imperative-mood message (≤ 60 chars). Examples:

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

If workspace is a git repo: ask once "Want me to also `git add` and commit `sp/`, `output/`, and `CHANGELOG.md`?" Don't push without explicit asking.

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
