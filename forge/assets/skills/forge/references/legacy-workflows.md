# Legacy inbox and proposal workflows

Read this reference only for a workspace that has not enabled zones/Forge Run and still uses `system/inbox` plus `system/pr`. Once zones/Run are active, do not route new intake here.

## Process inbox to proposal

For a large memory/history import, start with a workbench rather than a premature approval proposal:

```bash
forge proposal workbench --root <path> --inbox <id-prefix>
```

Use the workbench for item-level triage, canonical sink, volatility, verification, privacy, scope, coverage, and cross-review. Create `proposal.md` only after the items are reviewable.

For a small or already-triaged import:

```bash
forge proposal new --root <path>
forge proposal new --root <path> --inbox <id-prefix>
```

Fill each schema item with one disposition:

- `APPLY`: real asset/section change, with modifications and propagation;
- `COVERED`: already present, with `covered_by`;
- `ARCHIVE`: capture-only evidence trail;
- `DECIDE`: real owner choice, with options and recommendation;
- `NA`: index/metadata/non-asset, with reason;
- `MIXED`: composite parent whose sub-items each receive one disposition. Count sub-items only, never the MIXED parent itself.

Prefer `modified_files`, `modifications`, and optional `propagation_hints` so Forge derives the source → section → runtime propagation tree. Use a hand-written `propagation` tree only where the derived route is insufficient.

Validate until clean:

```bash
forge proposal validate <pr-id> --root <path>
```

The validator can normalize frontmatter and render the fallback view. Do not hand-write a second parallel review document.

## Prepare the review surface

Before asking for approval, apply the proposed canonical/context edits to the working tree without committing, then run:

```bash
forge proposal validate <pr-id> --root <path>
forge build --root <path>
forge doctor --root <path>
forge audit portal --root <path> --diff --base HEAD
```

The Portal is the primary review surface; `proposal.md` is the audit record. If build, doctor, or Portal generation fails, stop and show the error. Text fallback:

```bash
forge pr render <pr-id> --root <path>
forge pr render <pr-id> --root <path> --stdout
```

After the proposal exists, close represented inbox items with `forge inbox done --root <path> <inbox-file-path>`. Raw capture remains the evidence trail.

## Apply an owner decision

`approve` means approve the current Portal/proposal working-tree state; do not request a second commit confirmation.

After explicit approval:

```bash
forge approve --root <path> -m "<short message>"
forge pr done --root <path> -m "<short message>" <pr-id>
```

The first command rebuilds runtime, stages governed paths, and commits; the second records closure and removes the proposal directory.

On rejection, do not touch assets/context:

```bash
forge pr done --root <path> --reject -m "<reason>" <pr-id>
```

On revise, update only the proposal and working-tree review state; rebuild the Portal before asking again.

## Context source changes outside a proposal

Only when the user asks to inspect such a change:

```bash
forge build --root <path>
forge doctor --root <path>
forge diff --root <path> --no-color --no-pager
forge audit portal --root <path> --diff --base HEAD
```

Runtime files are generated views. If the user explicitly rejects an externally applied context-source change, use `forge reject --root <path>`; do not manually edit runtime output.
