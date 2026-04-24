# Migrating a personal-OS vault to forge-core

If you already have a "personal OS" style workspace — markdown files organized into sections/topics, hand-maintained or script-generated `CLAUDE.md` / `AGENTS.md` — this guide shows you how to migrate to forge-core, what you gain, and (honestly) what doesn't fit.

Example basis: [`dxy_OS`](https://github.com/dxxbb/dxy_OS). The validation script at [`examples/dxyos-validation/validate.py`](../examples/dxyos-validation/validate.py) runs this migration end-to-end automatically.

---

## 1. The target layout

forge-core expects:

```
<your-root>/
    sp/
        section/
            <one-concern>.md      # each with YAML frontmatter
            <another-concern>.md
            ...
        config/
            <config-name>.md      # recipe per compile target
```

After `forge init`:

```
    .forge/
        approved/sp/…             # last-approved source snapshot
        output/CLAUDE.md          # compiled artifacts
        output/AGENTS.md
        changelog.md
        manifest.json
        bench/<snapshot-name>/…
```

---

## 2. Mapping a typical personal-OS vault

Most personal-OS setups have something like:

- A `me.md` / `about-me.md` identity file.
- A collection of "preferences" or "working style" notes.
- A workspace/projects overview.
- A knowledge-base index.
- A skills catalog.
- Some kind of "CLAUDE.md" or "AGENTS.md" they paste into their agent setup.

To migrate:

**For each long-term content file:** extract the core content (drop host-app cruft) into `sp/section/<name>.md` with a YAML frontmatter header. Minimum frontmatter:

```yaml
---
name: about-me
type: identity
---
```

Supported optional fields (all preserved in provenance):

```yaml
name: about-me
type: identity
kind: canonical          # or: derived
updated_at: 2026-04-24
source: 02 user/me/me.md
upstream:                # list of files this was derived from
  - 02 user/me/me.md
  - 02 user/life/seeking/self understand/PAI Telos.md
generated_by: feishu-ingest-pipeline
```

**For each compile target:** write a config like:

```yaml
---
name: master
target: claude-code          # or: agents-md
sections:
  - about-me
  - preferences
  - workspace
  - knowledge-base
  - skills
required_sections:           # schema constraint — `forge doctor` enforces
  - about-me
  - preferences
preamble: |
  This is the personal context for Claude Code.
---

Optional free markdown body appended after sections.
```

---

## 3. Validated concretely on dxy_OS

The dxy_OS migration result (reproducible: `python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS`):

| Check                                          | Result                           |
|------------------------------------------------|----------------------------------|
| Sections loaded (filenames with spaces)        | 5 / 5 ✅                          |
| Configs loaded with `required_sections`        | 2 / 2 ✅                          |
| `forge doctor`                                  | 0 errors, 0 warnings ✅           |
| Compile is deterministic (same bytes on rerun) | ✅                                |
| Line recall vs dxyOS's own SP-compiled CLAUDE.md | **92.5%**                       |
| Per-section body completeness                   | 5 / 5 ✅                          |
| Full gate + bench round-trip (diff / approve / snapshot / compare) | ✅        |

**What's the 7.5% we don't recall?**

Inspecting the missing lines: they're dxyOS's own wrapper preamble text like *"This file provides guidance to Claude Code when working in this environment. It is auto-generated from..."*. That text is part of dxyOS's compile template, not its section content. forge-core replaces it with its own preamble + provenance block, so the content lines (identity, preferences, knowledge-base, skills) are all there — it's the *wrapper* that differs. We consider 92.5% recall on a MVP-schema-aligned vault a strong result for a first migration; if you want byte-level identical wrapping, you'd customize the adapter.

---

## 4. What forge-core gives you vs. a hand-rolled script

| Hand-rolled                                 | forge-core                              |
|---------------------------------------------|-----------------------------------------|
| Edit → rerun your own compile script       | Edit → `forge diff` shows BOTH source + per-target compiled diff before ship |
| "Hope nothing broke"                       | Every change gates through `forge approve`; `forge reject` cheap rollback |
| Your own custom changelog                  | `.forge/changelog.md` append-only, hash-tagged |
| Wrote your own "is it still the same?" check | `forge bench snapshot` + `compare` per-section bytes |
| No schema                                  | `required_sections` + `forge doctor` health check |
| "Where did this line come from?"           | Provenance header in every compiled output, per-section `upstream` chain |
| Hard to swap runtimes                      | Add a new target = write one `TargetAdapter` subclass |

---

## 5. What forge-core does NOT solve (honest)

These are real limits of v0.1, not "roadmap fluff":

1. **No `@file` include resolution.** Claude Code's `@README.md` transclusion is handled at the runtime level; forge-core inlines sections at compile time instead. If your current CLAUDE.md relies on `@` imports, you either:
    - Move the @-imported content into a section (becomes canonical), OR
    - Leave a thin root CLAUDE.md with `@` imports and use forge-core to generate the imported file.
2. **No ingest / watcher.** Sections are hand-edited (or script-edited by YOU). forge-core doesn't watch your vault. That's v0.2.
3. **No content-level migration from non-forge schemas.** If your current sections have exotic YAML fields, they're preserved in `section.meta` but forge-core doesn't do anything semantic with them. Add your own loader if you need.
4. **Sections are files, not database rows.** If you have 500 micro-facts and want retrieval, forge-core is the wrong tool. Use a vector store + retrieval sidecar; forge-core sits above that layer, not in it.
5. **Bench is structural.** v0.1 tells you "the compile grew by 45 bytes in the preference section." It does not tell you "your agent got smarter." LLM-based eval is v0.3.
6. **One workspace at a time.** No multi-vault federation, no team sharing contracts. Those are v0.4+.

---

## 6. Migration checklist

- [ ] Identify your 3-10 core long-term content files. Resist the urge to migrate 50.
- [ ] Create `<root>/sp/section/` and move them there, adding YAML frontmatter.
- [ ] Create `<root>/sp/config/` with at least one config (likely `master.md` targeting `claude-code`).
- [ ] Run `forge init`. Read `.forge/output/CLAUDE.md`. Does it look right?
- [ ] Run `forge doctor`. Fix any errors.
- [ ] Baseline: `forge bench snapshot baseline`.
- [ ] Make one real edit. `forge diff`. `forge approve`. `forge bench snapshot next`. `forge bench compare baseline next`.
- [ ] If all four feel natural, migrate the rest of your content. Otherwise: it's alpha; file an issue.

---

## 7. Keep your original vault

forge-core is additive. Nothing in the migration asks you to delete your original personal-OS vault, delete your existing scripts, or commit to forge-core long-term. The `examples/dxyos-validation/validate.py` approach — stage sections into a side directory, run forge-core there — is a safe way to evaluate without touching your mainline.

In dxy_OS's case, the actual vault stays at `~/dxy_OS` with its existing `01 assist/SP/output/` pipeline. forge-core runs on a copy in `_staging/` and is used to validate the concept. Moving the mainline over is a separate decision.
