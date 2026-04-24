# forge-core

> You asked Claude to clean up your `CLAUDE.md`. It silently deleted the section that told it to always write tests. You didn't notice for three sessions.
>
> Or: you edited your preferences, and somehow the compiled context doubled in size. You have no idea why.
>
> Or: you pushed your `CLAUDE.md` to share with a teammate, and realized you can't explain where half the lines came from.

If any of those felt familiar, this is for you.

**`forge-core`** is a tiny tool that sits between your long-term personal content and the context files agents actually read (`CLAUDE.md`, `AGENTS.md`, …). It treats that relationship the way a build system treats code: **canonical source you edit, compiled artifacts you never edit, and a gate between them that shows you exactly what's about to change before it ships.**

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ .forge/output│
│ (you edit    │    │ (recipe:      │    │ CLAUDE.md    │
│  markdown    │    │  which        │    │ AGENTS.md    │
│  files, one  │    │  sections,    │    │ …            │
│  concern     │    │  for which    │    │  (never      │
│  per file)   │    │  runtime)     │    │  hand-edited)│
└──────────────┘    └──────────────┘    └──────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ forge diff    │ ← see what would change
                    │ forge approve │ ← ship + log + rebuild
                    │ forge reject  │ ← roll back
                    └──────────────┘
```

Status: **v0.1.0 alpha.** Single workspace, local-only, two target adapters. See [Roadmap](#roadmap).

---

## For the skeptic: "can't I do this with `make` + `git` already?"

Yes, roughly. And if you've already wired up `make` + `git` to your agent context, you probably don't need this.

What `forge-core` gives you that a hand-rolled `make` + `git` doesn't:

1. **A semantic diff, not just a text diff.** `forge diff` shows you both the source change AND a preview of how *each compiled output* would change. `git diff` shows only text; you'd have to manually re-run your build to see what the output diff looks like, and do it for every runtime target.
2. **A single integrity contract.** An approved snapshot is a hash over the whole `sp/` tree. Any drift shows up in `forge status`. You can tell at a glance whether your compiled outputs are stale.
3. **A structural bench built in.** When you change sections, you immediately see which sections grew/shrank, which were added/removed, total byte delta per output. No need to write that yourself.
4. **A sharable convention.** Anyone can look at `sp/section/` + `sp/config/` + `.forge/changelog.md` and understand the system. A hand-rolled `make` setup is readable only to its author.

**What `forge-core` is NOT pretending to be yet:**

- It's not a smarter compiler than your `make` rules. The compilation is deliberately dumb.
- Its bench is *structural only* in v0.1. It measures byte / line / section deltas. It does NOT yet measure "is the agent actually smarter with the new context." That's v0.3, and it needs real agent-run harnesses that v0.1 doesn't ship. If you want LLM-graded evals today, use `promptfoo` or similar — `forge-core` is not a replacement for that, and won't be.
- It's not a runtime memory system. It doesn't watch sessions, doesn't auto-capture, doesn't decide for you. You do the editing. `forge-core` just makes the editing safer and the compilation reproducible.

If "dumb compiler + semantic diff + audit log + roadmap toward real evals" sounds useful, keep reading.

---

## 30-second demo

```bash
$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - Ground external facts in live sources.
 - No emojis unless requested.
+
+- When touching shared config, always PR first.

======== output diff ========
--- personal ---
@@ -19,6 +19,8 @@
 - No emojis unless requested.
 
+- When touching shared config, always PR first.
+

$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .forge/output/CLAUDE.md
  wrote .forge/output/AGENTS.md
```

That's the core loop. Every change to `sp/` shows both as a source diff and a *compiled output diff* before it ships. If the compiled diff is wrong, `forge reject` puts you back.

See [`docs/demo-walkthrough.md`](docs/demo-walkthrough.md) for the full walkthrough (init → edit → diff → approve → bench snapshot → compare).

---

## Quickstart (2 minutes)

```bash
pip install -e .

mkdir -p my-context/sp/section my-context/sp/config
cd my-context

cat > sp/section/about-me.md <<'EOF'
---
name: about-me
type: identity
---

I'm a backend engineer. Prefer terse responses. No emojis.
EOF

cat > sp/config/personal.md <<'EOF'
---
name: personal
target: claude-code
sections: [about-me]
---
EOF

forge init
cat .forge/output/CLAUDE.md
```

Now edit a section and run `forge diff`.

---

## Core concepts (five small things)

- **Section** — one markdown file, one concern. YAML frontmatter + body.
- **Config** — recipe: for target X, include these sections in this order.
- **Output** — the compiled file (`CLAUDE.md`, …). Never hand-edited. Deterministic.
- **Gate** — `.forge/` state: approved snapshot, changelog, manifest. Every source change must pass `forge approve` before outputs regenerate.
- **Bench** — structural before/after over compiled outputs. `snapshot` / `list` / `compare`.

Full spec: [`docs/design.md`](docs/design.md).

---

## CLI

```
forge init                      # bootstrap .forge/ from current sp/
forge status                    # show approved hash, drift state
forge doctor                    # schema + provenance health check
forge build                     # render sp/ to .forge/output/ (no gate; for CI)
forge diff                      # source diff + compiled preview
forge approve -m "message"      # promote current sp/, rebuild, log
forge reject                    # discard current sp/ changes, restore approved

