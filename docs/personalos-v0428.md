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
system/                  rules, eval, inbox, PR state, approve log
```

The governed flow is:

```text
import raw material
  -> capture/import
  -> system/inbox
  -> system/pr proposal
  -> user review
  -> apply reviewed assets + context projections
  -> forge build / doctor / diff
  -> approve commits the reviewed state
```

Import should not write directly into `context build/sections`.

## Claude Code Skill

The example skill in `examples/skills/forge/SKILL.md` is v0428-first:

- it must not call legacy `forge new`
- it must not create `sp/` or `output/` during onboarding
- it scaffolds the personalOS directories
- it routes import through `capture`, `system/inbox`, and `system/pr`
- `approve` means approve the current proposal; after applying and passing build/doctor, it commits the reviewed state

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
