"""Tests for `forge update`."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge import update as update_mod
from forge.cli import main


# ---------- detection ----------


def test_detect_editable_when_inside_git_repo(monkeypatch, tmp_path: Path) -> None:
    fake_repo = tmp_path / "checkout"
    (fake_repo / "forge").mkdir(parents=True)
    (fake_repo / ".git").mkdir()
    fake_init = fake_repo / "forge" / "__init__.py"
    fake_init.write_text("# stub", encoding="utf-8")

    monkeypatch.setattr(update_mod, "forge", _stub_module(str(fake_init)))
    info = update_mod.detect_install_kind()
    assert info.kind == "editable"


def test_detect_pipx_by_path(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "pipx" / "venvs" / "context-forge" / "lib" / "python3.12" / "site-packages" / "forge" / "__init__.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr(update_mod, "forge", _stub_module(str(fake)))
    assert update_mod.detect_install_kind().kind == "pipx"


def test_detect_uv_tool_by_path(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "uv" / "tools" / "context-forge" / "lib" / "site-packages" / "forge" / "__init__.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr(update_mod, "forge", _stub_module(str(fake)))
    assert update_mod.detect_install_kind().kind == "uv-tool"


def test_detect_system_when_no_signals(monkeypatch, tmp_path: Path) -> None:
    fake = tmp_path / "site-packages" / "forge" / "__init__.py"
    fake.parent.mkdir(parents=True)
    fake.write_text("# stub", encoding="utf-8")
    monkeypatch.setattr(update_mod, "forge", _stub_module(str(fake)))
    assert update_mod.detect_install_kind().kind == "system"


# ---------- run_update behavior ----------


def test_editable_install_does_not_run_upgrade(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "editable", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod, "_run", _fail_run)
    action = update_mod.run_update()
    assert action.kind == "editable"
    assert action.upgrade_status == "skipped"
    assert "git pull" in action.upgrade_output


def test_pipx_install_invokes_pipx_upgrade(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "pipx", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod.shutil, "which", lambda _: "/usr/bin/pipx")
    calls: list[list[str]] = []
    monkeypatch.setattr(update_mod, "_run", lambda cmd: (calls.append(cmd) or ("ok", "ran")))

    action = update_mod.run_update()
    assert action.kind == "pipx"
    assert action.upgrade_cmd == ["pipx", "upgrade", "context-forge"]
    assert action.upgrade_status == "ran"
    assert calls == [["pipx", "upgrade", "context-forge"]]


def test_uv_install_invokes_uv_tool_upgrade(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "uv-tool", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod.shutil, "which", lambda _: "/usr/bin/uv")
    monkeypatch.setattr(update_mod, "_run", lambda cmd: ("ok", "ran"))

    action = update_mod.run_update()
    assert action.upgrade_cmd == ["uv", "tool", "upgrade", "context-forge"]
    assert action.upgrade_status == "ran"


def test_system_install_prints_pip_hint(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "system", tmp_path)
    _stub_self_install(monkeypatch)
    action = update_mod.run_update()
    assert action.upgrade_status == "skipped"
    assert "pip install --upgrade context-forge" in action.upgrade_output


def test_dry_run_does_not_subprocess(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "pipx", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod.shutil, "which", lambda _: "/usr/bin/pipx")
    monkeypatch.setattr(update_mod, "_run", _fail_run)
    action = update_mod.run_update(dry_run=True)
    assert action.upgrade_status == "ran"  # reported, not executed
    assert action.self_install_summary.startswith("(dry-run")


def test_pipx_unavailable_when_not_on_path(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "pipx", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod.shutil, "which", lambda _: None)
    action = update_mod.run_update()
    assert action.upgrade_status == "unavailable"


# ---------- CLI surface ----------


def test_cli_update_prints_summary(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "editable", tmp_path)
    _stub_self_install(monkeypatch, summary="claude-code  unchanged  /tmp/SKILL.md")
    runner = CliRunner()
    result = runner.invoke(main, ["update"])
    assert result.exit_code == 0, result.output
    assert "install kind: editable" in result.output
    assert "self-install:" in result.output
    assert "claude-code" in result.output


def test_cli_update_dry_run(monkeypatch, tmp_path: Path) -> None:
    _force_kind(monkeypatch, "pipx", tmp_path)
    _stub_self_install(monkeypatch)
    monkeypatch.setattr(update_mod.shutil, "which", lambda _: "/usr/bin/pipx")
    monkeypatch.setattr(update_mod, "_run", _fail_run)
    runner = CliRunner()
    result = runner.invoke(main, ["update", "--dry-run"])
    assert result.exit_code == 0, result.output


# ---------- helpers ----------


class _StubModule:
    def __init__(self, init_path: str) -> None:
        self.__file__ = init_path


def _stub_module(path: str) -> _StubModule:
    return _StubModule(path)


def _force_kind(monkeypatch, kind: str, tmp_path: Path) -> None:
    pkg_path = tmp_path / "fake" / "forge"
    pkg_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        update_mod,
        "detect_install_kind",
        lambda: update_mod.InstallKind(kind=kind, package_path=pkg_path),
    )


def _stub_self_install(monkeypatch, summary: str = "(stubbed)") -> None:
    """Replace the late-imported self_install symbols inside run_update."""
    import forge.self_install as si

    monkeypatch.setattr(si, "self_install", lambda *_a, **_kw: [])
    monkeypatch.setattr(si, "format_summary", lambda _actions: summary)


def _fail_run(_cmd: list[str]) -> tuple[str, str]:
    raise AssertionError("subprocess should not have been invoked")
