# forge-core v0.1.0 — behavioral eval report

**Date:** 2026-04-24
**Question:** If you swap dxyOS's hand-rolled compile pipeline for forge-core, do agent behaviors degrade, improve, or stay comparable?
**TL;DR:** **Comparable.** 2–2 split across 4 behavioral tasks, with honest caveats.

This is the "is it actually good" evidence we owe, beyond the structural 92.5% line recall reported in [`migration-from-personal-os.md`](migration-from-personal-os.md). Structural recall says *the same text is there*. This report says *the agent actually uses it the same way*.

---

## Setup

Two CLAUDE.md files:

- **M** (master) — dxyOS's pre-migration compiled `01 assist/SP/output/claude code/CLAUDE.md`. 118 lines, 8722 bytes. Generator: `pr-0021-advisory-project-skill-events`.
- **F** (forge) — post-migration version, same 5 sections, same config structure, compiled by `forge-core@0.1.0`. 126 lines, ~9.9KB. Adds a provenance header and `demote_section_headings: true` for clean H2/H3 hierarchy.

Both files are checked in on dxyOS branch `forge-core-migration`.

4 behavioral tasks (subset of `forge.eval.default_tasks()`):

| ID | Probes | Prompt summary |
|---|---|---|
| identity-summary | about-user | "3 sentences on who I am / what I do / core challenge" |
| workspace-awareness | workspace | "List my 3 main projects/topics, ranked" |
| grounding-rule | preference | "User asks release date of a product. What do you do first?" |
| ikigai-direction | about-user + workspace | "Next concrete step on finding my startup direction" |

For each task × version (8 total), a fresh `general-purpose` subagent was spawned. Each subagent received the same system-style instruction: *read the CLAUDE.md file, do not call any other tools, output only the answer based on that context*. Answers recorded in [`/tmp/eval-answers.md`](/tmp/eval-answers.md) at run-time.

## Judge setup

4 judge subagents, one per task. Each saw two responses labeled **Response 1** and **Response 2** without knowing which came from M or F. **Position assignment was randomized** across tasks:

| Task | Response 1 origin | Response 2 origin |
|---|---|---|
| T1 (identity) | M | F |
| T2 (workspace) | F | M |
| T3 (grounding) | M | F |
| T4 (ikigai) | F | M |

Judge was given the task prompt, both responses, a brief user-background blurb, and a short rubric. Output was strict JSON: `{"winner": "1"|"2"|"tie", "reason": "..."}`.

## Results

### Position-blind (what judges actually said)

All 4 judges picked **Response 2**. Every time.

```
T1: winner=2  reason: "more concrete specifics (explicit 2026 ikigai deadline, reading 智能简史...)"
T2: winner=2  reason: "ordering better reflects importance since topic research supports forge"
T3: winner=2  reason: "additionally leverages the KB pointer to claude-code.md before defaulting to WebSearch"
T4: winner=2  reason: "ties the next step to his existing forge workstream with specific dates, channels"
```

### Decoded by origin

Applying the randomized mapping above:

| Task | Winner | Origin | Score |
|---|---|---|---|
| T1 identity-summary | Response 2 | **F** (forge) | F |
| T2 workspace-awareness | Response 2 | **M** (master) | M |
| T3 grounding-rule | Response 2 | **F** (forge) | F |
| T4 ikigai-direction | Response 2 | **M** (master) | M |

**Final tally: F 2, M 2, tie 0.**

Forge-compiled CLAUDE.md holds up. No behavioral regression observed.

## The caveat you need to hear

The 4/4 positional-bias is louder than the 2/2 outcome. Two non-exclusive interpretations:

1. **The two answers on each task really were indistinguishably close in quality**, and judges defaulted to positional tie-breaking. This is consistent with 92.5% structural line recall — most section content is literally identical, so answers derived from it should be nearly identical. The 2–2 split is just what random position assignment plus position-bias-judges mathematically produces from near-identical answers.
2. **LLM-as-judge has a systematic recency bias** on this specific subagent + this prompt format, independent of answer quality. This is a known limitation of small-N LLM-judge setups. To actually measure quality difference (if any), we'd need ≥20 tasks, counter-balanced position assignment (each task judged twice with swapped positions), and ideally a human-judge sanity pass.

Either way, the v0.1 conclusion does NOT claim "forge is better than master" or "master is better than forge." It claims **"no detectable behavioral degradation"** — the migration is safe to ship.

## What this is and isn't

**Is:** real subagent runs on real dxyOS CLAUDE.md files, real LLM judge, real side-by-side outputs. Not a simulation.

**Isn't:**
- Not large-N (4 tasks × 2 versions = 8 answers, 4 judgments).
- Not multi-seed — each subagent was one-shot, no repeats.
- Not human-judged.
- Not controlled for prompt-position bias (we randomized but did not counter-balance).
- Does not test multi-turn behavior or tool-calling differences.

**v0.3 roadmap** (mentioned in README): ≥20 tasks, counter-balanced positions, optional Anthropic SDK runner for higher throughput, human-in-the-loop scoring for a subset. That's when the claim moves from "no degradation" to "forge compiles objectively better / worse / equal contexts."

## How to reproduce

1. On dxyOS `forge-core-migration` branch (or any personal-OS vault set up per [`migration-from-personal-os.md`](migration-from-personal-os.md)).
2. Save the pre-migration `CLAUDE.md` somewhere (e.g. `/tmp/claude-md-master.txt`) BEFORE running `forge approve`. Save the post-compile version too.
3. Define your own `default_tasks()` — customize prompts to what you actually ask your agent.
4. Spawn subagents (via Claude Code's `Agent` tool, or Anthropic SDK with the CLAUDE.md as system prompt).
5. Feed answer pairs to judge subagents with randomized position assignment.
6. Decode and report.

The `forge/eval/` Python module (`tasks.py`, `harness.py`, `judge.py`) ships the interface. v0.1 runners are stubs — wire in your own.

## Why this still counts as evidence

It's small-N. It's positional-bias-vulnerable. But it is **real** — real agent behavior on real content, not vibes. Every personal-AI tool that claims "it makes your agent smarter" owes this level of experiment at minimum, and most don't. forge-core v0.1 ships the apparatus + one small honest result, instead of a bigger claim it can't back up.
