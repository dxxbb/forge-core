# dxyOS validation

This example validates that `forge-core` can consume a real personal-OS workspace
(`dxy_OS`) end-to-end: load its sections, compile to `CLAUDE.md` + `AGENTS.md`,
and produce structurally equivalent output.

The validation does NOT try to byte-reproduce dxyOS's existing `CLAUDE.md` —
dxyOS uses `@`-imports and other runtime tricks that aren't part of
`forge-core`'s v0.1 adapter surface. We instead check:

1. All five sections load without errors (despite filenames with spaces).
2. The compiled output contains every section's content.
3. The compiled output is smaller than (or within 15% of) the hand-maintained
   version, confirming nothing is lost.
4. The full gate flow runs: init → diff → approve → bench snapshot → compare.

## Run

    python examples/dxyos-validation/validate.py \
        --dxyos-root ~/dxy_OS

By default the script uses `~/dxy_OS`. It copies the five section files into a
staging directory (`_staging/`, gitignored), writes a forge-compatible config,
then runs the full flow and reports metrics.

The staging directory is created fresh on each run; nothing from your real
dxyOS is modified.