forge bench snapshot <name>     # capture current output + metadata
forge bench list
forge bench compare <a> <b>     # structural diff between snapshots
```

---

## Where this sits in the 2026 landscape

| Tool                     | What it owns                                        | What forge-core does that it doesn't |
|--------------------------|-----------------------------------------------------|---------------------------------------|
| `rulesync`, `ai-rules-sync` | Format translation across 8+ runtimes         | Review gate + canonical-vs-compiled split + bench |
| `claude-memory-compiler` | Auto-capture sessions → LLM-organize into memory    | Human review in the loop; no hidden LLM rewrites |
| `agents-md-generator`    | Generate AGENTS.md from codebase                    | Source is your long-term content, not code |
| `skills-to-agents`       | Compile SKILL.md → AGENTS.md                        | Full multi-section source, not just skills |
| DSPy / BAML              | Compile *prompts / schemas*                         | Different layer — compiles *content*, not prompts |
| Google ADK (Context Compaction) | In-session context compaction                | Cross-session canonical source, not in-flight |

Nothing stops you from combining forge-core with any of them: an adapter can emit Cursor rules, a watcher can feed inbox from captured sessions. See roadmap.

---

## Hard validation (not just "it works")

Claims about "personal AI" tools usually stop at *"I built it and it feels good."* forge-core ships two concrete layers of evidence:

**Structural** (every change, every commit):

| Check                                          | Result                |
|------------------------------------------------|-----------------------|
| Sections loaded (incl. filenames with spaces)  | 5 / 5                 |
| Configs with `required_sections` schema        | 2 / 2                 |
| `forge doctor`                                  | 0 errors              |
| Compile determinism (same bytes, 2 runs)       | pass                  |
| **Line recall vs dxy_OS's own SP-compiled CLAUDE.md** | **92.5%**      |
| Per-section body completeness                  | 5 / 5                 |
| Gate round-trip (diff → approve → rollback)    | pass                  |
| Bench round-trip (snapshot → compare)          | pass                  |
| Unit test suite                                | 54 / 54               |

**Behavioral** (one real A/B eval, v0.1):

4 tasks × 2 versions = 8 subagent-generated answers + 4 blind LLM judges on a real personal-OS vault. After randomized position assignment, **2–2 split** between master (pre-migration pipeline) and forge (post-migration). No detectable behavioral regression. Full methodology, positional-bias caveat, and raw judgments in [`docs/eval-report.md`](docs/eval-report.md).

This is not "forge compiles objectively better context" — v0.1 doesn't have the statistical power to say that. It's "forge compiles context the agent uses at least as effectively as the hand-rolled pipeline." For a migration decision, that's the claim that matters.

Reproduce:

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

The 7.5% line-recall gap is dxy_OS's own preamble text ("This file provides guidance..."), not content — the five SP sections land in full. See [`docs/migration-from-personal-os.md`](docs/migration-from-personal-os.md) for the full analysis and how to migrate your own personal-OS vault.

---

## Examples

- [`examples/basic/`](examples/basic) — minimal 4-section workspace with two configs.
- [`examples/dxyos-validation/`](examples/dxyos-validation) — end-to-end validation against a real personal-OS vault (`dxy_OS`). Runs all the hard-validation checks above.

## Adding a custom target

Adapters are the extension surface. Adding a new runtime is ~20 LoC:

```python
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets import register_adapter
from forge.targets.base import TargetAdapter

class CursorAdapter(TargetAdapter):
    name = "cursor"
    default_filename = ".cursorrules"

    def render(self, sections: list[Section], config: Config) -> str:
        body = "\n\n".join(f"# {s.name}\n{s.body}" for s in sections)
        return f"# cursor rules for {config.name}\n\n{body}\n"

register_adapter(CursorAdapter())
```

Then any config with `target: cursor` compiles through it. No forks, no core patches.

---

## Roadmap

- **v0.1 (current)** — compiler core, gate CLI, structural bench, two adapters (`claude-code`, `agents-md`).
- **v0.2** — full governance: watcher, inbox, event-type dispatch, rollback, request-changes round-trip.
- **v0.3** — LLM-based eval harness: agent runs against question sets, before/after quality scoring. *This is where the "evaluation as first-class layer" claim becomes real rather than aspirational.*
- **v0.4** — adapters for external memory providers (Mem0 / Letta / Zep) as *optional sidecars*, not core.

---

## Development

```bash
pip install -e '.[dev]'
pytest
```

45 unit tests + end-to-end dxyOS validation. Run the full hard validation with:

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

---

## License

MIT. See [`LICENSE`](LICENSE).
