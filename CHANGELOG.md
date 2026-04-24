# Changelog

All notable changes to `forge-core` will be recorded in this file.

## [0.1.0] — 2026-04-24

First release. Review-gated context compiler with schema-checked provenance.

### Added
- **Compiler core** — `Section` + `Config` + `Renderer`. YAML frontmatter + markdown body. Deterministic compile.
- **Section provenance** — `kind`, `upstream`, `generated_by` frontmatter fields; `last_rebuild_at` accepted as `updated_at` fallback (dxyOS-style schemas).
- **Config schema** — `required_sections` enforced by `forge doctor`.
- **Compiled-output provenance** — every CLAUDE.md / AGENTS.md carries a machine-readable header: config name, target, SHA256 digest (12 hex), compile timestamp, per-section type / kind / upstream / generated_by / bytes.
- **Target adapters** — `claude-code` (→ CLAUDE.md) and `agents-md` (→ AGENTS.md). Registry with `register_adapter()` for custom runtimes.
- **Review gate CLI** — `forge init / status / doctor / build / diff / approve / reject`.
- **Structural bench** — `forge bench snapshot / list / compare`. Per-file + per-section byte/line deltas, added/removed sections.
- **Schema health check** — `forge doctor` validates section references, required-section coverage, adapter registration, orphan sections, derived-without-upstream.
- **Examples**
  - `examples/basic/` — 4-section workspace with two configs.
  - `examples/dxyos-validation/` — full hard-validation on a real personal-OS vault: semantic equivalence (line recall vs the vault's own SP-compiled CLAUDE.md), completeness, doctor, gate + bench round-trip.
- **Migration guide** — `docs/migration-from-personal-os.md`.
- **Tests** — 45 pytest tests (section parser, loader, both adapters, all gate actions, bench, provenance, doctor).

### Validated
- Line recall vs dxyOS's own SP-compiled CLAUDE.md: **92.5%** (7.5% gap is dxyOS wrapper prose, not content).
- Compile is deterministic (identical bytes across runs on identical input).
- Full gate round-trip (diff → approve → rollback) passes on real vault content.

### Known limitations (honest)
- No watcher / inbox / auto-ingest. Sections are hand-edited or script-edited. (v0.2)
- No `@file` include resolution — Claude Code's `@README.md` transclusion happens at runtime, not compile time. If your vault relies on it, migrate imported content into sections OR keep a thin root CLAUDE.md that imports a forge-generated file.
- No external memory provider adapters (Mem0 / Letta / Zep). (v0.4, symptom-driven)
- Bench is **structural**, not LLM-based. v0.3 adds real LLM-graded eval harness.
- No cross-tool rules sync beyond claude-code + agents-md. Easy to add via adapter.
