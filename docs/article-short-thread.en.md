# Short version (X / Mastodon thread, 8 posts)

*Drafted as an 8-post thread. Replace [LINK] with the repo URL before posting. Keep screenshots in mind between posts 3/4 and 7/8.*

---

**1/**
Have you ever asked your AI to "clean up" its own `CLAUDE.md` / `AGENTS.md`, only to find later that it silently deleted a section you actually needed?

I have. That's why I built `forge-core`.

**2/**
The agent-tooling ecosystem in 2026 has three rich layers:

- rules sync (rulesync, ai-rules-sync)
- memory compilers (claude-memory-compiler)
- prompt compilers (DSPy, BAML)

None of them has a **review gate** between your long-term content and the compiled context the agent actually reads.

**3/**
`forge-core` treats your personal context the way a build system treats code:

- `sp/section/` = canonical source (you edit)
- `sp/config/` = recipe (which sections, for which runtime)
- `.forge/output/` = compiled artifacts (never hand-edited)
- `forge diff / approve / reject` = gate

**4/**
The thing no text-diff tool gives you: a **compiled-output diff**.

When you edit `sp/section/preferences.md`, `forge diff` shows:
(a) what changed in the source, AND
(b) what will change in *each* compiled target (`CLAUDE.md`, `AGENTS.md`, …).

If the output diff is wrong, `forge reject` puts you back.

**5/**
"Can't I do this with `make` + `git`?"

Sort of. You'd be re-inventing: semantic diff across multiple compiled targets, integrity hash over the source tree, structural bench, append-only changelog, reproducible adapter contract.

forge-core just packages all of that in ~1k LoC Python.

**6/**
I'm not pretending `forge-core`'s v0.1 bench is "LLM evaluation." It isn't. It's a **structural** bench — byte/line/section deltas between snapshots. It catches the failure mode: "I made a change and didn't notice the context doubled."

Real LLM-graded evals are v0.3.

**7/**
Validated end-to-end on two fixtures:

- a minimal toy (`examples/basic/`)
- a real personal-OS vault with 5 sections, 3.3KB+ each, filenames-with-spaces (`examples/dxyos-validation/`)

29 unit tests. MIT. Zero hosted service. Works offline.

**8/**
v0.1 is alpha; breaking changes are welcome feedback. If you've felt the "my CLAUDE.md got silently corrupted" pain, try it and push back.

Especially curious about:
- adapters for non-Claude runtimes (Cursor, Aider)
- what bench metrics are actually useful to you

[LINK]
