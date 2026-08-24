# Initialize and import

Read this reference only when the user asks to create/setup a personalOS workspace, import existing context/memory, or triage a workspace that has not enabled the current Forge Run.

## Initialize a workspace

Resolve the exact path first. If the user says `当前目录` / `here` / `.`, use `pwd`. If they supply a path, resolve it. State the resolved path before writing.

Check `forge --version`. If missing, install Forge or ask for the local `forge-core` checkout; do not scaffold a working workspace that cannot build.

If an existing non-personalOS directory contains user files, ask once before adding the framework. An empty or partially initialized personalOS can proceed.

Create the current layout:

```text
capture/{agent history & memory,web clipping,external updates,import}/
user space/{daily,profile,goals,notes,private/secret config store}/
workspace/{project,topic,writing,whiteboard}/
assist config/{collaboration preference,work preference,skill}/
public knowledge base/{entity,topic,source}/
context build/{sections,config,runtime}/
system/{rules,eval,inbox,pr,approve log}/
```

Create these reviewed projection sources when missing:

```markdown
---
name: _preface
type: wrapper
---

This file provides guidance to agents when working in this environment.
It is generated from reviewed personalOS context projections. Do not edit runtime files by hand.
```

Create `about user.md`, `workspace.md`, `knowledge base.md`, `preference.md`, and `skill.md` in `context build/sections/`, each with matching `name`, its semantic `type`, and a short reviewed TODO rather than invented user facts.

Create `context build/config/claude-code.md` and `agents-md.md` with targets `CLAUDE` / `AGENTS`, target runtimes `claude-code` / `agents-md`, and this ordered section list:

```yaml
sections:
  - _preface
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
required_sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
demote_section_headings: true
```

Create a short root `README.md` describing the seven top-level areas if missing, initialize Git if needed, then run:

```bash
forge build --root <path>
forge doctor --root <path>
```

If both pass, report the workspace ready and offer import. Do not read personal files until the user says `import` or names explicit paths.

## Import into capture

Import is evidence intake. It never writes directly to `context build/sections`.

For a bare `import`, metadata-only discovery is authorized:

```bash
forge ingest --detect --root <path>
git status --short
```

Do not inspect or import private/secret stores, `.env`, credentials, cookies, keychains, or tokens.

Present a short concrete default plan from discovery: current project Claude memory, Codex memory/history, and relevant changed non-private personalOS notes. Include global runtime context only for onboarding or an explicit refresh. Ask for one confirmation because capture reads personal files.

After the user selects sources, use CLI-owned capture formats:

```bash
forge capture --root <path> --from <file>
forge capture --root <path> --from-claude-memory
forge capture --root <path> --from-claude-memory --claude-project <slug>
forge capture --root <path> --from-codex-memory
forge capture --root <path> --from-stdin
```

On a zones/Run workspace, the next owner-requested `forge 一下` screens the new evidence. Do not route it into a legacy proposal. On a pre-zones workspace, read `legacy-workflows.md` before processing the inbox.

## Pre-Run workspace triage

Use this only where zones/Run are not yet the active governance flow:

```bash
forge monitor --root <path>
```

- clean → report clean and stop;
- pending proposal → use the legacy review reference;
- pending inbox → use the legacy proposal reference;
- changed context source → build, doctor, diff, and prepare a Portal;
- import source update → offer concrete import candidates;
- `workspace-project changed` → capture that project with `forge capture --workspace-project <name>`;
- legacy onepage schema hint → dry-run and then `forge migrate-onepage --root <path>`;
- monitor/doctor failure → show the failing lines; do not claim readiness.

For workspace-project sync, the external repo remains the source of project implementation truth. Capture `git log`, diff/stat/status, and declared status sources; owner review decides what propagates into the onepage. Approval updates `last_synced`; rejection does not.
