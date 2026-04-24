# forge-core · Design

**One line.** `forge-core` is a *review-gated context compiler*. It turns long-term content (your notes, preferences, project state) into the context files that AI agents actually read (`CLAUDE.md`, `AGENTS.md`, …), with a PR-style review gate between source changes and compiled output, and a before/after bench to tell you if the compiled context actually got better.

---

## 1. The problem

Every "configure your agent" workflow today has three unsolved problems:

1. **Long-term content and runtime context are mixed together.**
   Notes, memories, rules, compiled output all sit in the same pile, no clear layer.
2. **Changes to long-term content enter the system without traceability.**
   An agent writes to your memory file — who approved it, why, can you roll it back? Usually: no.
3. **You can't tell if the system actually got better.**
   Most tools stop at "feels nicer now." There is no evaluation layer.

Existing tools each cover a slice:

- **`rulesync` / `ai-rules-sync`** — sync config across Cursor / Claude Code / Copilot / etc. But: no review gate, no long-term canonical source, no evaluation.
- **`claude-memory-compiler`** — auto-capture sessions → LLM-organize into memory. But: no human review in the loop, no multi-runtime compilation contract.
- **`agents-md-generator`, `skills-to-agents`** — generate `AGENTS.md` from code/skills. But: only one direction (code → view), not "long-term content → view".
- **DSPy / BAML** — compile *prompts / schemas*, not *long-term content*.
- **Google ADK Context Compaction** — in-session compaction, not cross-session canonical source.

`forge-core` is the layer none of them are.

---

## 2. Core model

```
┌─────────────┐    ┌──────────────┐    ┌─────────────────┐
│  section/   │──▶│   config/     │──▶│   output/       │
│ (canonical  │    │ (which        │    │ (per-runtime    │
│  source,    │    │  sections,    │    │  rendered view) │
│  one file   │    │  how to       │    │  CLAUDE.md      │
│  per        │    │  combine,     │    │  AGENTS.md      │
│  concern)   │    │  for which    │    │  …              │
│             │    │  target)      │    │                 │
└─────────────┘    └──────────────┘    └─────────────────┘
       ▲                                         ▲
       │                                         │
   human writes                          agent reads this
   long-lived                            every session
```

Three concepts, three directories:

- **Section** — an atomic piece of long-term content. One markdown file, one concern. Has a frontmatter (`name`, `type`, `updated_at`, optional `source`). Body is free markdown.
- **Config** — a recipe: "for target X, include these sections in this order with these wrappers." YAML frontmatter + optional preamble/postamble markdown.
- **Output** — the compiled file a runtime reads. Never hand-edited. Always reproducible from `section + config` via a target adapter.

Why this split matters:

- **canonical source ≠ compiled view.** You edit `section/`. The compiler produces `output/`. If someone edits `output/` directly, next rebuild wipes it — by design. This forces all truth to live in `section/`.
- **one source, many runtimes.** The same section set renders to `CLAUDE.md` and `AGENTS.md` (and future targets) via different configs + adapters.
- **composability.** A config is just "a list of section references." Sections are reusable across configs. You can have one config for a personal assistant, another for a project-specific agent, both reusing the same `about-me` section.

---

## 3. The review gate

Every `section/` change goes through a gate before `output/` is regenerated.

```
edit section/*.md  →  forge diff         (what would change in output/?)
                  ↓
                   forge approve         (accept: rebuild output/ + log)
                 or forge reject         (discard: revert section/ changes)
```

Mechanics:

- `.forge/approved/` holds the last approved snapshot of `section/` and `config/`.
- `forge diff` compares current `section/ + config/` against `approved/`, shows both the source diff AND a preview of how `output/` would change.
- `forge approve` promotes current state into `approved/`, rebuilds all outputs, appends an entry to `.forge/changelog.md` with timestamp + diff summary.
- `forge reject` reverts working tree to `approved/`.
- Provenance: every output file includes a header comment with the approval hash + timestamp, so you can trace any line in `CLAUDE.md` back to a specific approved section snapshot.

**What this gives you that `rulesync` doesn't:** you can't accidentally push a bad change to your agent context. You always see the compiled diff before it ships. You can always roll back.

---

## 4. The evaluation layer

`forge bench` gives you a quantitative before/after when you change sections or configs.

v0.1 ships a minimal harness:

- `forge bench snapshot` — capture current output + metadata (byte size, line count, section footprint) as a named baseline.
- `forge bench compare <before> <after>` — structural diff between two snapshots: which sections grew/shrank, total size delta, section-level changes.

This is deliberately *structural*, not LLM-based. v0.1 answers "did my change do what I expected structurally?" — not "is the agent smarter?" The latter belongs in v0.3 with real agent runs.

**What this gives you:** when you refactor your sections, you can verify the compiled output changed the way you meant it to change, and didn't bloat or drop content.

---

## 5. Target adapters

A target adapter knows the conventions of one runtime. v0.1 ships two:

- **`claude-code`** → produces `CLAUDE.md` with markdown sections and optional heading normalization.
- **`agents-md`** → produces `AGENTS.md` following the emerging cross-tool convention (plain markdown with predictable H2s).

Adapter contract is small:

```python
class TargetAdapter:
    name: str
    def render(self, sections: list[Section], config: Config) -> str: ...
    def filename(self) -> str: ...
```

Adding a new runtime = writing one class. No core changes.

---

## 6. What's explicitly NOT in v0.1

- No watcher / inbox / auto-ingest. You edit `section/` by hand or by script — `forge` doesn't watch for changes. (v0.2)
- No external memory providers (Mem0, Letta, Zep). v0.1 canonical source is plain markdown files. (v0.4, symptom-driven)
- No LLM-based eval. v0.1 bench is structural only. (v0.3)
- No cross-tool rules sync (Cursor `.cursorrules`, Copilot, Gemini, etc.). Only Claude Code + AGENTS.md. (Can add via adapter any time.)
- No CI / GitHub action integration. (Easy to add once API is stable.)

---

## 7. Design principles

1. **Canonical source is plain markdown.** No database, no vector store, no lock-in. You can delete `forge-core` and keep your content.
2. **Every output is reproducible.** Given the same `section/ + config/ + adapter version`, you get the same output bytes. Deterministic.
3. **The review gate is load-bearing.** Removing it turns `forge-core` into "another markdown templater." The gate is the concept.
4. **Small core, adapter surface.** Core stays under 1k LoC. Runtime-specific logic lives in adapters.
5. **Bench is first-class.** Not a plugin, not a "future feature." Ship it in v0.1 even minimal, because "does this actually work?" is the first thing anyone asks.

---

## 8. Roadmap

- **v0.1 (this release)** — compiler core, gate CLI, structural bench, Claude Code + AGENTS.md adapters, end-to-end fixture.
- **v0.2** — full governance: watcher, inbox, event-type dispatch, rollback, request-changes round-trip.
- **v0.3** — LLM-based eval: agent runs against question sets, before/after quality scoring.
- **v0.4** — adapters for external memory providers (Mem0 / Letta / Zep) as *optional sidecars*, not core.

See `docs/roadmap.md` (planned) for details.
