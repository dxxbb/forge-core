"""Regression test for Bug 5: forge capture FileExistsError on same-second collision.

When two `forge capture` invocations land in the same second, the second one
crashed with FileExistsError because batch_dir.mkdir(parents=True, exist_ok=False).

Fix: collision-resolution suffix `-1`, `-2`, ... appended to the timestamp.
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


def test_capture_collision_same_second_resolves_with_suffix(
    tmp_path: Path, monkeypatch
) -> None:
    """Two captures landing in the same second must both succeed."""
    _make_personal_os(tmp_path)
    src1 = tmp_path / "src1.md"
    src1.write_text("first source content here", encoding="utf-8")
    src2 = tmp_path / "src2.md"
    src2.write_text("second source content here", encoding="utf-8")

    # Pin datetime.now() so both captures resolve to the same timestamp string.
    import forge.cli as cli_mod
    from datetime import datetime as _real_dt

    fixed = _real_dt(2026, 5, 5, 12, 0, 0)

    class _FakeDT(_real_dt):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.astimezone(tz)

    monkeypatch.setattr(cli_mod, "datetime", _FakeDT)

    runner = CliRunner()
    r1 = runner.invoke(
        main, ["capture", "--from", str(src1), "--root", str(tmp_path)]
    )
    assert r1.exit_code == 0, r1.output

    r2 = runner.invoke(
        main, ["capture", "--from", str(src2), "--root", str(tmp_path)]
    )
    assert r2.exit_code == 0, r2.output

    # Both batch dirs should exist; the second has a numbered suffix.
    base_ts = "20260505-120000"
    batch_dirs = sorted(
        d.name for d in (tmp_path / "capture" / "import").iterdir() if d.is_dir()
    )
    assert base_ts in batch_dirs, batch_dirs
    assert any(name.startswith(f"{base_ts}-") for name in batch_dirs), batch_dirs
    # No crash, no FileExistsError surfaced.
    assert "FileExistsError" not in r2.output
