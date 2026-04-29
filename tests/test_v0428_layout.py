from pathlib import Path

from forge.gate import _git
from forge.gate import actions as gate
from forge.compiler.loader import load_sections, load_all_configs
from forge.bench import harness as bench


def test_v0428_context_build_layout_round_trip(tmp_path: Path) -> None:
    sec = tmp_path / "context build" / "sections"
    cfg = tmp_path / "context build" / "config"
    sec.mkdir(parents=True)
    cfg.mkdir(parents=True)
    (sec / "about.md").write_text(
        "---\nname: about\n---\n\nAbout body.\n", encoding="utf-8"
    )
    (cfg / "claude.md").write_text(
        "---\nname: personal\ntarget: claude-code\nsections:\n  - about\n---\n",
        encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text(".forge/\n", encoding="utf-8")

    _git.init_repo(tmp_path)
    gate.init(tmp_path)

    assert sorted(load_sections(tmp_path)) == ["about"]
    assert sorted(load_all_configs(tmp_path)) == ["personal"]
    runtime = tmp_path / "context build" / "runtime" / "claude-code" / "CLAUDE.md"
    assert runtime.exists()
    assert "About body." in runtime.read_text("utf-8")

    (sec / "about.md").write_text(
        "---\nname: about\n---\n\nAbout body changed.\n", encoding="utf-8"
    )
    diff = gate.diff_summary(tmp_path)
    assert diff.changed
    assert any("context build/sections/about.md" in line for line in diff.source_diff_lines)
    assert "personal" in diff.output_diffs

    approved = gate.approve(tmp_path, "update about")
    assert approved.outputs_written == [runtime]
    assert "About body changed." in runtime.read_text("utf-8")

    snap = bench.snapshot(tmp_path, "after")
    assert "claude-code/CLAUDE.md" in snap.outputs
