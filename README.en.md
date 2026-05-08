# forge

> CLI name: `forge`. PyPI package: `context-forge` (the name `forge-core` is taken on PyPI).

**`forge`** is a review-gated context compiler: your long-term content (preferences, project state, knowledge base, skills) is the source; `CLAUDE.md` / `AGENTS.md` are compiled artifacts. There's a review gate in between — see what changed, who's affected, how big, then approve or reject.

The recommended way to use forge is inside Claude Code. The agent drives the entire workflow; you make the review decisions.

---

## Get started

In Claude Code, say:

> "Install forge and set up a workspace for me"

The agent will install the CLI, scaffold the workspace, import your existing `CLAUDE.md`, classify it into sections, and run review. You just say ok or reject.

<details>
<summary>Manual install</summary>

```bash
pipx install git+https://github.com/dxxbb/forge-core.git
forge self-install
```

</details>

---

## What daily use looks like

You saved a web clipping about AI compute. A couple days later you tell Claude "check forge" — it scans the workspace, finds the unprocessed clipping, compares it against your existing knowledge base, and drafts a proposal:

```
You: check forge

Claude: monitor found 1 new web clipping. Let me triage it.

  The article's thesis (TSMC 2026 roadmap + AI as structural shift,
  not hype) relates to ai-policy.md but takes a different angle.
  Recommend creating a new ai-compute.md topic page. Proposal:

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     monitor:  capture/web clipping/tsmc-report.md
  ══════════════════════════════════════════════════════════════════════

    extracted   - TSMC 2026 report: AI chip industrial structure shift
                - Advanced packaging roadmap + semiconductor supercycle
                - Overlaps ai-policy.md but different angle (industrial vs geopolitical)
    disposition ✅ APPLY · create ai-compute.md + cross-link ai-policy
    rationale   Existing KB has no compute-industrial dimension; this fills the gap

    propagation
    └─ b: public knowledge base/topic/tech/ai/compute/ai-compute.md
       ├─ modification: create topic page, distill TSMC report
       └─ b1: context build/sections/knowledge base.md
          ├─ modification: append ai-compute entry to index
          └─ (terminal)

  approve / reject?

You: ok

Claude: approved. ai-compute.md created, knowledge base section updated,
       CLAUDE.md and AGENTS.md recompiled.
```

What happened here:

1. **Agent discovered the change** — `forge monitor` found the new clipping; you didn't have to remember
2. **Compared against existing assets** — didn't blindly insert; classified as APPLY / COVERED / ARCHIVE
3. **Propagation tree traced the impact chain** — clipping → KB asset → context build section → compiled output, every step auditable
4. **You made one decision** — ok or reject. The agent handled capture, proposal, build, and commit

A lighter scenario — you updated your work journal, forge detects it but determines it doesn't affect agent context:

```
You: review this

Claude: monitor detected memo2026Q2.md changed.

  ══ ITEM 1 ══════════════════════════════════════════════════════════
     monitor:  user space/daily/memo2026Q2.md (3264 bytes, modified)
  ══════════════════════════════════════════════════════════════════════

    extracted   - Q2 work log update (20260508)
                - forge: preparing the post
                - watermark: restarting research
    disposition 📦 ARCHIVE · rolling work log, no context build propagation
    rationale   Personal work journal — capture preserved as audit trail

  approve / reject?

You: ok

Claude: approved. Capture archived, no context build changes.
```

**ARCHIVE doesn't mean delete** — raw evidence stays in `capture/` permanently. It just means this content doesn't need to propagate to agent context.

---

## The problem it solves

You told your agent "use Python, not TypeScript" last week. Today it gives you TypeScript. You open `CLAUDE.md` — that preference line is gone.

You didn't commit that file. `git blame` shows nothing. The agent's memory isn't broken — it's unmanaged.

`forge` adds the missing management layer:

- **Source and compiled output are separate** — you edit `sp/section/preferences.md`; CLAUDE.md and AGENTS.md are compiled, never hand-edited
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

**488 tests / 0 failures**. Line recall vs hand-rolled `CLAUDE.md`: **91.5%**. Behavioral 4-task A/B eval: 2:2 split. See [`docs/eval-report.en.md`](docs/eval-report.en.md).

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
