# Demo walkthrough

Real terminal output from the `examples/basic/` fixture. You can reproduce everything below by:

```bash
pip install -e .
cd examples/basic
rm -rf .forge
```

Then run the commands in order.

---

## 1. `forge init`

Bootstrap `.forge/` from the current `sp/`. Treats the current state as the first approved baseline.

```
$ forge init
initialized .forge at /.../examples/basic/.forge

$ forge status
{
  "initialized": true,
  "manifest": {
    "approved_hash": "2132239a4399eac283fdbf13ba252a3be463aa2912c70a7fa0cb9ae5202b24b5",
    "approved_at": "2026-04-24T03:57:51+00:00",
    "version": "0.1.0"
  },
  "current_hash": "2132239a4399eac283fdbf13ba252a3be463aa2912c70a7fa0cb9ae5202b24b5",
  "drifted": false
}

$ forge diff
no changes since last approve
```

`.forge/output/` now contains the compiled views:

```
$ ls .forge/output/
AGENTS.md  CLAUDE.md
```

---

## 2. Edit a section, see both diffs

Add a line to `sp/section/preferences.md`:

```
$ echo "- When touching shared config, always PR first." >> sp/section/preferences.md

$ forge diff
======== source diff (sp/) ========
--- approved/section/preferences.md
+++ current/section/preferences.md
@@ -9,3 +9,5 @@
 - When unsure, ask. Don't guess.
 - Ground external facts in live sources (docs, repo) before asserting.
 - No emojis unless explicitly requested.
+
+- When touching shared config, always PR first.


======== output diff ========
--- codex ---
--- approved/codex
+++ proposed/codex
@@ -18,6 +18,8 @@
 - Ground external facts in live sources (docs, repo) before asserting.
 - No emojis unless explicitly requested.
 
+- When touching shared config, always PR first.
+
 ## Skills
 
 Available skills (loaded on demand):
--- personal ---
--- approved/personal
+++ proposed/personal
@@ -19,6 +19,8 @@
 - Ground external facts in live sources (docs, repo) before asserting.
 - No emojis unless explicitly requested.
 
+- When touching shared config, always PR first.
+
 ## workspace

 Active projects:
```

Two things to notice:

- **Source diff** shows the raw edit to `sp/section/preferences.md`.
- **Output diff** shows the same change landing in BOTH compiled targets (`CLAUDE.md` and `AGENTS.md`). That's the "canonical-source-to-many-runtimes" compilation visible per-file.

---

## 3. `forge approve`

Promotes current `sp/` to the new approved baseline, rebuilds all outputs, appends a changelog entry.

```
$ forge approve -m "add shared-config PR rule"
approved hash=82bab7145d23 at 2026-04-24T03:57:58+00:00
  wrote .../examples/basic/.forge/output/AGENTS.md
  wrote .../examples/basic/.forge/output/CLAUDE.md

$ forge diff
no changes since last approve

$ cat .forge/changelog.md
# forge-core changelog

- 2026-04-24T03:57:51+00:00 init (hash=2132239a4399)
- 2026-04-24T03:57:58+00:00 approve (hash=82bab7145d23) — add shared-config PR rule
```

---

## 4. `forge reject` — undo an in-progress change

Make a bad edit, then reject:

```
$ echo "noise" >> sp/section/about-me.md

$ forge diff --source-only
======== source diff (sp/) ========
--- approved/section/about-me.md
+++ current/section/about-me.md
@@ -7,3 +7,4 @@
 I'm a senior software engineer ...
 Working language: English.
+noise

$ forge reject
Discard all current changes to sp/ and restore approved? [y/N]: y
restored sp/ from last approved

$ forge diff
no changes since last approve
```

---

## 5. Bench: before/after structural comparison

Snapshot the current state, make a real change, snapshot again, compare.

```
$ forge bench snapshot v1
snapshot `v1` created at 2026-04-24T03:58:11+00:00
  outputs: ['AGENTS.md', 'CLAUDE.md']
  sections: 4

$ echo "- bench-runner — compare snapshots." >> sp/section/skills.md
$ forge approve -m "add bench-runner skill"
approved hash=9d489ad17c3e ...

$ forge bench snapshot v2

$ forge bench compare v1 v2
compare v1 -> v2

# outputs
  AGENTS.md: 952B -> 1023B (+71B, +2L)
  CLAUDE.md: 1212B -> 1283B (+71B, +2L)

# section size deltas
  skills: 203B -> 274B (+71B)
```

What this tells you:

- Both compiled outputs grew by exactly 71 bytes / 2 lines (as expected — one new bullet).
- The growth came entirely from the `skills` section.
- No other section was affected. No accidental bloat. No missing section.

If you edit five sections at once and only one was *supposed* to change, this is where you catch the rest.

---

## 6. What bench v0.1 does NOT do (yet)

It does not answer "is the agent actually smarter." It answers "did my change to `sp/` produce the structural change I expected in the compiled outputs." That's a weaker claim, on purpose — we'd rather ship a small-but-honest bench in v0.1 than a fake "LLM eval" that's just vibes.

LLM-graded evals against question sets are v0.3 (see [design.md §8](design.md#8-roadmap) and roadmap in README).

---

## Validation: real personal-OS vault

The above uses a toy fixture. To prove the same flow works on a real long-term-content vault, `examples/dxyos-validation/validate.py` runs the entire loop against [`dxy_OS`](https://github.com/dxxbb/dxy_OS) — 5 sections, filenames with spaces, 3.3KB+ per section. Excerpt:

```
staged 5 sections + 2 configs into .../examples/dxyos-validation/_staging
============================================================
step 1/6: load sections
  loaded `about user` (1482B, 11L)
  loaded `knowledge base` (1504B, 22L)
  loaded `preference` (1530B, 24L)
  loaded `skill` (487B, 7L)
  loaded `workspace` (3302B, 25L)

step 4/6: content completeness check
  [ok]    `about user` present in both outputs
  [ok]    `knowledge base` present in both outputs
  [ok]    `preference` present in both outputs
  [ok]    `skill` present in both outputs
  [ok]    `workspace` present in both outputs

step 6/6: gate + bench flow on real content
  snapshot v1: ['AGENTS.md', 'CLAUDE.md']
  diff: 2 output file(s) would change
  approved hash=d3729c8349fb
  AGENTS.md delta: +24B, +3L
  CLAUDE.md delta: +24B, +3L

VALIDATION PASSED
```

Run it yourself:

```
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```
