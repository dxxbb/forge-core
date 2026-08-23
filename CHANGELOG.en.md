# Changelog

All notable changes to `forge-core` will be recorded in this file.

## [0.13.0] — 2026-08-23

### Changed

- Candidate selection now operates on bounded semantic Review Units instead of provider files. Codex uses `MEMORY.md` Task Groups; Claude uses non-index memory files.
- Memory batches are capped by both unit count and 128 KiB. Aggregate indexes, raw history streams, and archived sessions remain evidence pointers and are reported separately.
- `run next` returns one `classify-source-item`; `run disposition --item` records an independent outcome for every unit.
- Status and close distinguish Selection Coverage from Candidate Conclusion. Any unprocessed source unit or standalone capture evidence makes the candidate conclusion `unknown`; provider-managed raw captures are not double-counted. `none` is reserved for complete selection.
- Close reports and persists one refreshed remaining-unit count, includes tracked provider checkpoints in the scoped commit, and prints the commit hash.

## [0.12.0] — 2026-08-23

Disposition alone did not make live Runs deterministic: aggregate counts could change mid-conversation, Memory had no bounded cursor, settled clippings could reappear, and agents could choose different workflow depth for the same signal. This release moves batch scope, provider settlement, the next action, and closing facts into the CLI.

### Added

- Stable Source Batches: at most 10 Agent Memory files or 5 web clippings per Run.
- Provider-specific settlement: Memory advances its seen checkpoint; clipping settlement writes a source marker and `covered` requires an existing canonical asset.
- `forge run next`, a single machine-readable Run Contract with the current action, batch items, constraints, and remaining candidate-review budget.
- `complete / batch-complete / incomplete` close states plus machine-checked open-Run, worktree, and remaining-source facts.
- [ADR-0004](docs/adr/0004-deterministic-source-settlement.md).

### Changed

- Reopening an active Run preserves its original batch; later same-source arrivals wait for the next Run.
- Web clippings enter through their bounded Source Batch only, not again as generic capture evidence.
- First Memory baseline/import reminders remain monitor information and cannot create an empty, unsettleable Run batch.
- The packaged Forge Skill now loops on `run next`, obeys batch boundaries, and reports close facts verbatim.

## [0.11.1] — 2026-08-23

### Added
- Grouped `source://<kind>` Source Signals connect monitor discovery to Run completeness without bulk-copying external corpora.
- `run status` reports source attention; unresolved signals may only be deferred with an explicit reason.

### Changed
- A still-actionable source can no longer disappear behind a successful empty Run. Deferred Runs report incomplete and resurface next time.
- Genuinely clean empty Runs create no audit file or Git commit.
- Untracked files are labeled unseen; those predating a provider baseline are additionally labeled historical backlog rather than guessed to be recent memory.

## [0.11.0] — 2026-08-23

Evidence-to-Asset Promotion replaces bulk item-by-item memory review while preserving capture, zones, the compile gate, ledger, compiler, provenance Portal, and evaluation substrate.

### Added
- Time-bounded `system/observations/` with evidence deduplication and automatic expiry.
- Admission-checked `system/candidates/` with repeated/explicit/high-risk grounds, scope, exclusions, exact patch, and verification.
- Observation, Candidate, input-disposition, owner-decision, real-use feedback, and promotion-metric CLI paths.

### Changed
- A Run presents integrity issues plus at most three Candidate Assets; state freshness is audit-only.
- A Run cannot close while any new input lacks an explicit disposition.
- The Portal renders read-only Candidate cards and the Evidence-to-Asset workflow.

### Fixed
- Ledger and Run frontmatter parsing now recognizes delimiter lines instead of splitting on literal `---` inside YAML values.
- `forge run close` no longer swallows scoped-commit failures; it restores a resumable open Run and fails loudly.

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
