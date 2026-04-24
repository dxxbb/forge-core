"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A minimal forge-core workspace with 2 sections + 1 config."""
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
    return tmp_path
