# personalOS v0428 layout

forge-core supports two workspace layouts:

- legacy: `sp/section`, `sp/config`, `output`
- personalOS v0428: `context build/sections`, `context build/config`, `context build/runtime/<target>`

The v0428 layout is for an asset-first personalOS workspace. It keeps raw inputs, review workflow, reviewed assets, context projections, and runtime artifacts separate.

## Runtime-Facing Layout

forge-core compiles the runtime-facing part:

```text
context build/
  sections/
    _preface.md
    about user.md
    workspace.md
    knowledge base.md
    preference.md
    skill.md
  config/
    claude-code.md
    agents-md.md
  runtime/
    claude-code/CLAUDE.md
    agents-md/AGENTS.md
```

`sections/` are reviewed projections. They are not the user's full asset store.

`config/` contains target recipes.

`runtime/` is generated output and should not be edited by hand.

## Full personalOS Scaffold

A v0428 personalOS workspace usually has more than `context build`:

```text
capture/                 raw imported evidence
user space/              personal material; private/secret config is no-agent by default
workspace/               active projects, topics, writing, whiteboards
assist config/           collaboration preferences, work preferences, skills
public knowledge base/   source-grounded external knowledge
context build/           reviewed projections -> configs -> runtime artifacts
system/                  rules, eval, run, observations, candidates, ledger; legacy inbox/PR
```

The governed flow is:

```text
import raw material
  -> capture/import (retained evidence)
  -> explicit disposition
  -> time-bounded Observation or admitted Candidate Asset
  -> owner reviews at most three Candidate Assets, one at a time
  -> approve applies through ledger + compile gate
  -> forge build / doctor / diff
  -> runtime + real-use feedback
```

Import should not write directly into `context build/sections`.

## Claude Code Skill

The example skill in `examples/skills/forge/SKILL.md` is v0428-first:

- it must not call legacy `forge new`
- it must not create `sp/` or `output/` during onboarding
- it scaffolds the personalOS directories
- once zones/run are active, it routes import through evidence disposition,
  Observation, Candidate Asset, and `forge run`; `system/inbox`/`system/pr`
  remain compatibility-only for legacy workspaces
- `approve` means promote the current Candidate Asset through ledger, gate,
  build, validation, and scoped commit

## Validation

The dxyOS validation example stages from `context build/` first and falls back to older layouts:

```bash
python examples/dxyos-validation/validate.py --dxyos-root ~/dxy_OS
```

It checks:

- sections and configs load
- build outputs are deterministic
- doctor passes
- output content remains semantically equivalent to the existing dxyOS context
- gate + bench round trip works on nested runtime artifacts
