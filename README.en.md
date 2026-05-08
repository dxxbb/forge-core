# forge

> CLI name: `forge`. PyPI package: `context-forge` (the name `forge-core` is taken on PyPI).

**`forge`** is a review gate between your long-term personal content and the context files agents actually read (`CLAUDE.md`, `AGENTS.md`, …). Edit source, see what the compiled output would change, approve or reject. No memory, no sync, no prompt compilation.

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  sp/section/ │──▶│ sp/config/    │──▶│ output/       │
│ (you edit    │    │ (recipe:      │    │ CLAUDE.md    │
│  markdown)   │    │  which        │    │ AGENTS.md    │
│              │    │  sections,    │    │ (never       │
│              │    │  for which    │    │  hand-edited)│
│              │    │  runtime)     │    │              │
└──────────────┘    └──────────────┘    └──────────────┘
                           │                    │
                           ▼                    ▼ (forge target install)
                    ┌──────────────┐     ┌──────────────────┐
                    │ forge diff    │     │ ~/.claude/        │
                    │ forge approve │     │  CLAUDE.md        │
                    │ forge reject  │     │  (live artifact,  │
                    └──────────────┘     │   auto-synced)    │
                                         └──────────────────┘
```

---

## Install

```bash
# From GitHub (recommended)
pipx install git+https://github.com/dxxbb/forge-core.git
# or: uv tool install git+https://github.com/dxxbb/forge-core.git

forge --version
```

> Will simplify to `pipx install context-forge` once published to PyPI. Upgrade: `forge update`.

---

## 2-minute quickstart

### Option A: Claude Code drives it (recommended)

```bash
forge self-install               # bind forge skill into Claude Code
```

Open Claude Code, say:

> "Set up forge for me, import my existing CLAUDE.md"

Claude walks you through 8 steps (scaffold → import → review → approve → bind to `~/.claude/CLAUDE.md`). **No CLI needed.**

### Option B: pure CLI

```bash
forge new ~/forge-context
cd ~/forge-context

ls sp/section/                              # 5 template sections + _preface
ls sp/config/                               # claude-code.md + agents-md.md

forge init                                  # current sp/ becomes approved baseline

forge ingest --from ~/.claude/CLAUDE.md     # auto-classify into 5 sections
                                            # no API key? use --no-llm

forge review                                # one-screen: Origin + What changed +
                                            #   Affects + Bench + full diff

forge approve -m "import existing CLAUDE.md"

forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink
```

Daily workflow:

```bash
$EDITOR sp/section/preferences.md
forge review
forge approve -m "no auto git push"         # auto-syncs to ~/.claude/CLAUDE.md
```

---

## The problem

You told your agent "use Python, not TypeScript" last week. Today it gives you TypeScript. You open `CLAUDE.md` — that preference line is gone.

You didn't commit that file. `git blame` shows nothing. The agent's memory isn't broken — it's unmanaged.

You manage code with git: edit, diff, review, commit, rollback. What manages your agent config? Most people hand-edit and hope nothing broke.

`forge` adds that missing workflow. Not replacing git — filling the gap between long-term content and the compiled context agents actually read.

---

## "Can't I do this with `make` + `git`?"

Roughly, yes. If you've already wired that up, keep using it.

What forge adds:

1. `forge diff` shows both source diff AND compiled output preview for every target. `git diff` only shows text.
2. `sp/` tree has an integrity hash. `forge status` instantly shows drift.
3. Built-in structural bench.
4. Sharable convention — `sp/section/` + `sp/config/` is self-documenting.

What forge does NOT do:

- Compilation is deliberately dumb — no smarter than your `make` rules.
- v0.1 bench is structural only (bytes, lines, section sizes). LLM behavioral eval is v0.8.
- No session watching, no auto-capture, no decisions for you.

---

## Who should NOT use this

- **Your `CLAUDE.md` is 5 lines.** Hand-edit. Done.
- **You want AI to auto-organize your memory.** Use `claude-memory-compiler`.
- **You have thousands of micro-facts for retrieval.** That's vector store + RAG.
- **You use one AI tool and don't worry about lock-in.** forge's cross-runtime value is limited.
- **You want "install and forget."** forge requires `forge review / approve` on every change.

Good fit: **multiple AI tools, 30–300 lines of long-term context, you care about "is this still mine in 5 years."**

---

## Five concepts

- **Section** — one markdown file, one concern. YAML frontmatter + body.
- **Config** — recipe: for target X, include these sections in this order.
- **Output** — compiled file (`CLAUDE.md`, etc.). Never hand-edited. Deterministic.
- **Gate** — approve = `git commit`, reject = `git restore`, rollback any hash, audit = `git log`.
- **Target** — bind an output to an external path (e.g. `~/.claude/CLAUDE.md`), auto-synced on approve.

Full spec: [`docs/design.md`](docs/design.en.md).

---

## CLI commands

### Core (any forge workspace)

```
forge new <path>                # scaffold workspace
forge init                      # initialize approved baseline
forge status                    # approved hash + drift state
forge doctor                    # schema / provenance / adapter health check
forge build                     # sp/ → output/ (no gate, for CI)

