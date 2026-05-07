"""v0.4.2: monitor must not report self-loop import updates.

Bug (dogfood, ~/personalOS): after `forge target install` binds
`~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` to this workspace's runtime
artifacts, every `forge approve` flips those files (copy mode rewrites mtime
+ contents; symlink mode just delegates to the runtime artifact). Monitor's
``_import_updates`` happily reports them back as "import source updates",
because it doesn't know they are this workspace's *own* output. That's a
self-loop false positive — the agent burns one cycle re-importing the
context it just compiled.

Fix: load `.forge/manifest.json::targets[]`, build the set of bound target
paths (both literal + resolved-real), and skip any candidate path that lies
in that set. Workspaces with no manifest (legacy SP, fresh init) keep the
historical behavior.

The four cases below pin:
  1. target binding present  -> candidate is suppressed (new file)
  2. no target binding       -> candidate is reported (legacy behavior)
  3. target binding present, mtime/content drift -> still suppressed
  4. external (un-bound) source -> still reported alongside skipped target
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from forge.cli import _import_updates, _target_binding_paths


# ---------- helpers ----------


def _seed_workspace(tmp_path: Path) -> Path:
    """Workspace with `.forge/` dir + empty capture/inbox so _import_updates runs."""
    ws = tmp_path / "ws"
    (ws / ".forge").mkdir(parents=True)
    (ws / "capture" / "import").mkdir(parents=True)
    (ws / "system" / "inbox").mkdir(parents=True)
    return ws


def _seed_fake_home(tmp_path: Path, monkeypatch) -> Path:
    """Fake $HOME with `.claude/` and `.codex/` subdirs."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".codex").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("HOME", str(home))
    return home


def _write_manifest(ws: Path, targets: list[dict]) -> None:
    (ws / ".forge" / "manifest.json").write_text(
        json.dumps({"targets": targets}, indent=2), encoding="utf-8"
    )


# ---------- target binding paths helper ----------


def test_target_binding_paths_returns_empty_for_no_manifest(tmp_path: Path) -> None:
    """Legacy / fresh workspace with no `.forge/manifest.json` -> empty set."""
    ws = _seed_workspace(tmp_path)
    # no manifest written
    assert _target_binding_paths(ws) == set()


def test_target_binding_paths_returns_empty_for_no_targets_key(tmp_path: Path) -> None:
    """Manifest exists but has no `targets` key -> empty set."""
    ws = _seed_workspace(tmp_path)
    (ws / ".forge" / "manifest.json").write_text(
        json.dumps({"approved_hash": "abc"}), encoding="utf-8"
    )
    assert _target_binding_paths(ws) == set()


def test_target_binding_paths_collects_literal_and_resolved(tmp_path: Path) -> None:
    """Each binding contributes literal path AND resolved-real path."""
    ws = _seed_workspace(tmp_path)
    real_target = tmp_path / "real" / "CLAUDE.md"
    real_target.parent.mkdir()
    real_target.write_text("seed", encoding="utf-8")
    sym = tmp_path / "ext" / "CLAUDE.md"
    sym.parent.mkdir()
    os.symlink(real_target, sym)

    _write_manifest(
        ws, [{"adapter": "claude-code", "path": str(sym), "mode": "symlink"}]
    )

    paths = _target_binding_paths(ws)
    assert str(sym) in paths
    assert str(real_target.resolve()) in paths


# ---------- the four required cases ----------


def test_case1_target_binding_suppresses_import_update(
    tmp_path: Path, monkeypatch
) -> None:
    """Case 1: target binding to ~/.claude/CLAUDE.md -> not reported as new."""
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)

    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text("x" * 500, encoding="utf-8")

    # Pretend forge target install bound this path.
    _write_manifest(
        ws, [{"adapter": "claude-code", "path": str(claude_md), "mode": "copy"}]
    )

    updates = _import_updates(ws)

    # The bound target file must NOT show up.
    assert not any(str(claude_md) in u for u in updates), (
        f"self-loop: bound target {claude_md} leaked into import updates: {updates}"
    )


