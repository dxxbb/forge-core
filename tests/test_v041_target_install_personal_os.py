"""v0.4.1: target install must work in personalOS (v0428) layout.

Bug: `forge target install` resolved the runtime artifact path as
``state.output_dir / <filename>`` (legacy SP shape). The v0428 layout writes
runtime artifacts under ``context build/runtime/<adapter>/<filename>``
(``runtime_nested_by_target=True``), so the resolved path didn't exist and
``install_target`` failed with "no compiled output for adapter ..." (or, in
some installs, "no config in sp/config/ has target: ...").

These tests pin the new layout-aware behavior end-to-end:

- install_target finds the v0428 runtime artifact and creates the symlink/copy
- forge approve refreshes the symlink/copy after edits
- target list reports the binding correctly
- legacy SP layout still works (regression guard)
"""

from __future__ import annotations

from pathlib import Path

from forge.gate import actions as gate
from forge.gate.sync import install_target, list_targets


# ---------- helpers ----------


def _seed_personal_os(root: Path) -> Path:
    """Minimal personalOS / v0428 workspace ready for `gate.init`."""
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)
    (root / "context build" / "sections" / "about-user.md").write_text(
        "---\nname: about user\ntype: identity\n---\n\nThe user is dxy.\n",
        encoding="utf-8",
    )
    (root / "context build" / "config" / "claude-code.md").write_text(
        "---\n"
        "name: CLAUDE\n"
        "target: claude-code\n"
        "sections:\n"
        "  - about user\n"
        "---\n",
        encoding="utf-8",
    )
    (root / "context build" / "config" / "agents-md.md").write_text(
        "---\n"
        "name: AGENTS\n"
        "target: agents-md\n"
        "sections:\n"
        "  - about user\n"
        "---\n",
        encoding="utf-8",
    )
    return root


def _make_personal_os_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    _seed_personal_os(ws)
    gate.init(ws)
    return ws


# ---------- core regression: install in v0428 layout ----------


def test_install_target_resolves_v0428_nested_runtime(tmp_path: Path) -> None:
    """Install must locate runtime at `context build/runtime/<adapter>/<file>`."""
    ws = _make_personal_os_workspace(tmp_path)
    external = tmp_path / "ext" / "CLAUDE.md"

    binding = install_target(ws, "claude-code", external, mode="symlink")

    # external is a real symlink, pointing at the v0428 nested runtime artifact
    expected_runtime = ws / "context build" / "runtime" / "claude-code" / "CLAUDE.md"
    assert expected_runtime.exists(), "v0428 runtime artifact must exist before install"
    assert external.is_symlink()
    assert external.resolve() == expected_runtime.resolve()
    assert binding["adapter"] == "claude-code"
    assert binding["mode"] == "symlink"


def test_install_target_copy_mode_in_v0428_layout(tmp_path: Path) -> None:
    """Copy mode in v0428: external is a real file with the runtime contents."""
    ws = _make_personal_os_workspace(tmp_path)
    external = tmp_path / "ext" / "CLAUDE.md"

    install_target(ws, "claude-code", external, mode="copy")

    runtime = ws / "context build" / "runtime" / "claude-code" / "CLAUDE.md"
    assert external.exists() and not external.is_symlink()
    assert external.read_text("utf-8") == runtime.read_text("utf-8")


def test_install_target_handles_both_adapters_in_v0428(tmp_path: Path) -> None:
    """Both claude-code and agents-md should install cleanly in personalOS layout."""
    ws = _make_personal_os_workspace(tmp_path)
    claude_link = tmp_path / "ext" / "CLAUDE.md"
    agents_link = tmp_path / "ext" / "AGENTS.md"

    install_target(ws, "claude-code", claude_link, mode="symlink")
    install_target(ws, "agents-md", agents_link, mode="symlink")

    assert claude_link.is_symlink()
    assert agents_link.is_symlink()
    assert claude_link.resolve() == (
        ws / "context build" / "runtime" / "claude-code" / "CLAUDE.md"
    ).resolve()
    assert agents_link.resolve() == (
        ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    ).resolve()


