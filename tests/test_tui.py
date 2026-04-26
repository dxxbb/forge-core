"""Smoke tests for the TUI: import paths + non-TTY error path.

We can't drive the textual app from pytest (no TTY in test runner), so the
real interactive flow is exercised by hand. These tests cover:
  - `forge review --tui` exits cleanly with code 2 when stdout isn't a TTY,
    instead of crashing
  - the ReviewApp class can be instantiated (catches import-time errors)
  - the modal screens can be constructed
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner


def test_review_tui_no_tty_errors_cleanly(tmp_path: Path) -> None:
    """Calling `forge review --tui` from a non-TTY context should error nicely."""
    from forge.cli import main

    runner = CliRunner()
    runner.invoke(main, ["new", str(tmp_path / "ws")])

    result = runner.invoke(main, ["review", "--root", str(tmp_path / "ws"), "--tui"])
    # CliRunner's stdin/stdout aren't TTYs, so tui.run() returns 2
    assert result.exit_code == 2
    assert "real terminal" in result.output


def test_review_app_instantiates(tmp_path: Path) -> None:
    """Constructing the app shouldn't raise (catches import-time / class errors)."""
    from forge.tui import ReviewApp

    app = ReviewApp(tmp_path)
    assert app.BINDINGS  # has bindings registered
    binding_keys = {b.key for b in app.BINDINGS}
    for required in ("a", "r", "e", "d", "q"):
        assert required in binding_keys


def test_modal_screens_instantiate() -> None:
    """Modal screens should construct without errors."""
    from forge.tui import ApproveScreen, ConfirmScreen, SectionPickerScreen

    ApproveScreen()
    ConfirmScreen("test prompt")
    SectionPickerScreen(["preferences", "workspace"])
