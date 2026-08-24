---
name: forge
description: "Operate a personalOS workspace with forge: run review-gated context settlement, inspect pending governance, initialize a workspace, import memory, or review legacy proposals."
metadata:
  version: 0.20.0
  requires:
    bins: ["forge"]
  cliHelp: "forge --help"
---

# forge — review-gated context asset workflow

Forge preserves raw experience but only promotes a small, qualified subset into owner-governed assets. Canonical Sources are reviewed truth; compiled `AGENTS.md` / `CLAUDE.md` files are Runtime Views.

Never use legacy `forge new`, `sp/`, or `output/` for onboarding.

## Route the request

- `forge 一下` / `做一次 forge` / `结算` / `forge run` → use **Forge Run** below.
- `有什么待审的` / `队列里有什么` → run `forge run status`; do not open a Run.
- Workspace has no personalOS framework or user asks to initialize/import → read [references/initialize-and-import.md](references/initialize-and-import.md) before acting.
- Workspace has not enabled zones/Run and still uses inbox/proposals → read [references/legacy-workflows.md](references/legacy-workflows.md). Once zones/Run are active, new intake must not return to that legacy path.
- `安装 forge` → check `forge --version`; if absent install with `pipx install git+https://github.com/dxxbb/forge-core.git` (fallback `uv tool install` or `pip install --user`), run `forge self-install`, report, and stop unless initialization was also requested.

Resolve workspace authority from the current task checkout (`git rev-parse --show-toplevel`). A detached worktree is a valid isolated workspace. Never switch to a sibling checkout because it looks more canonical; Forge rejects a `--root` that crosses this boundary.

## Forge Run

A Run is an owner-initiated settlement conversation. Do not raise governance topics proactively between Runs.

### Execute the Run Contract

1. `forge run status --root <path>` → briefly report time since last Run, source attention, reviewable Candidate count, Selection Coverage, and state freshness.
2. `forge run open --root <path>` → freeze this Run's Source Batch and dirty baseline. Reopening resumes the same batch.
3. Repeatedly run `forge run next --root <path> --budget 1` and execute only the returned action:
   - `decide-integrity`: present this one issue and wait for owner approve/reject.
   - `classify-source-items`: silently classify only the listed 1–3 Review Units; record one independent disposition for every unit with `--item <unit-id>`.
   - `classify-source-item`: same, for the single listed Review Unit.
   - `classify-source`: classify the one source contract only; do not invent another workflow.
   - `classify-evidence`: classify the one capture item only.
   - `decide-candidate`: present the complete Review Card and wait for the owner.
   - `close`: immediately run `forge run close --root <path>`, then send only the returned `OWNER-FACING SUMMARY` text exactly as written.
4. Treat `owner_facing_projection` as the complete public boundary. Do not compose a second owner-facing account from internal contract fields.

Default Candidate review budget is **1**. A background slice may contain up to 3 Review Units, but each keeps its own disposition, checkpoint, and stale check. Do not reread this Skill or broadly rescan the provider for every unit; use the content and evidence pointers in the contract, opening only what the semantic decision actually requires.

### Classify each Review Unit

Every listed unit gets exactly one route:

- **covered** — an existing Canonical Source already states the claim. The receipt must prove actual content, not merely name a file:

  ```bash
  forge run disposition <input> --item <unit-id> --as covered \
    --sink <tracked-canonical-path> \
    --coverage-claim <claim> \
    --coverage-locator <stable-heading-or-text> \
    --coverage-excerpt <exact-existing-excerpt> \
    --root <path>
  ```

- **one-off** — a concrete defect belongs in code, tests, or an Issue; fix that bounded defect first, then record `--as one-off --sink <receipt>`.
- **volatile-state** — update the real current-state asset during this Run, then record `--as volatile-state --sink <path>`. The path must have been clean when the Run opened, or have a ledger entry with `origin=run:<id>`. Multiple units may keep their own semantic receipts for the same Run-owned sink; close checks the latest formal receipt for that path, so do not issue a mechanical “refresh” that overwrites an earlier unit's real reason. Any drift after the latest receipt still fails. Pre-existing dirty content is never a Run-Owned Write.
- **observe** — only for an actual unresolved owner correction, observed failure, conflict, or owner-deferred Candidate. First record an Observation with real `--source-context`, a falsifiable `--repeat-if`, `--route-gap`, and stable `--event-id`; then route to its Observation id.
- **candidate** — only after current Candidate Qualification is satisfied. Create the card, then route to its Candidate id.
- **closed** — no durable value or correct further action; preserve raw evidence and give a short reason.
- **defer** — genuinely cannot settle this unit now; state why. The Run must close as incomplete.

Canonical sinks are files inside the current checkout that are Git tracked, persistent, authoritative, non-private, and not under `capture/`, `system/`, `context build/runtime/`, scratch/output/temp, or another generated surface. Never search private/secret paths to find a receipt.

### Candidate Qualification

A Candidate may enter Owner Review only with one of these Promotion Grounds:

- `repeated`: at least two different Evidence Events (real thread/session/incident/source encounters), not two files pointing to the same event.
- `owner-directed`: the owner explicitly asked for a rule or asset to apply **in future**, and the card preserves the exact long-term request.

`high-risk` affects priority, not qualification. A single important task, successful research result, or request such as “这次认真做 / 先判断 / 给教程” is not owner-directed. Route a confirmed single defect to code/test/control; route a real unresolved recurrence hypothesis to Observation; otherwise use covered, the proper project/state sink, or closed.

