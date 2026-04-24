# Why I built a review-gated context compiler (and why `rulesync` wasn't enough)

*Draft — not yet published.*

---

## The thing nobody is building

In 2026 the agent-tooling landscape has three rich layers and one missing layer.

**Layer 1 — rules sync.** Tools like `rulesync` and `ai-rules-sync` take your agent instructions and mirror them across Cursor, Claude Code, Copilot, Codex, Gemini, Windsurf. One source of truth, eight generated config files. Great.

**Layer 2 — memory compilers.** Tools like `claude-memory-compiler` hook into your sessions, extract "key decisions," and use an LLM to organize the results into structured memory articles. Also great.

**Layer 3 — prompt compilers.** DSPy and BAML take your prompt logic and compile it into optimized call patterns. These operate at a different layer — they compile *programs*, not *content*.

The missing layer is the one between them: **a review-gated compiler for your long-term content.**

I don't want another tool that auto-writes to my memory file. I don't want another sync tool that shoves whatever I typed into eight runtimes. I want the thing a build system gives you for code: canonical sources I edit, compiled artifacts I never edit, and a gate between the two that tells me *what's about to change* before I ship it.

That's `forge-core`.

## The three problems

1. **Long-term content and runtime context are mixed together.** Your notes, preferences, learned rules, generated `CLAUDE.md`, and the actual conversation scratch space all sit in the same pile. There's no clear "this is truth" vs "this is a derived artifact." When something in `CLAUDE.md` looks wrong, you can't trace it back to a specific source.

2. **Changes enter the system without traceability.** An agent edits your memory file during a session. Who approved it? Why? Can you roll it back? For most tools, the answer is "no — that's now your memory."

3. **You can't tell if the system actually got better.** Most "personal OS" workflows stop at "feels nicer now." There is no bench, no before/after, no structural check. You made a change — did it actually shrink the bloat, add the preference, rebalance the sections?

Each of these is solvable individually. None of the existing tools solve all three.

## How forge-core works

Three directories, three concepts:

```
sp/
  section/          # canonical source: one concern per markdown file
    about-me.md
    preferences.md
    workspace.md
    skills.md
  config/           # recipe: for target X, include these sections
    personal.md     # → CLAUDE.md
    codex.md        # → AGENTS.md
.forge/
  approved/         # snapshot of last-approved sp/
  output/           # compiled artifacts (CLAUDE.md, AGENTS.md, …)
  changelog.md      # append-only audit
  manifest.json     # approved hash, timestamps
```

The loop:

```bash
# you edit
$ vim sp/section/preferences.md

# you see what would change
$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - Ground external facts in live sources.
 - No emojis unless explicitly requested.
+
+- When touching shared config, always PR first.

======== output diff ========
--- personal ---
+++ proposed/personal
@@ -19,6 +19,8 @@
 - No emojis unless explicitly requested.
 
+- When touching shared config, always PR first.
+

# you commit (or discard)
$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .forge/output/CLAUDE.md
  wrote .forge/output/AGENTS.md
```

That's the entire core concept: **every change to the canonical source surfaces both as a source diff and a compiled-output diff, before it ships**. If you don't like what it would do to `CLAUDE.md`, `forge reject` puts you back to the last approved state.

## Why the gate matters more than the compiler

The compiler is straightforward. Sections are markdown with frontmatter. Configs are lists of section names. Adapters render ordered sections into target-specific format. Anyone could write that in an afternoon. You might correctly point out that `rulesync` already does the interesting part of the compilation for rules.

**The gate is the thing.** Without it, forge-core is just another markdown templater. With it, forge-core becomes the thing that prevents your agent context from being silently corrupted by one bad edit, and lets you trace every line of the compiled output back to a specific approved source snapshot.

This is the same reason git matters and rsync doesn't quite. Both move bytes between states. Only one of them has a notion of "this change was reviewed and committed" with a full history you can walk backwards.

