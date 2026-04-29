"""Tests for `forge self-install` and the underlying self_install module.

All tests pass an explicit fake HOME via the module API; CLI tests use a
sandboxed HOME so we never touch the real ~/.claude or ~/.forge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main
from forge.self_install import (
    MANAGED_MARKER_RE,
    self_install,
    manifest_path,
    format_summary,
)


def _make_claude_home(home: Path) -> Path:
    (home / ".claude").mkdir(parents=True)
    return home


# ---------- module-level: detection / install / idempotence ----------


def test_skipped_when_runtime_not_detected(tmp_path: Path) -> None:
    actions = self_install(home=tmp_path)
    statuses = {a.runtime: a.status for a in actions}
    assert statuses["claude-code"] == "skipped"
    # No manifest written when nothing was installed.
    assert not manifest_path(tmp_path).exists()


def test_fresh_install_writes_skill_with_marker(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    actions = self_install(home=home)

    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "installed"
    assert cc.target == home / ".claude" / "skills" / "forge" / "SKILL.md"
    assert cc.target.exists()

    body = cc.target.read_text("utf-8")
    assert MANAGED_MARKER_RE.search(body), "managed-by marker missing"
    assert "forge-runtime: claude-code" in body
    assert "name: forge" in body  # original frontmatter survived


def test_rerun_is_idempotent(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    self_install(home=home)
    actions = self_install(home=home)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "unchanged"


def test_managed_file_drift_is_refreshed(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    self_install(home=home)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    body = target.read_text("utf-8")
    assert MANAGED_MARKER_RE.search(body)
    # Append a tampered line; managed marker still present.
    target.write_text(body + "\nTAMPERED_LINE\n", encoding="utf-8")

    actions = self_install(home=home)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "updated"
    assert "TAMPERED_LINE" not in target.read_text("utf-8")


def test_unmanaged_file_is_a_conflict(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("user wrote this skill themselves\n", encoding="utf-8")

    actions = self_install(home=home)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "conflict"
    # File untouched.
    assert target.read_text("utf-8") == "user wrote this skill themselves\n"


def test_force_overwrites_unmanaged(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("custom user skill\n", encoding="utf-8")

    actions = self_install(home=home, force=True)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "updated"
    assert MANAGED_MARKER_RE.search(target.read_text("utf-8"))


def test_legacy_install_skill_content_auto_migrates(tmp_path: Path) -> None:
    """Old `forge install-skill` wrote the packaged asset verbatim, no marker.
    First run of `self-install` should adopt that file (not conflict)."""
    home = _make_claude_home(tmp_path)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    target.parent.mkdir(parents=True)
    from forge.self_install import _packaged_skill_source
    target.write_text(_packaged_skill_source().read_text("utf-8"), encoding="utf-8")

    actions = self_install(home=home)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "updated"
    assert "legacy" in cc.detail.lower()
    assert MANAGED_MARKER_RE.search(target.read_text("utf-8"))


def test_legacy_install_skill_file_migrates_without_force(tmp_path: Path) -> None:
    """A file we previously wrote (recorded in manifest) is ours to refresh
    even if it lacks the new managed marker — covers users who installed via
    the old `forge install-skill` before markers existed."""
    home = _make_claude_home(tmp_path)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("old install-skill content (no marker)\n", encoding="utf-8")
    # Simulate prior manifest claim.
    mf = manifest_path(home)
    mf.parent.mkdir(parents=True)
    mf.write_text(
        json.dumps(
            {
                "version": 1,
                "runtimes": {
                    "claude-code": {
                        "path": str(target),
                        "forge_version": "0.1.0",
                        "content_sha": "deadbeef",
                        "installed_at": "1970-01-01T00:00:00Z",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    actions = self_install(home=home)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "updated"
    body = target.read_text("utf-8")
    assert MANAGED_MARKER_RE.search(body)


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    actions = self_install(home=home, dry_run=True)
    cc = next(a for a in actions if a.runtime == "claude-code")
    assert cc.status == "detected"
    assert not (home / ".claude" / "skills" / "forge" / "SKILL.md").exists()
    assert not manifest_path(home).exists()


def test_manifest_records_binding(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    self_install(home=home)
    data = json.loads(manifest_path(home).read_text("utf-8"))
    assert data["runtimes"]["claude-code"]["forge_version"]
    assert data["runtimes"]["claude-code"]["path"].endswith(
        ".claude/skills/forge/SKILL.md"
    )
    assert "last_self_install_at" in data


def test_only_filter_restricts_runtimes(tmp_path: Path) -> None:
    home = _make_claude_home(tmp_path)
    actions = self_install(home=home, only=["claude-code"])
    assert {a.runtime for a in actions} == {"claude-code"}


def test_format_summary_handles_empty() -> None:
    assert "no runtimes" in format_summary([])


# ---------- CLI: command surface + deprecation alias ----------


def test_cli_self_install_runs_in_sandboxed_home(tmp_path: Path, monkeypatch) -> None:
    home = _make_claude_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    runner = CliRunner()
    result = runner.invoke(main, ["self-install"])
    assert result.exit_code == 0, result.output
    assert "installed" in result.output
    assert (home / ".claude" / "skills" / "forge" / "SKILL.md").exists()


def test_cli_self_install_dry_run(tmp_path: Path, monkeypatch) -> None:
    home = _make_claude_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    runner = CliRunner()
    result = runner.invoke(main, ["self-install", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "detected" in result.output
    assert not (home / ".claude" / "skills" / "forge" / "SKILL.md").exists()


def test_cli_install_skill_alias_emits_deprecation(tmp_path: Path, monkeypatch) -> None:
    home = _make_claude_home(tmp_path)
    monkeypatch.setenv("HOME", str(home))
    runner = CliRunner()
    result = runner.invoke(main, ["install-skill"])
    assert result.exit_code == 0, result.output
    assert "deprecated" in result.output.lower()
    assert (home / ".claude" / "skills" / "forge" / "SKILL.md").exists()


def test_cli_conflict_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    home = _make_claude_home(tmp_path)
    target = home / ".claude" / "skills" / "forge" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("user content\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    runner = CliRunner()
    result = runner.invoke(main, ["self-install"])
    assert result.exit_code == 1
    assert "conflict" in result.output.lower()
    assert target.read_text("utf-8") == "user content\n"
