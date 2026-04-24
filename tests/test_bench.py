from pathlib import Path

import pytest

from forge.gate import actions as gate
from forge.bench import harness as bench


def test_snapshot_without_output_raises(workspace: Path) -> None:
    with pytest.raises(RuntimeError):
        bench.snapshot(workspace, "v1")


def test_snapshot_and_list(workspace: Path) -> None:
    gate.init(workspace)
    snap = bench.snapshot(workspace, "v1")
    assert snap.name == "v1"
    assert "CLAUDE.md" in snap.outputs
    assert set(snap.sections) == {"alpha", "beta"}
    assert bench.list_snapshots(workspace) == ["v1"]


def test_compare_detects_section_growth(workspace: Path) -> None:
    gate.init(workspace)
    bench.snapshot(workspace, "v1")
    # grow alpha
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text(
        "---\nname: alpha\n---\n" + "extra content\n" * 20,
        encoding="utf-8",
    )
    gate.approve(workspace, note="grew alpha")
    bench.snapshot(workspace, "v2")
    cmp = bench.compare(workspace, "v1", "v2")
    assert cmp.section_deltas["alpha"]["bytes_delta"] > 0
    assert cmp.output_deltas["CLAUDE.md"]["bytes_delta"] > 0


def test_compare_detects_added_section(workspace: Path) -> None:
    gate.init(workspace)
    bench.snapshot(workspace, "before")
    (workspace / "sp" / "section" / "gamma.md").write_text(
        "---\nname: gamma\n---\ngamma body\n", encoding="utf-8"
    )
    # update config to include gamma
    (workspace / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections:\n  - alpha\n  - beta\n  - gamma\n---\n",
        encoding="utf-8",
    )
    gate.approve(workspace, note="add gamma")
    bench.snapshot(workspace, "after")
    cmp = bench.compare(workspace, "before", "after")
    assert "gamma" in cmp.added_sections


def test_compare_missing_snapshot_raises(workspace: Path) -> None:
    gate.init(workspace)
    bench.snapshot(workspace, "v1")
    with pytest.raises(FileNotFoundError):
        bench.compare(workspace, "v1", "nonexistent")
