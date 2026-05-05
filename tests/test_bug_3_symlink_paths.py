"""Regression test for Bug 3: detect vs monitor disagree on symlink source paths.

Old behavior:
  forge monitor   →  /real/target/AGENTS.md       (resolved)
  forge ingest --detect → ~/.codex/AGENTS.md      (symlink path as user typed)

Both detectors should report the **symlink path** — that's the path the user
and the agent platform actually configured. The resolved target is fine to
record internally for digest-based change detection, but should not be the
externally-printed identity.
"""

from __future__ import annotations

import os
from pathlib import Path

from click.testing import CliRunner

from forge.cli import _import_updates, main


def test_import_updates_reports_symlink_path_not_target(
    tmp_path: Path, monkeypatch
) -> None:
    """Monitor's update list should print the symlink path, matching detect."""
    # Build a fake home with one symlinked candidate (~/.codex/AGENTS.md →
    # actual target). We point _FILE_CANDIDATES at this through HOME.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "AGENTS.md"
    target.write_text("x" * 500, encoding="utf-8")  # > _MIN_BYTES

    codex_dir = fake_home / ".codex"
    codex_dir.mkdir()
    symlink = codex_dir / "AGENTS.md"
    os.symlink(target, symlink)

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    # `_FILE_CANDIDATES` uses literal "~/.codex/AGENTS.md", which expanduser
    # resolves via $HOME, not Path.home(). Override both to be safe.
    monkeypatch.setenv("HOME", str(fake_home))

    workspace = tmp_path / "ws"
    (workspace / "capture" / "import").mkdir(parents=True)
    (workspace / "system" / "inbox").mkdir(parents=True)

    updates = _import_updates(workspace)

    # The output should mention the symlink path, not the resolved target.
    symlink_str = str(symlink)
    target_str = str(target.resolve())
    matching = [u for u in updates if symlink_str in u]
    assert matching, (
        f"expected updates to reference symlink path {symlink_str!r}, "
        f"got updates={updates!r}"
    )
    # And, conversely, the resolved target alone should not show up as the
    # primary identity (it may appear inside an arrow-form, but never standalone).
    bare_target = [
        u
        for u in updates
        if target_str in u and symlink_str not in u
    ]
    assert not bare_target, (
        f"updates contain bare resolved-target path: {bare_target!r}"
    )