# ---------- post-install: approve auto-refresh ----------


def test_approve_refreshes_v0428_symlink_target(tmp_path: Path) -> None:
    """After install + edit + approve, the symlinked external file reflects the new render."""
    ws = _make_personal_os_workspace(tmp_path)
    external = tmp_path / "ext" / "CLAUDE.md"
    install_target(ws, "claude-code", external, mode="symlink")

    # Edit a section
    section = ws / "context build" / "sections" / "about-user.md"
    section.write_text(
        "---\nname: about user\ntype: identity\n---\n\nNew identity body line.\n",
        encoding="utf-8",
    )

    result = gate.approve(ws, note="dogfood edit")
    assert result.targets_synced

    # Symlink content reflects the new render (resolves through the link)
    assert "New identity body line." in external.read_text("utf-8")


def test_approve_refreshes_v0428_copy_target(tmp_path: Path) -> None:
    """Copy-mode targets in v0428 layout get re-copied on approve."""
    ws = _make_personal_os_workspace(tmp_path)
    external = tmp_path / "ext" / "CLAUDE.md"
    install_target(ws, "claude-code", external, mode="copy")

    section = ws / "context build" / "sections" / "about-user.md"
    section.write_text(
        "---\nname: about user\ntype: identity\n---\n\nFresh copy line.\n",
        encoding="utf-8",
    )

    result = gate.approve(ws, note="copy refresh")
    assert result.targets_synced
    assert "Fresh copy line." in external.read_text("utf-8")


# ---------- target list ----------


def test_target_list_reports_v0428_binding(tmp_path: Path) -> None:
    """`list_targets` should return both bindings with the correct external paths."""
    ws = _make_personal_os_workspace(tmp_path)
    claude_link = tmp_path / "ext" / "CLAUDE.md"
    agents_link = tmp_path / "ext" / "AGENTS.md"
    install_target(ws, "claude-code", claude_link, mode="symlink")
    install_target(ws, "agents-md", agents_link, mode="symlink")

    bindings = list_targets(ws)
    by_adapter = {b["adapter"]: b for b in bindings}
    assert set(by_adapter) == {"claude-code", "agents-md"}
    assert by_adapter["claude-code"]["path"] == str(claude_link)
    assert by_adapter["agents-md"]["path"] == str(agents_link)
    assert by_adapter["claude-code"]["mode"] == "symlink"


# ---------- legacy SP layout regression guard ----------


def test_install_still_works_for_legacy_sp_layout(tmp_path: Path) -> None:
    """The v0.4.1 fix must not regress the legacy SP layout.

    Legacy: runtime is flat under `output/`, not nested by adapter.
    """
    from click.testing import CliRunner
    from forge.cli import main

    runner = CliRunner()
    ws = tmp_path / "ws"
    runner.invoke(main, ["new", str(ws)])
    runner.invoke(main, ["init", "--root", str(ws)])

    external = tmp_path / "ext" / "CLAUDE.md"
    install_target(ws, "claude-code", external, mode="symlink")

    # Legacy layout: output/CLAUDE.md (flat, not nested by adapter)
    expected = ws / "output" / "CLAUDE.md"
    assert expected.exists()
    assert external.is_symlink()
    assert external.resolve() == expected.resolve()


def test_install_unknown_adapter_in_v0428_uses_new_label(tmp_path: Path) -> None:
    """Error message should use the active layout's source label, not hardcode `sp/`."""
    import pytest
    from forge.gate.sync import TargetError

    ws = _make_personal_os_workspace(tmp_path)
    external = tmp_path / "ext.md"

    with pytest.raises(TargetError, match=r"no config in context build/config/"):
        install_target(ws, "made-up-adapter", external)
