---
name: forge
version: 0.1.0
description: "Review-gated context compile flow for forge-core. Triggers when the user wants to inspect, approve, or reject changes to their `sp/section/` files (the long-term AI context source). Common phrases: 'approve my changes', 'review my context', 'forge diff', 'forge approve', '过一下我改的 section', '审一下', 'discard the change'. Also auto-invoke if the agent has just edited any file under `sp/section/` during this conversation, before the user's next significant ask."
metadata:
  requires:
    bins: ["forge"]
  cliHelp: "forge --help"
---

# forge — review-gated context compile

This skill drives the `forge-core` review-gate workflow: every change to a user's long-term AI context (`sp/section/*.md`) goes through `diff → approve / reject` before it reaches `agent` runtime files like `CLAUDE.md` / `AGENTS.md`.

User just needs to say what they want in plain language. The skill picks the right CLI commands.

## Step 0 — Locate workspace

A forge workspace is any directory containing `sp/section/` (and usually `.forge/` after first init).

1. Try cwd. If `sp/section/` exists, you're in.
2. Walk up parents looking for `sp/section/`.
3. If still not found, ask: **"Where's your forge workspace?"** Common answers: `~/dxy_OS`, `/path/to/my-context`, "I haven't made one yet" → suggest `forge new <path>` then stop.

**Do NOT modify files in any forge workspace from outside it.** Always `cd` into the workspace before running commands.

## Step 1 — Health check

Always run this first; it catches broken state cheaply.

```bash
forge doctor
```

- 0 errors: continue.
- Errors: show them, stop, ask user to fix (or offer to fix together — only edit `sp/config/*.md` after explicit approval).
- Warnings only: continue but mention them once.

## Step 2 — Show diff

```bash
forge diff
```

If output is `no changes since last approve`: tell user "nothing to review" and stop.

Else:
- If diff is **≤ 80 lines**: show the full output verbatim.
- If diff is **> 80 lines**: first show a one-paragraph summary (which sections changed, +/- line counts per section), then ask: **"Show full diff? (y / no, just go to decision)"**. On `y`: dump full output.

## Step 3 — Suggest commit message

Read the source diff. Propose **one short message** (≤ 60 chars, imperative mood) that summarizes the change. Examples:

| Diff content | Suggested message |
|---|---|
| Added a "no emoji" rule to `preferences.md` | `add no-emoji preference` |
| Updated workspace section's project list | `update workspace projects` |
| New `_preface.md` wrapper section | `add preface wrapper` |
| Removed an obsolete preference | `remove stale Python-3.7 note` |

If you can't summarize confidently, propose `update <section name>` and tell the user "you might want to override this".

## Step 4 — Decision prompt

Present three options clearly:

```
1. ✅ Approve with message: "<suggested>"   (or override the message)
2. ❌ Reject — discard all sp/ changes
3. ⏸  Wait — leave changes uncommitted, do nothing now
```

Wait for user choice. Don't pick for them.

If user types something other than 1/2/3 (e.g. "approve but use my own message: foo"), parse intent and confirm before acting. **Never auto-approve.**

## Step 5 — Execute

### Approve

```bash
forge approve -m "<final message>"
```

After success:
1. Show the approved hash and "wrote" lines from the output.
2. **If the workspace is a vault** (heuristic: `~/.claude/CLAUDE.md` is auto-generated from this workspace; check `~/dxy_OS` specifically, or look for a `README.md` that mentions `forge-core` as compile pipeline):
   - Mention sync: `cp <workspace>/.forge/output/CLAUDE.md ~/.claude/CLAUDE.md` (or skip if symlinked).
3. **If the workspace is a git repo** AND user hasn't said anything about git: ask once "Want me to also `git add` and commit `sp/` + `.forge/changelog.md`?" Don't push without explicit asking.

### Reject

`forge reject` prompts y/N. Pipe `yes |` to auto-confirm only if user just confirmed in chat.

```bash
yes | forge reject
```

Show the result. Mention that working-tree `sp/` is now back to last-approved state.

### Wait

Do nothing. Exit cleanly, telling user "leaving sp/ as-is — run `forge approve` or `forge reject` whenever you're ready."

## Don'ts

- ❌ Don't auto-approve without showing diff (Step 2 must run first)
- ❌ Don't run `forge approve` if `forge doctor` returned errors
- ❌ Don't `git push` without explicit user request
- ❌ Don't edit `02 user/**` or `06 system/**` in a dxyOS-style vault — those have separate write rules
- ❌ Don't propose changes to `sp/config/master.md` schema unless user asked

## Auto-invoke heuristic

If during this conversation the agent (you) has just used Edit/Write on any file matching `sp/section/*.md`, **after the action returns**, proactively run Step 1-2 (doctor + diff) and present the decision prompt. Don't wait for the user to explicitly say "approve". They'll often expect the review to happen automatically once they see "Edit succeeded".

Exception: if you're in the middle of a longer multi-edit task (e.g. user said "rewrite my whole preferences file"), wait until that task is logically complete before invoking review.

## Examples of the full flow

### User: "approve my changes"

```
You: [run forge doctor]
     0 errors.
     [run forge diff]
     Source diff: 1 file changed in sp/section/preferences.md, +2 lines.
     Output: codex and personal CLAUDE.md both pick up "+- 改公共配置前先开 PR" line.
     Suggested message: "add shared-config PR rule"
     Approve with this message? Or 2) reject, 3) wait?

User: 1

You: [run forge approve -m "add shared-config PR rule"]
     Approved e84d1b65ceb4. Wrote AGENTS.md, CLAUDE.md.
     This workspace looks like ~/dxy_OS — remember to refresh ~/.claude/CLAUDE.md
     (or use a symlink: ln -sf ~/dxy_OS/.forge/output/CLAUDE.md ~/.claude/CLAUDE.md).
```

### User: "我改了 preference，过一下"

Same flow, replies in Chinese. The skill content is bilingual-aware — match the user's language.

### Auto-invoke after agent Edit

Agent just used Edit on `sp/section/about-me.md` per user's earlier request "把我的工作改成独立开发"。After the Edit returns:

```
You: 改完了。我看了下整体 diff:
     [diff summary]
     建议 commit message: "update about-me — switch to independent"
     1) approve  2) reject  3) wait
```

User picks → proceed.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `forge: command not found` | not installed in this Python env | `pip install -e ~/workspace/projects/forge-core` |
| `forge not initialized at <path>` | first-time use of this workspace | `forge init` |
| `unknown section X` from doctor | config references missing section | edit `sp/config/master.md` to remove or add the section |
| `output_frontmatter must be a mapping` | YAML typo | open the config file, fix YAML |
| `forge diff` shows `no changes` but user just edited | edited a file outside `sp/section/` (e.g. `sp/config/`)  | check which file — config changes also count, but might need re-init if structure changed |