def test_case2_no_manifest_falls_back_to_legacy_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    """Case 2: no target binding -> historical behavior (reports import update)."""
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)
    # NO manifest written -> legacy / pre-bind workspace.

    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text("x" * 500, encoding="utf-8")

    updates = _import_updates(ws)

    matching = [u for u in updates if str(claude_md) in u]
    assert matching, (
        f"without manifest, monitor must still report {claude_md}; got {updates}"
    )
    # And specifically as `(new, ...)` since we have no capture record yet.
    assert any("(new" in u for u in matching), updates


def test_case3_target_binding_suppresses_even_when_content_changes(
    tmp_path: Path, monkeypatch
) -> None:
    """Case 3: bound target's mtime/content changed (e.g. forge approve refresh)
    -> still suppressed, because it's our own output, not an external change.
    """
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)

    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text("x" * 500, encoding="utf-8")

    # Seed a capture record reflecting the *previous* content, then mutate the
    # file as if `forge approve` just rewrote it. Without the manifest guard
    # this would surface as `(changed, ...)`.
    capture_dir = ws / "capture" / "import" / "20260507-100000"
    capture_dir.mkdir(parents=True)
    from forge.cli import _digest_text

    old_digest = _digest_text("x" * 500)
    (capture_dir / "claude-code.md").write_text(
        f"---\nsource: {claude_md}\nsource_digest: {old_digest}\n---\n\nold body\n",
        encoding="utf-8",
    )

    # Now flip the content (simulate forge approve copy-mode write-back).
    claude_md.write_text("y" * 600, encoding="utf-8")

    _write_manifest(
        ws, [{"adapter": "claude-code", "path": str(claude_md), "mode": "copy"}]
    )

    updates = _import_updates(ws)

    assert not any(str(claude_md) in u for u in updates), (
        f"self-loop on content drift: {claude_md} leaked: {updates}"
    )


def test_case4_real_external_source_still_reported_alongside_bound_target(
    tmp_path: Path, monkeypatch
) -> None:
    """Case 4: with one bound target + one un-bound external source, the
    bound one is suppressed and the external one is still reported."""
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)

    # Bound target — this should be suppressed.
    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text("x" * 500, encoding="utf-8")

    # Un-bound external source — should still be reported.
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_text("y" * 500, encoding="utf-8")

    # Manifest only binds claude-code, not agents-md.
    _write_manifest(
        ws, [{"adapter": "claude-code", "path": str(claude_md), "mode": "copy"}]
    )

    updates = _import_updates(ws)

    assert not any(str(claude_md) in u for u in updates), (
        f"bound target {claude_md} leaked: {updates}"
    )
    assert any(str(agents_md) in u for u in updates), (
        f"unbound external source {agents_md} should still be reported: {updates}"
    )


# ---------- symlink-mode coverage ----------


def test_symlink_mode_target_binding_also_suppressed(
    tmp_path: Path, monkeypatch
) -> None:
    """`forge target install --to ... --mode symlink`: external is a symlink
    pointing at the runtime artifact. Both the literal symlink path and the
    resolved real path must be suppressed.
    """
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)

    runtime = ws / "context build" / "runtime" / "claude-code" / "CLAUDE.md"
    runtime.parent.mkdir(parents=True)
    runtime.write_text("z" * 500, encoding="utf-8")

    claude_md = home / ".claude" / "CLAUDE.md"
    os.symlink(runtime, claude_md)

    _write_manifest(
        ws, [{"adapter": "claude-code", "path": str(claude_md), "mode": "symlink"}]
    )

    updates = _import_updates(ws)

    assert not any(str(claude_md) in u for u in updates), (
        f"symlink-mode bound target leaked: {updates}"
    )


# ---------- malformed manifest tolerance ----------


def test_malformed_manifest_falls_back_to_legacy_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    """A broken manifest must not crash monitor; degrade to legacy behavior."""
    home = _seed_fake_home(tmp_path, monkeypatch)
    ws = _seed_workspace(tmp_path)

    (ws / ".forge" / "manifest.json").write_text("{ not json", encoding="utf-8")

    claude_md = home / ".claude" / "CLAUDE.md"
    claude_md.write_text("x" * 500, encoding="utf-8")

    updates = _import_updates(ws)

    # Not crashing is the main contract; with no parseable targets it should
    # fall back to reporting the file (legacy behavior).
    matching = [u for u in updates if str(claude_md) in u]
    assert matching, (
        f"malformed manifest must degrade to legacy report; got {updates}"
    )
