# forge

> CLI name: `forge`. PyPI package: `context-forge` (the name `forge-core` is taken on PyPI).

Models are commoditizing. Every few months a new release closes the capability gap. The "which model" differentiator is shrinking; **the context you bring to AI** is growing — your workflow, preferences, domain knowledge, judgment calls. That's the part that's actually yours.

But it doesn't behave like an asset right now. Your `CLAUDE.md` has lines you don't remember adding. Switching tools means reconfiguring from scratch. When something goes wrong you can't trace what changed. The content isn't the problem — **nothing manages it**.

`forge` is the minimum viable management layer: a review-gated context compiler.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

Run it in your terminal yourself, or paste it to your agent and let it run.

Then tell your agent (Claude Code / Codex / Cursor / etc.):

> "Use forge to set up a workspace and take over my existing CLAUDE.md / AGENTS.md"

The agent scaffolds the workspace, imports your content, and runs review. You just say ok or reject.

---

## What is it

**`forge`** treats your long-term content as **source files**, and the `CLAUDE.md` / `AGENTS.md` your agent actually reads as **compiled outputs**:

```
long-term content (your source)  ─→  review gate  ─→  compiled outputs (the view your agent reads)
preferences / workspace                              CLAUDE.md
knowledge base / skill                               AGENTS.md
                                                     .cursorrules ...
```

Source and output are explicitly separated. Source is plain markdown you can read directly; outputs are compiled — **never hand-edited**. A review gate sits in between: every source change shows you what changed, which outputs are affected, and how the agent's behavior will shift, before you approve.

The recommended way to use forge is to drive everything through agent conversation: you describe the change, the agent drafts the proposal, compiles, runs the diff. You make the review decisions.

---

## What problem it solves

Treating the same content as an **asset** rather than **scratch** requires three properties at once:

- **Legible** — source is plain markdown, not vectors, embeddings, or LLM-generated black-box summaries. You can open it and read it
- **Explainable** — every line in the compiled output traces back to a section and an approve. `forge changelog` answers "when was this added"
- **Controllable** — changes go through a review gate before reaching runtime. AI cannot bypass you to modify your preferences or identity narrative

Hand-editing `CLAUDE.md` doesn't satisfy any of these. Letting an LLM auto-organize your memory doesn't either — LLM-organized memory drifts toward the base model's average aesthetic, which means the more an LLM organizes for you, the less differentiated you become. Differentiation only comes from **you deciding what to keep and what to drop**.

`forge` provides the minimum structure that makes "you decide" possible: source / gate / compiler / multi-runtime adapters.

---

## What daily use looks like

You updated your work journal and saved a tech article as a web clipping. Tell your agent "check forge":

```
You: check forge

Agent: monitor found 2 changes. Proposal:

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     monitor:  user space/daily/work-log.md (2048 bytes, modified)
  ══════════════════════════════════════════════════════════════════════

    extracted   - Work log update (Project A in test, Project B in research)
    disposition 📦 ARCHIVE
    rationale   Just a trail — the agent doesn't need to read it
    propagation (empty — chain stops at capture; CLAUDE.md untouched)

  ══ ITEM 2 ══════════════════════════════════════════════════════════
     monitor:  capture/web clipping/react-server-components.md
  ══════════════════════════════════════════════════════════════════════

    extracted   - Deep dive into React Server Components architecture
                - RSC vs SSR: fundamental differences
                - Complements existing react-patterns.md (architecture vs practice)
    disposition ✅ APPLY · create rsc.md + index entry
    rationale   Existing KB has no RSC architecture dimension

    propagation
    └─ public knowledge base/topic/tech/frontend/rsc.md     [create]
       └─ context build/sections/knowledge base.md          [index +1 line]
          ├─ CLAUDE.md                                       [recompile]
          └─ AGENTS.md                                       [recompile]

  Distribution: 📦 × 1, ✅ × 1. approve / reject?

You: ok

Agent: approved. CLAUDE.md / AGENTS.md recompiled.
       knowledge base section gains one line:

         + - tech/frontend/rsc.md — RSC architecture deep-dive (complements react-patterns)

       Next time you launch your agent, it will answer RSC questions based on this new entry.
```

The key difference between the two dispositions is the propagation chain:

- **ARCHIVE** — chain stops at capture. The file is saved, but the CLAUDE.md your agent reads doesn't change
- **APPLY** — chain reaches CLAUDE.md / AGENTS.md. The compiled output gains a line; the agent's behavior changes on next launch

Every item makes "does this affect the final compiled output" explicit before you approve.

---

## Who should NOT use this

