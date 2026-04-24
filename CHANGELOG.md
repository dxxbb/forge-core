# Changelog

All notable changes to `forge-core` will be recorded in this file.

## [0.1.0] — 2026-04-24

First release. Minimum viable review-gated context compiler.

### Added
- **Compiler core** — Section + Config + Renderer models. YAML frontmatter + markdown body parsing.
- **Target adapters** — `claude-code` (→ CLAUDE.md) and `agents-md` (→ AGENTS.md). Adapter registry with `register_adapter()` for custom runtimes.
- **Review gate** — `forge init / diff / approve / reject / status / build` CLI. `.forge/` state directory with approved snapshot, compiled outputs, `manifest.json`, and append-only `changelog.md`.
- **Structural bench** — `forge bench snapshot / list / compare`. Per-file byte/line deltas, per-section growth tracking, added/removed section detection.
- **Examples**
  - `examples/basic/` — 4-section workspace with two configs.
  - `examples/dxyos-validation/` — end-to-end validation script that runs the full flow on a real personal-OS vault.
- **Tests** — 29 pytest tests covering parser, loader, both adapters, all gate actions, and bench.

### Known limitations
- No watcher / inbox / auto-ingest. Edit `sp/section/` by hand or by script.
- No external memory provider adapters (Mem0 / Letta / Zep). Canonical source is plain markdown files only.
- Bench is structural, not LLM-based. Answers "did my change do what I meant structurally?", not "is the agent smarter?"
- No cross-tool rules sync (Cursor, Copilot, Gemini, …) beyond `claude-code` and `agents-md`. Easy to add via adapter.
