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
```

After this completes, **briefly** describe the structure (don't dump full content):

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
ls .forge/output/
```

Show:

> "Same source compiled into two runtime views:
>   - `.forge/output/CLAUDE.md` — what Claude Code reads
>   - `.forge/output/AGENTS.md` — what Codex / OpenCode / etc. read
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
cat .forge/changelog.md
```

> "This changelog is your audit trail. In 3 months, when you wonder 'when did I add the no-emoji rule?', `grep .forge/changelog.md`. **That's the provenance point.**"

### Step 8 — Tell user how to wire to real Claude Code

**Do not auto-wire.** Tell user explicitly:

> "Your forge workspace's compiled output lives at `<workspace>/.forge/output/CLAUDE.md`. But Claude Code reads `~/.claude/CLAUDE.md`. To bridge:
>
> Option A (one-time copy each approve):
>   `cp <workspace>/.forge/output/CLAUDE.md ~/.claude/CLAUDE.md`
>
> Option B (symlink, recommended — auto-updates on every forge approve):
>   `ln -sf <workspace>/.forge/output/CLAUDE.md ~/.claude/CLAUDE.md`
>
> I'm not running this for you — `~/.claude/CLAUDE.md` is your global config and overwriting it without your explicit OK feels wrong. Run whichever you prefer."

End the onboarding with: "You're set up. From here on, edit `sp/section/<name>.md` whenever your context changes, then say 'approve' and I'll run the review flow for you."

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

Show approved hash and `wrote` lines.

If workspace appears to be a vault (heuristic: workspace path is `~/dxy_OS` or contains `02 user/`), remind: "Run `cp .forge/output/CLAUDE.md ~/.claude/CLAUDE.md` to refresh global Claude Code (or use a symlink — see onboarding §8)."

If workspace is a git repo: ask once "Want me to also `git add` and commit `sp/` + `.forge/changelog.md`?" Don't push without explicit asking.

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
- ❌ Don't auto-symlink `~/.claude/CLAUDE.md` — show the command, user runs it
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