forge review                    # recommended: Origin + What changed +
                                #   Affects + Bench + full diff
forge review --summary-only     # panels only, skip raw diff
forge review --tui              # keyboard-driven TUI (real terminal)
forge diff                      # legacy entry (= git diff HEAD -- sp/)

forge approve -m "message"      # = git commit + rebuild + sync targets
forge reject                    # = git restore HEAD -- sp/ output/
forge changelog                 # audit log from git log
forge rollback [hash]           # restore to historical approved state

forge ingest --from <file>      # import existing context, auto-classify
```

### Target binding

```
forge target install <adapter> --to <path>
forge target install <adapter> --to <path> --mode symlink
forge target list
forge target remove <adapter>
```

### Structural bench

```
forge bench snapshot <name>
forge bench list
forge bench compare <a> <b>
```

### Agent skill management

```
forge self-install              # bind forge skill to detected agent runtime
forge self-install --dry-run
forge update                    # upgrade CLI + refresh skill
```

### personalOS extension commands

These commands require a personalOS workspace layout (`capture/` / `system/inbox/` / `system/pr/` etc.). Not needed for regular forge workspaces:

```
forge monitor                   # scan personalOS workspace for global state changes
forge capture                   # capture raw evidence into capture/
forge proposal new              # generate schema-aware proposal from inbox
forge proposal validate         # validate proposal completeness
forge pr render                 # render §0.5 monitor-item view
forge pr done                   # close PR, archive to approve log
forge inbox done                # close inbox item
forge synthesize-clipping       # web clipping → KB topic synthesis
forge migrate-onepage           # upgrade onepage schema
```

---

## Adapters

Two core + three contrib adapters built in:

| Location | Name | Output |
|---|---|---|
| `forge/targets/` | `claude-code` | `CLAUDE.md` |
| `forge/targets/` | `agents-md` | `AGENTS.md` (cross-tool standard) |
| `forge/contrib/` | `cursor` | `.cursorrules` |
| `forge/contrib/` | `codex-cli` | Codex CLI variant of AGENTS.md |
| `forge/contrib/` | `rulesync-bridge` | Input for rulesync |

Custom adapter is ~20 LoC. See [adapters-spec.md](docs/adapters-spec.md).

---

## Validation

**488 tests / 0 failures** (was 88 at v0.1.0). Line recall vs hand-rolled `CLAUDE.md`: **91.5%**.

Behavioral: 4-task A/B with blind LLM judges, **2:2 split** — no regression. See [`docs/eval-report.en.md`](docs/eval-report.en.md).

---

## Examples

- [`examples/basic/`](examples/basic) — minimal workspace
- [`examples/dxyos-validation/`](examples/dxyos-validation) — end-to-end against a real personal-OS vault

---

## Development

```bash
pip install -e '.[dev]'
pytest -q                       # 488 tests, ~27s
```

---

## License

MIT. See [`LICENSE`](LICENSE).

---

*中文版：[`README.md`](README.md)。*
