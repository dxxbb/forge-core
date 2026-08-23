# forge

> CLI name: `forge`. PyPI package: `context-forge`.

`forge` is a **review-gated context compiler**. It retains all raw evidence, but promotes only a small number of screened, bounded, owner-approved candidates into long-term assets and then compiles them into runtime views such as `CLAUDE.md` and `AGENTS.md`.

It is not a vector-memory product, and it does not ask the owner to review every memory item.

```text
experience / memory / external input
                 ↓
 Source Signal → stable Source Batch ──selective read──→ evidence
                 ↓
       disposition → provider Source Settlement
       ├─ covered / one-off / volatile-state / closed
       └─ Observation ──new independent evidence──→ Candidate Asset
                                                    ↓ one-card owner review
                                            reject / observe / promote
                                                                      ↓
                                           Canonical Source → compiler → runtime
                                                                      ↓
                                                     effective / revise / retire
```

## Why

Unreviewed automatic memory tends to fail in opposite ways: it either accumulates case-by-case rules until the asset layer becomes garbage, or declares everything covered and produces no useful accumulation.

Forge separates raw experience, time-bounded observations, promotion candidates, approved canonical assets, and generated runtime views. Approved writes reuse the existing ledger, verified snapshots, scoped commits, blame, and revert paths, so every asset can answer why it exists, who approved it, and how to undo it.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/dxxbb/forge-core/main/install.sh | bash
```

Then tell your agent:

> Use forge to initialize this workspace and take over my CLAUDE.md / AGENTS.md.

## Owner experience

The owner starts a Forge Run and reviews at most three Candidate Assets, one at a time. Between Runs there is no observation-pool or review-queue maintenance obligation.

The only candidate admission grounds are:

- evidence from at least two independent events;
- an explicit owner request for a lasting rule;
- a high-risk invariant with deterministic verification.

Every card must also contain `problem / proposal / scope / exclusions / exact patch / verification`. Frequency alone is not an abstraction-quality signal.

## Core objects

| Object | Location | Role |
|---|---|---|
| Source Signal | `source://...` in a Run | grouped monitor discovery without bulk-copying the external corpus |
| Source Batch | `batch_items` on a Source Signal | stable per-Run limit: 10 Memory Review Units/128 KiB or 5 clippings |
| Source Settlement | disposition plus provider checkpoint | prevents a settled batch from resurfacing |
| Evidence | `capture/` | retained, searchable raw material |
| Observation | `system/observations/` | time-bounded theme waiting for more evidence |
| Candidate Asset | `system/candidates/` | admitted one-card owner decision |
| Canonical Source | personalOS content / `context build/sections/` | governed long-term truth |
| Ledger Entry | `system/ledger/` | evidence, patch, commit, blame, and revert record |
| Runtime View | `context build/runtime/` | deterministic output for each agent runtime |

## Forge Run CLI

```bash
forge run status
forge run open
forge run next --budget 3

forge observation record --theme "..." --evidence capture/a.md
forge candidate create --help
forge run disposition <input> --as covered|one-off|volatile-state|observe|candidate|closed|defer

forge run ask --budget 3  # compatibility read view; run next drives the main flow
forge candidate show <candidate-id>
forge candidate revise <candidate-id> --scope "..." --exclusion "..."
forge run decide <candidate-id> --approve|--reject|--observe
forge run close

forge candidate feedback <candidate-id> \
  --outcome effective|revise|retire \
  --evidence <real-task-receipt>
```

The hosting agent performs semantic deduplication, classification, and abstraction. The CLI deterministically owns durable state, admission checks, budgets, expiry, the ledger, compile gate, commits, and metrics.

`run open` freezes the current bounded inputs. The operator then repeats `run next --budget N` and executes exactly the returned action until it says `close`. Agent Memory is capped at 10 semantic Review Units and 128 KiB per batch; web clippings are capped at 5 and default to checking existing canonical sinks, not launching deep knowledge intake. A non-deferred disposition must advance the provider checkpoint.

`run close` returns one of `complete`, `batch-complete`, or `incomplete`, plus machine-checked open-Run, clean/dirty worktree, and concrete remaining-source facts. The hosting agent must not overwrite those facts with its own summary. A genuinely clean empty Run creates neither an audit file nor a Git commit.

## Preserved substrate

- owner-controlled Rule and State Zones;
- verified-snapshot gate: unapproved rules cannot enter runtime;
- Canonical Source / Runtime View separation;
- multi-runtime adapters;
- atomic ledger apply, conflict/stale guards, blame, and revert;
- read-only provenance/diff/Candidate cards in the Portal;
- structural bench and behavioral evaluation harness.

Legacy `system/pr`, proposal schemas, memory workbenches, and bulk Portal review remain migration compatibility and audit history, not the main workflow once Forge Run is active.

## Status

`0.13.0` Alpha and dogfood-stage. Semantic Review Units, Selection Coverage, and Candidate Conclusion separate a zero-candidate batch from a globally complete selection; semantic candidate quality and long-term real-use outcomes still require repeated live Runs.

## Development

```bash
pip install -e '.[dev]'
pytest -q
```

Design: [`docs/run-design.md`](docs/run-design.md) · Acceptance: [`docs/run-acceptance-spec.md`](docs/run-acceptance-spec.md) · Decisions: [`ADR-0003`](docs/adr/0003-evidence-to-asset-promotion.md), [`ADR-0004`](docs/adr/0004-deterministic-source-settlement.md)

## License

MIT. See [`LICENSE`](LICENSE).

---

*中文:[`README.md`](README.md).*