For `repeated`, target authority changes the evidence requirement. If the target is a rule-zone `type: preference` Section or one of that Section's declared upstream sources, Forge treats it as a global Preference Authority. It then requires at least two exact owner corrections from two different Evidence Events **and two different bounded operational contexts**:

```bash
--owner-correction '<event-id>' '<operational-context>' '<exact owner quote>'
```

Repeated failures, tests, or corrections inside one workflow prove that workflow needs repair; they do not prove a global owner preference. Route them to that workflow's Skill, code, tests, current-state asset, or closed. `owner-directed` remains valid from one exact request that explicitly applies in future.

Historical Candidate files missing current grounds, events, Review Card fields, or executable patch are `legacy-unqualified`: audit-only, excluded from pending Candidate counts, Candidate Conclusion, and Owner Review. Never fill missing fields with placeholders or ask the owner to qualify them. If later evidence independently meets the current contract, create a new qualified card.

Before candidate creation, read the target and directly related Canonical Sources. The card must contain:

- `source-context` and stable `event-id` values: what actually happened;
- `existing-coverage`: what already exists and the exact durable gap;
- `asset-fit`: why this belongs in an owner-governed asset rather than code/test, volatile state, reusable Skill, platform baseline, or Observation;
- applicable `owner-correction` evidence: each bounded context, event id, and exact owner quote when a repeated global preference is proposed;
- `promotion-rationale`: why the stated ground is satisfied now;
- problem, proposal, scope, exclusions, exact patch target/anchor/mode/text, verification;
- `expected-effect`: what future behavior changes;
- `decision-question`: the precise owner choice.

If any part cannot be stated from evidence, it is not a Candidate.

### Present a Candidate for review

Do not lead with the proposed rule. Explain, in simple language:

1. which real experiences caused the card to exist;
2. why the current assets or engineering controls do not already solve it;
3. why it is a durable cross-situation asset rather than a case-specific patch;
4. which target authority Forge resolved and, for a repeated global preference, the two cross-context owner corrections;
5. why its Promotion Ground is satisfied now;
6. the exact text and location to be written;
7. what future behavior changes and what remains out of scope.

Then ask the card's exact decision question. Owner outcomes:

- 同意 → `forge run decide <id> --approve [--note] --root <path>`
- 不写 → `forge run decide <id> --reject [--note] --root <path>`
- 继续观察 → `forge run decide <id> --observe [--note] --root <path>`

“为什么 / 举例 / 改一下” is not a decision. Explanations do not write state. Revisions update the same card with `forge candidate revise`; do not create a duplicate.

### Source bounds

- Agent Memory: inspect only contract Review Units and their listed evidence pointers. Codex uses one `## Task` plus explicitly tagged group conclusions; unassigned group material is a separate Group Summary unit; content without Task structure falls back to one Task Group. Claude uses one non-index memory file. Raw histories, aggregate indexes, and archived sessions are pointers/diagnostics, not extra Review Units. A batch is capped at 10 units and 128 KiB.
- Web clipping: inspect only the listed, at most 5 files. Search existing Canonical Sources for coverage; do not start deep `knowledge-intake`, external research, or full-article walkthrough unless the owner separately requests it.
- Do not process the same web clipping or provider-managed Memory capture again as standalone evidence.

All `classify-*` actions are silent to the owner. Their `owner_facing_projection.default` is `silent`. If a heartbeat is actually required, emit `owner_facing_projection.heartbeat_if_required` **原样且单独**; do not paraphrase it or add unit titles, themes, routes, Observation details, counts, remaining work, or reasons. Only `decide-*` and the machine-generated close summary enter the foreground.

### Truth at close

- Selection Coverage is complete only when every eligible Review Unit and standalone capture item has a disposition. Observation is already a route and is not unscreened backlog.
- Candidate Conclusion is `available` when a qualified pending Candidate exists; `none` only when coverage is complete and none exists; otherwise `unknown`.
- `batch-complete`, current-batch zero, and an empty `forge run open` are not global completion claims.
- Close must stale-check Run-Owned Writes and atomically commit only Run-owned sinks plus Run records/settlement state. It must not absorb the dirty baseline or unrelated user changes.
- `forge run close` returns an `OWNER-FACING SUMMARY` derived from the Closure Snapshot. Send that summary **原样且单独**; do not prepend “Forge 完成”, reinterpret `batch-complete`, or write another summary. The projection contains `complete|batch-complete|incomplete`, Run closure, clean/dirty, commit, Selection Coverage, Candidate Conclusion, and remaining screenable units. A clean empty Run creates no audit file or commit.

## Read-only questions

- Why does this rule exist? `forge ledger blame <path> --line N`
- What changed in this file? `forge state show <path>`
- When was the last settlement? `forge run status`
- What is in the observation pool? `forge observation list`
- What is this card? `forge candidate show <id>` (legacy-unqualified output must say it will not enter Owner Review)
- Is an asset still effective? `forge candidate list --all`, then record real use with `forge candidate feedback` when appropriate.

## Safety

- Do not read private/secret paths or import personal files without permission.
- Do not hand-edit `system/observations`, `system/candidates`, Run state, ledger, or Runtime Views.
- Do not promote, approve, send, deploy, or make production changes without the required explicit owner decision.
- When a command reports stale/failed, report it honestly and follow the next Run Contract; do not hide the failure with a different sink or a hand-written state edit.
