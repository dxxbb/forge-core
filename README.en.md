# forge

> CLI name: `forge`. PyPI package: `context-forge` (the name `forge-core` is taken on PyPI).

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

This installs the CLI and binds the forge skill into Claude Code. You can run it yourself, or paste it to your agent and let it run.

Then tell Claude in Claude Code:

> "Set up a forge workspace, import my existing CLAUDE.md"

The agent scaffolds the workspace, imports your content, and runs review. You just say ok or reject.

---

## What is it

**`forge`** is a review-gated context compiler: your long-term content (preferences, project state, knowledge base, skills) is the source; `CLAUDE.md` / `AGENTS.md` are compiled artifacts. There's a review gate in between — see what changed, who's affected, how big, then approve or reject.

The recommended way to use forge is inside Claude Code. The agent drives the entire workflow; you make the review decisions.

---

## What daily use looks like

You updated your work journal and saved a tech article as a web clipping. Tell Claude "check forge":

```
You: check forge

Claude: monitor found 2 changes. Proposal:

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     monitor:  user space/daily/work-log.md (2048 bytes, modified)
  ══════════════════════════════════════════════════════════════════════

    extracted   - Work log update
                - Project A entering test phase
                - Project B in research
    disposition 📦 ARCHIVE · rolling work log, no context build propagation
    rationale   Personal work journal — capture preserved as audit trail

  ══ ITEM 2 ══════════════════════════════════════════════════════════
     monitor:  capture/web clipping/react-server-components.md
  ══════════════════════════════════════════════════════════════════════

    extracted   - Deep dive into React Server Components architecture
                - RSC vs SSR: fundamental differences
                - Complements existing react-patterns.md (architecture vs practice)
    disposition ✅ APPLY · create rsc.md + cross-link react-patterns
    rationale   Existing KB has no RSC architecture dimension; this fills the gap

    propagation
    └─ public knowledge base/topic/tech/frontend/rsc.md
       ├─ modification: create topic page, distill article
       └─ context build/sections/knowledge base.md
          ├─ modification: append rsc entry to index
          └─ (terminal)

  Distribution: 📦 × 1, ✅ × 1. approve / reject?

You: ok

Claude: approved. Log archived, rsc.md created,
       knowledge base section updated, CLAUDE.md and AGENTS.md recompiled.
```

One PR handles both changes:

- **ARCHIVE** — the log is a work journal; captured for audit trail but doesn't affect agent context
- **APPLY** — the web clipping has new knowledge; distilled into the KB, propagation tree traces the impact chain all the way to compiled output

You said two words. The agent handled monitor → capture → proposal → build → commit.

---

## The problem it solves

You told your agent "use Python, not TypeScript" last week. Today it gives you TypeScript. You open `CLAUDE.md` — that preference line is gone.

You didn't commit that file. `git blame` shows nothing. The agent's memory isn't broken — it's unmanaged.

`forge` adds the missing management layer:

- **Source and compiled output are separate** — you edit `context build/sections/preference.md`; CLAUDE.md and AGENTS.md are compiled, never hand-edited
- **Changes go through a review gate** — nothing takes effect until you approve
- **One source, multiple runtimes** — the same preferences compile to both Claude Code and Codex; switch tools without rewriting
- **Every change has a hash and audit trail** — `forge changelog` tells you when any rule was added

---

## Who should NOT use this

- **Your `CLAUDE.md` is 5 lines.** Hand-edit. Done.
- **You want AI to auto-organize your memory.** Use `claude-memory-compiler`. forge deliberately keeps humans in the loop.
- **You have thousands of micro-facts for retrieval.** That's vector store + RAG.
- **You want "install and forget."** forge requires review / approve on every change.

Good fit: **multiple AI tools, 30+ lines of long-term context, you care about change traceability.**

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
         │         ┌────────────────────┘
         │         ▼
         │   agent drafts proposal:
         │   items[] → disposition (APPLY/ARCHIVE/COVERED)
         │          → propagation tree (which assets change)
         │         │
         ▼         ▼
   you review → approve / reject
         │
         ▼
   context build/sections/ → forge build → CLAUDE.md + AGENTS.md
         │
         ▼
   forge target install → ~/.claude/CLAUDE.md (auto-sync)
```

- **Capture** — raw evidence (web clippings, logs, agent memory). Store only, never modified
- **Proposal** — each monitored change is an item; agent classifies as APPLY / ARCHIVE / COVERED / DECIDE, with a propagation tree showing the impact chain
- **Section** — context build source files, one per concern (about user / workspace / knowledge base / preference / skill)
- **Output** — compiled artifacts (CLAUDE.md / AGENTS.md). Never hand-edited; auto-regenerated on approve
- **Target** — bind an output to an external path; auto-synced on approve

---

## CLI commands

### Core

```
forge new <path>                # scaffold workspace
forge init                      # initialize approved baseline
forge build                     # section → output compilation
forge review                    # one-screen impact + diff
forge approve -m "message"      # = git commit + rebuild + sync
forge reject                    # revert to last approved
forge changelog                 # audit log
forge rollback [hash]           # restore any historical version
```

### Governance (recommended via agent conversation)

```
forge monitor                   # scan workspace for changes
forge capture                   # capture raw evidence
forge proposal new              # generate schema-aware proposal
forge proposal validate         # validate proposal
forge pr render                 # render §0.5 view
forge pr done                   # archive PR
forge inbox done                # close inbox item
forge synthesize-clipping       # web clipping → KB topic synthesis
```

### Target binding & tools

```
forge target install <adapter> --to <path>
forge target list / remove
forge bench snapshot / compare
forge self-install              # bind skill to agent runtime
forge update                    # upgrade CLI
```

---

## Adapters

| Name | Output | Description |
|---|---|---|
| `claude-code` | `CLAUDE.md` | Claude Code |
| `agents-md` | `AGENTS.md` | Cross-tool standard |
| `cursor` | `.cursorrules` | Cursor |
| `codex-cli` | AGENTS.md variant | OpenAI Codex |
| `rulesync-bridge` | rulesync input | Bridge to 20+ tools |

Custom adapter is ~20 LoC. See [adapters-spec.md](docs/adapters-spec.md).

---

## Validation

- **Unit tests**: ~490 / 0 failures (`pytest -q`)
- **v0.1.0 behavioral eval**: 4-task A/B vs hand-rolled `CLAUDE.md` tied 2:2; structural preservation 92.5%. See [`docs/eval-report.en.md`](docs/eval-report.en.md). Not re-run on later versions.

---

## Development

```bash
pip install -e '.[dev]'
pytest -q                       # 488 tests, ~27s
```

## License

MIT. See [`LICENSE`](LICENSE).

---

*中文版：[`README.md`](README.md)。*
