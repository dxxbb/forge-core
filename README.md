# forge-core

**A review-gated context compiler.** Turn long-term personal content into the context files AI agents actually read (`CLAUDE.md`, `AGENTS.md`, …), with a PR-style gate between your edits and the compiled output, plus a before/after bench to tell you whether the change actually did what you meant.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ .forge/output│
│ (your notes, │    │ (recipe:      │    │ CLAUDE.md    │
│  one concern │    │  which        │    │ AGENTS.md    │
│  per file)   │    │  sections,    │    │ …            │
│              │    │  for which    │    │              │
│              │    │  runtime)     │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
         ▲                                      ▲
      you edit                          agents read this
                                        every session
```

Status: **v0.1.0 alpha.** Local-only, single workspace, two target adapters (Claude Code + AGENTS.md). See [Roadmap](#roadmap).

---

## Why another config tool?

There are already plenty of tools that sync agent config across runtimes (`rulesync`, `ai-rules-sync`), generate `AGENTS.md` from code (`agents-md-generator`, `skills-to-agents`), or compile session transcripts into memory files (`claude-memory-compiler`). **`forge-core` is not any of those.**

What's missing from all of them:

1. **A review gate.** Changes to your long-term content go straight into the compiled view with no human checkpoint. One bad `Edit` from an agent, and your next session is reading corrupted context.
2. **A clean split between canonical source and compiled view.** When you edit `CLAUDE.md` directly, where did that content really come from? Can you trace it? Roll it back?
3. **An evaluation layer.** You changed your `preferences.md`. Did the compiled context actually reflect that the way you wanted — or did it bloat, or drop a section, or mangle ordering?

`forge-core` addresses all three as first-class concerns. The compiler is the easy part; the gate and the bench are the point.

---

## Quickstart (2 minutes)

```bash
pip install -e .

# Create a workspace anywhere:
mkdir -p my-context/sp/section my-context/sp/config
cd my-context

# Write a section
cat > sp/section/about-me.md <<'EOF'
---
name: about-me
type: identity
---

I'm a backend engineer. Prefer terse responses. No emojis.
EOF

# Write a config
cat > sp/config/personal.md <<'EOF'
---
name: personal
target: claude-code
sections:
  - about-me
---
EOF

# Compile and gate
forge init              # snapshot current sp/ as approved baseline
cat .forge/output/CLAUDE.md
```

Now edit `sp/section/about-me.md`, then:

```bash
forge diff              # show source diff + compiled preview
forge approve -m "..."  # promote + rebuild + log
# or
forge reject            # discard changes, restore approved state
```

---

## Core concepts

### Section
An atomic piece of long-term content: one markdown file, one concern. YAML frontmatter (`name`, `type`, `updated_at`, `source`) + free markdown body.

### Config
A recipe: *"for target X, include these sections in this order with this preamble."* YAML frontmatter naming `target` (adapter) and `sections` (ordered list of section names).

### Output
The compiled file a runtime reads (`CLAUDE.md`, `AGENTS.md`, …). Never hand-edited. Always reproducible from `section + config` via an adapter. If you edit the output directly, the next rebuild wipes it — **by design**.

### The gate (`.forge/`)
Hidden state directory. Holds the last approved snapshot of `sp/`, the last compiled outputs, and an append-only `changelog.md`. Every change to `sp/` must pass through `forge approve` (or `forge reject`) before outputs are regenerated.

### The bench
Structural before/after comparison of compiled outputs — byte size, line count, per-section delta, added/removed sections. Not LLM-based in v0.1; that's v0.3.

---

## CLI

```
forge init                      # bootstrap .forge/ from current sp/
forge status                    # show approved hash, drift state
forge build                     # render sp/ to .forge/output/ (no gate; for CI)
forge diff                      # source diff + compiled preview
forge approve -m "message"      # promote current sp/, rebuild, log
forge reject                    # discard current sp/ changes, restore approved

forge bench snapshot <name>     # capture current output + metadata
forge bench list
forge bench compare <a> <b>     # structural diff between snapshots
```

---

## Comparison with related tools

| Tool                     | What it does                                        | What forge-core adds                               |
|--------------------------|-----------------------------------------------------|----------------------------------------------------|
| `rulesync`, `ai-rules-sync` | Sync agent rules across Cursor / Claude Code / Copilot / etc. | Review gate, canonical source, evaluation            |
| `agents-md-generator`    | Generate AGENTS.md from codebase                    | Source is your long-term content, not code          |
| `skills-to-agents`       | Compile SKILL.md → AGENTS.md                        | Full multi-section canonical source, not just skills |
| `claude-memory-compiler` | Auto-capture sessions → LLM-organize into memory    | Human review in the loop; no hidden LLM rewrites   |
| DSPy / BAML              | Compile prompts / schemas                           | Different layer — compiles *content*, not prompts  |

Nothing prevents you from combining forge-core with any of them: an adapter can emit Cursor rules, a watcher can feed inbox from captured sessions, etc. That's on the roadmap.

---

## Examples

- [`examples/basic/`](examples/basic) — minimal 4-section workspace with two configs (Claude Code + AGENTS.md). `cd examples/basic && forge build`.
- [`examples/dxyos-validation/`](examples/dxyos-validation) — end-to-end validation against a real personal-OS vault (`dxy_OS`). Script stages the sections, runs the full gate + bench flow, checks that every section survives the compile.

---

## Design

See [`docs/design.md`](docs/design.md) for the longer form: problem statement, design principles, adapter contract, roadmap details.

---

## Roadmap

- **v0.1 (current)** — compiler core, gate CLI, structural bench, two adapters (`claude-code`, `agents-md`).
- **v0.2** — full governance: watcher, inbox, event-type dispatch, rollback, request-changes round-trip.
- **v0.3** — LLM-based eval: agent runs against question sets, before/after quality scoring.
- **v0.4** — adapters for external memory providers (Mem0 / Letta / Zep) as *optional sidecars*.

---

## Development

```bash
pip install -e '.[dev]'
pytest
```

Tests: 29 unit tests covering section parsing, config loading, rendering (both adapters), gate actions, and bench. Run the dxyOS validation with `python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS`.

---

## License

MIT. See [`LICENSE`](LICENSE).