## The bench is also non-negotiable — but let me be honest about what it does

The first question anyone asks when they see a personal-AI system is: **does it actually work?** Most answers are vibes. "It feels better now." "I think the agent is sharper."

`forge-core` ships a structural bench in v0.1:

```bash
$ forge bench snapshot before
$ # (make some changes to sp/, approve them)
$ forge bench snapshot after
$ forge bench compare before after
compare before -> after

# outputs
  AGENTS.md: 952B -> 1023B (+71B, +2L)
  CLAUDE.md: 1212B -> 1283B (+71B, +2L)

# section size deltas
  skills: 203B -> 274B (+71B)
```

**Be clear about what this is and isn't.** The v0.1 bench measures *structural* deltas — byte count, line count, section size, added/removed sections. It does **not** measure "is the agent actually smarter with the new context." It cannot. That claim requires real agent runs against a fixed question set, with a grading harness, which is v0.3 on the roadmap.

I'm shipping the weak version on purpose. I'd rather ship a small bench I can point at and say "this is what it does, this is what it doesn't" than ship a fake LLM eval that's really just vibes dressed up. Even the structural version catches the most common failure mode: *I made a change and didn't notice it doubled the context size.* That's worth its weight in v0.1. Real eval in v0.3.

This is also why the tool is called `forge-core` and not `forge-eval` or `forge-bench-pro`. The core value prop in v0.1 is the gate + the compile contract. The bench is there to make sure future eval work has somewhere clean to plug in.

## What about rulesync? claude-memory-compiler? skills-to-agents?

Each of those solves a slice of the problem and solves it well. `forge-core` doesn't compete with them — it sits at a layer none of them own.

| Tool                    | What it owns                                  | What it doesn't                              |
|-------------------------|------------------------------------------------|----------------------------------------------|
| rulesync, ai-rules-sync | Format translation across 8+ runtimes         | No review gate, no canonical source layer    |
| claude-memory-compiler  | Auto-extract + LLM-organize session memory    | No human checkpoint, no multi-runtime target |
| agents-md-generator     | Generate AGENTS.md from codebase              | Source is code, not long-term content        |
| skills-to-agents        | Compile SKILL.md → AGENTS.md                  | Skills only, no identity / preferences / etc. |

Nothing stops you from combining them. A future forge-core watcher could consume output from claude-memory-compiler as proposed input (requiring review before it enters canonical source). A future adapter could emit Cursor `.cursorrules`. That's the point of a clean layer split.

## What's in v0.1 and what isn't

**Ships now:** compiler core, Claude Code + AGENTS.md adapters, review gate (init/diff/approve/reject/status/build), structural bench, 29 unit tests, a working dxyOS validation example.

**Doesn't ship yet:**
- No watcher / inbox / auto-ingest. You edit `sp/section/` by hand. (v0.2)
- No LLM-based eval. Bench is structural only. (v0.3)
- No Mem0 / Letta / Zep adapters. Canonical source is markdown files. (v0.4, symptom-driven)
- No CI integration, no hosted version, no web UI.

This is deliberate. The whole thesis is that the hard problem is the gate + the split + the bench contract — not the compilation itself. v0.1 ships the thesis minimally and lets me (and whoever else finds it interesting) pressure-test the concept before adding surface.

## What I want from you

If this resonates — if you've felt the "my CLAUDE.md got silently corrupted" or "I have no idea if my last edit helped or hurt" pain — try it, push back on it, tell me where the model breaks. Issues and PRs welcome. Especially:

- Second target adapter that isn't Claude-ecosystem (Cursor, Aider, something).
- Better diff UX (the current text diff is fine but not polished).
- Real-world bench scenarios where structural comparison is genuinely useful vs. where it falls short.

Repo: *(link pending — not yet pushed to public GitHub)*.

---

*Built by dxy, 2026-04-24. Status: v0.1.0 alpha.*