- **Your `CLAUDE.md` is 5 lines.** Hand-edit. forge is overkill
- **You want AI to auto-organize your memory.** That's `claude-memory-compiler` or similar. forge deliberately keeps the human in the loop
- **You have thousands of micro-facts for retrieval.** That's vector store + RAG, not this tool
- **You want "install and forget."** Every source change goes through review / approve. No skipping

Good fit: **you use multiple AI tools, have 30+ lines of long-term context to manage, and care whether this content is still yours in 5 years.**

---

## Core concepts

```
capture/web clipping/   ─┐
user space/daily/        ├─→ forge monitor detects changes
workspace/project/       │
public knowledge base/  ─┘
         │
         ▼
   forge capture → system/inbox/ → system/pr/proposal.md
         │                              │
         │                              ▼
         │   agent drafts proposal:
         │   items[] → disposition (APPLY/ARCHIVE/COVERED/...)
         │          → propagation tree (which assets change)
         │              │
         ▼              ▼
   you review → approve / reject
         │
         ▼
   context build/sections/ → forge build → CLAUDE.md / AGENTS.md / ...
         │
         ▼
   forge target install → ~/.claude/CLAUDE.md (auto-sync)
```

- **Capture** — raw evidence (web clippings, logs, agent memory). Stored, never modified
- **Inbox** — pending queue before the review pipeline
- **Proposal** — each monitored change is an item; agent classifies (APPLY / ARCHIVE / COVERED / DECIDE / NA / MIXED) with a propagation tree
- **Section** — context build source files, organized by concern (about user / workspace / knowledge base / preference / skill)
- **Output** — compiled artifacts (CLAUDE.md / AGENTS.md). Never hand-edited; auto-regenerated on approve
- **Target** — bind an output to an external path (like `~/.claude/CLAUDE.md`); auto-synced on approve

---

## CLI commands

### Core

```
forge new <path>          # scaffold workspace
forge build               # section → output compilation
forge review              # one-screen impact + diff
forge approve -m "..."    # = git commit + rebuild + sync
forge reject              # revert to last approved
forge changelog           # audit log
forge rollback [hash]     # restore any historical version
```

### Governance (recommended via agent conversation)

```
forge monitor             # scan workspace for changes
forge capture             # capture raw evidence
forge proposal new        # generate schema-aware proposal
forge proposal validate   # validate proposal
forge pr render           # render §0.5 view
forge pr done             # archive PR
forge inbox done          # close inbox item
```

### Target binding & tools

```
forge target install <adapter> --to <path>
forge target list / remove
forge bench snapshot / compare    # structural snapshot diff
forge self-install                # bind forge skill to agent runtime
forge update                      # upgrade CLI
```

---

## Adapters

| Name | Output | Tier |
|---|---|---|
| `claude-code` | `CLAUDE.md` | core |
| `agents-md` | `AGENTS.md` | core |
| `cursor` | `.cursorrules` | contrib |
| `codex-cli` | AGENTS.md variant | contrib |
| `rulesync-bridge` | rulesync input | contrib |

Core adapters load by default; contrib adapters require an explicit `register_adapter(...)` call. A custom adapter is ~20 LoC. See [`docs/adapters-spec.md`](docs/adapters-spec.md).

---

## How to run your own bench

forge has no universal benchmark, and shouldn't. Your context, your tasks, your usage patterns are different from anyone else's — **a meaningful bench has to be your own**. `forge bench snapshot / compare` only does structural snapshots (did compile preserve content); it's not a behavioral eval.

Minimal recipe for a behavioral eval:

1. **Pick 3–5 tasks** that reflect questions you actually ask your agent, covering different sections (about-user / workspace / preference / etc.)
2. **Prepare two CLAUDE.md files**: baseline (M — hand-rolled or previous version) and candidate (F — current forge output)
3. **Run each task twice**: agent reads only M, then only F, with no tool access, answering purely from the file
4. **Judge**: blind-compare each pair (human or a third agent), record win/tie/loss

Sample tasks (replace with your own):

```
- identity-summary:    "Summarize in 3 sentences who I am, what I'm working on, and my core challenge"
- workspace-awareness: "List my 3 most important active projects or topics"
- grounding-rule:      "If I ask about a product's release date, what should you do first?"
```

Full setup template in [`docs/eval-report.en.md`](docs/eval-report.en.md). Swap in your own tasks and your two CLAUDE.md versions to reuse it.

---

## Current status

Alpha. Still in dogfood — the author is the only real user. Schema, CLI surface, and directory layout may break between versions. Docs and implementation may drift; when in conflict, code is the source of truth.

---

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

## License

MIT. See [`LICENSE`](LICENSE).

---

*中文版：[`README.md`](README.md)。*
