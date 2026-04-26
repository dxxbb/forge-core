"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A minimal forge-core workspace with 2 sections + 1 config.

    v0.2: workspace is a git repo with an initial commit covering sp/ + output/.
    Tests that want to test "modified working tree" should edit sp/ files after
    the fixture returns; gate.diff_summary / gate.approve will operate against
    HEAD as the approved baseline.
    """
    from forge.gate import _git
    from forge.gate import actions as gate

    sec_dir = tmp_path / "sp" / "section"
    cfg_dir = tmp_path / "sp" / "config"
    sec_dir.mkdir(parents=True)
    cfg_dir.mkdir(parents=True)

    (sec_dir / "alpha.md").write_text(
        "---\nname: alpha\ntype: test\n---\n\nAlpha body content.\n",
        encoding="utf-8",
    )
    (sec_dir / "beta.md").write_text(
        "---\nname: beta\ntype: test\n---\n\nBeta body content.\n",
        encoding="utf-8",
    )
    (cfg_dir / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections:\n  - alpha\n  - beta\n---\n",
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(".forge/\n", encoding="utf-8")

    # Initialize git, build output, commit baseline
    _git.init_repo(tmp_path)
    gate.build(tmp_path)
    _git.add(tmp_path, ["sp", "output", ".gitignore"])
    _git.commit(
        tmp_path,
        "fixture initial commit",
        trailers={"forge-provenance": "version=0.2.0 source=test-fixture"},
    )
    return tmp_path
