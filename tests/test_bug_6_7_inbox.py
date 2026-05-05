"""Regression tests for Bug 6 (inbox list source) and Bug 7 (inbox --root option).

Bug 6: `forge inbox list` reads `.forge/governance/inbox/` (legacy) while
`forge monitor` reads `system/inbox/` (personalOS). They must agree on the
source of truth — the personalOS `system/inbox/*.md` items.

Bug 7: `forge inbox` group rejects `--root`. `monitor`, `doctor`, `capture`
all accept it; `inbox` should too. Place `--root` either before or after the
subcommand name.
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


def _seed_inbox(root: Path, n: int) -> list[Path]:
    inbox_dir = root / "system" / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    for i in range(n):
        p = inbox_dir / f"20260505-12000{i}-import-context.md"
        p.write_text(
            "---\nkind: inbox\ntype: import-context\nstatus: pending\n---\n\n# Import\n",
            encoding="utf-8",
        )
        out.append(p)
    return out


# ---------- Bug 7: --root option on inbox group ----------


def test_inbox_group_accepts_root_option(tmp_path: Path) -> None:
    """`forge inbox --root <path> list` must work, just like other commands."""
    _make_personal_os(tmp_path)
    _seed_inbox(tmp_path, 2)

    runner = CliRunner()
    # NB: `--root` belongs to the group, so it goes BEFORE the subcommand name.
    result = runner.invoke(main, ["inbox", "--root", str(tmp_path), "list"])
    assert result.exit_code == 0, result.output
    # No "No such option" complaint.
    assert "No such option" not in result.output


def test_inbox_subcommand_root_still_works_after_group_root(tmp_path: Path) -> None:
    """Per-subcommand --root remains functional too (back-compat)."""
    _make_personal_os(tmp_path)
    _seed_inbox(tmp_path, 1)

    runner = CliRunner()
    result = runner.invoke(main, ["inbox", "list", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output


# ---------- Bug 6: inbox list reads system/inbox in personalOS roots ----------


def test_inbox_list_reads_system_inbox_in_personal_os(tmp_path: Path) -> None:
    """`inbox list` must list system/inbox/*.md items in a personalOS root."""
    _make_personal_os(tmp_path)
    items = _seed_inbox(tmp_path, 3)

    runner = CliRunner()
    result = runner.invoke(main, ["inbox", "--root", str(tmp_path), "list"])
    assert result.exit_code == 0, result.output

    # Old behavior: `(inbox is empty)`. New behavior: list each file.
    assert "(inbox is empty)" not in result.output, result.output
    for item in items:
        assert item.name in result.output, f"missing {item.name} in: {result.output}"


def test_inbox_list_legacy_layout_still_works(tmp_path: Path) -> None:
    """Don't regress legacy `.forge/governance/inbox/` users."""
    # Build legacy SP workspace.
    (tmp_path / "sp" / "section").mkdir(parents=True)
    (tmp_path / "sp" / "config").mkdir(parents=True)
    legacy_inbox = tmp_path / ".forge" / "governance" / "inbox"
    legacy_inbox.mkdir(parents=True)
    legacy_inbox_file = legacy_inbox / "0001-test-event.md"
    legacy_inbox_file.write_text(
        "---\n"
        "id: 1\n"
        "event_type: test-event\n"
        "commit_sha: abc1234\n"
        'path: "sp/section/foo.md"\n'
        "created_at: 2026-05-05T00:00:00+00:00\n"
        "---\n\nlegacy todo\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(main, ["inbox", "--root", str(tmp_path), "list"])
    assert result.exit_code == 0, result.output
    # Legacy item must show up too.
    assert "test-event" in result.output, result.output


def test_inbox_list_matches_monitor_count(tmp_path: Path) -> None:
    """Bug 6 core invariant: `inbox list` and `monitor` see the same files."""
    _make_personal_os(tmp_path)
    items = _seed_inbox(tmp_path, 3)

    runner = CliRunner()
    list_result = runner.invoke(main, ["inbox", "--root", str(tmp_path), "list"])
    assert list_result.exit_code == 0
    monitor_result = runner.invoke(main, ["monitor", "--root", str(tmp_path)])

    # Monitor reports "pending inbox: <N>" when count > 0; we expect 3.
    assert any(
        "pending inbox: 3" in line for line in monitor_result.output.splitlines()
    ), monitor_result.output

    # And inbox list must mention each of the 3 files.
    for item in items:
        assert item.name in list_result.output, list_result.output
