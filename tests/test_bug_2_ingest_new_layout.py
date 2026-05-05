"""Regression test for Bug 2: `forge ingest` must not crash in personalOS roots.

In a personalOS / v0428 root (with `capture/` `system/inbox/` `context build/`),
the legacy `forge ingest` previously bailed with "not a forge workspace" because
it only checked for legacy `sp/section/`. Worse, it told the user to run
`forge new <root>` — a command the skill explicitly forbids.

Fix (recommendation b in the bug write-up): in a personalOS root, `forge ingest`
exits with a clear deprecation-style message that points the user to
`forge capture`. Legacy SP roots still work as before.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main


def _make_personal_os(root: Path) -> None:
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)


def test_ingest_in_personal_os_root_redirects_to_capture(tmp_path: Path) -> None:
    """In a personalOS root, ingest should refuse but point to `forge capture`,
    not tell the user to run `forge new` (which the skill forbids)."""
    _make_personal_os(tmp_path)
    src = tmp_path / "input.md"
    src.write_text("hello world\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main, ["ingest", "--from", str(src), "--root", str(tmp_path)]
    )
    # Non-zero exit (we refused), but error message must redirect users somewhere
    # actionable instead of asking them to bootstrap a parallel legacy workspace.
    assert result.exit_code != 0, result.output
    assert "forge capture" in result.output, result.output
    # Crucially, must NOT tell the user to run `forge new`.
    assert "forge new" not in result.output, result.output
    # Must NOT claim the workspace is invalid — it is, just not for ingest.
    assert "not a forge workspace" not in result.output, result.output


def test_ingest_in_legacy_sp_root_still_works(tmp_path: Path) -> None:
    """Don't regress legacy SP-layout users: `forge ingest --from` still works."""
    runner = CliRunner()
    target = tmp_path / "ws"
    new_result = runner.invoke(main, ["new", str(target)])
    assert new_result.exit_code == 0, new_result.output

    src = tmp_path / "input.md"
    src.write_text("Some content here.\nMore content.", encoding="utf-8")
    result = runner.invoke(
        main,
        ["ingest", "--from", str(src), "--root", str(target), "--overwrite"],
    )
    assert result.exit_code == 0, result.output
    workspace_md = (target / "sp" / "section" / "workspace.md").read_text("utf-8")
    assert "Some content here." in workspace_md
