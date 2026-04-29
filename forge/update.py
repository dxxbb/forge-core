"""forge update: refresh the CLI binary, then re-run self-install.

Detects how forge was installed and dispatches to the appropriate package
manager. Editable / dev installs are NEVER auto-overwritten — we print a
hint and skip the upgrade step, then still refresh skills via self-install
(safe and useful).

Supported install kinds:
    pipx        → pipx upgrade context-forge
    uv-tool     → uv tool upgrade context-forge
    editable    → no-op (warn + run self-install)
    system      → print pip command (don't run pip on the user's interpreter)
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import forge


PACKAGE_NAME = "context-forge"


@dataclass
class InstallKind:
    kind: str  # pipx | uv-tool | editable | system
    package_path: Path
    note: str = ""


def detect_install_kind() -> InstallKind:
    pkg_path = Path(forge.__file__).resolve().parent
    posix = pkg_path.as_posix()

    if "/pipx/venvs/" in posix or "\\pipx\\venvs\\" in posix:
        return InstallKind("pipx", pkg_path, "managed by pipx")
    if "/uv/tools/" in posix or "\\uv\\tools\\" in posix:
        return InstallKind("uv-tool", pkg_path, "managed by uv tool")

    # Editable / dev install: the package directory sits inside a git repo
    # we own (the forge-core source tree).
    walker = pkg_path
    for _ in range(6):
        if (walker / ".git").exists():
            return InstallKind("editable", pkg_path, f"editable install rooted at {walker}")
        if walker.parent == walker:
            break
        walker = walker.parent

    return InstallKind("system", pkg_path, "system / user-site install")


@dataclass
class UpdateAction:
    kind: str
    upgrade_cmd: list[str] | None
    upgrade_status: str  # ran | skipped | unavailable
    upgrade_output: str = ""
    self_install_summary: str = ""


def run_update(*, dry_run: bool = False) -> UpdateAction:
    """Pick the right upgrade strategy for this install, run it, refresh skills.

    Returns a structured action so the CLI layer can render whatever output
    style it wants and tests can assert on the chosen strategy.
    """
    info = detect_install_kind()
    cmd: list[str] | None = None
    status = "skipped"
    output = ""

    if info.kind == "pipx":
        if shutil.which("pipx"):
            cmd = ["pipx", "upgrade", PACKAGE_NAME]
            if not dry_run:
                output, status = _run(cmd)
            else:
                status = "ran"  # for dry-run reporting only
        else:
            status = "unavailable"
            output = "pipx not on PATH; reinstall pipx or rerun forge update."
    elif info.kind == "uv-tool":
        if shutil.which("uv"):
            cmd = ["uv", "tool", "upgrade", PACKAGE_NAME]
            if not dry_run:
                output, status = _run(cmd)
            else:
                status = "ran"
        else:
            status = "unavailable"
            output = "uv not on PATH; reinstall uv or rerun forge update."
    elif info.kind == "editable":
        status = "skipped"
        output = (
            f"editable install at {info.package_path.parent}. "
            "Pull from upstream there (e.g. `git pull`) to update the CLI; "
            "this command will not overwrite source you control."
        )
    else:  # system
        status = "skipped"
        output = (
            f"detected a system / user-site install at {info.package_path}. "
            f"Run: pip install --upgrade {PACKAGE_NAME}  "
            f"(or pipx install {PACKAGE_NAME} for an isolated install)"
        )

    # Refresh skill bindings regardless — fast and idempotent.
    if not dry_run:
        from forge.self_install import self_install, format_summary
        actions = self_install()
        summary = format_summary(actions)
    else:
        summary = "(dry-run: skill refresh skipped)"

    return UpdateAction(
        kind=info.kind,
        upgrade_cmd=cmd,
        upgrade_status=status,
        upgrade_output=output,
        self_install_summary=summary,
    )


def _run(cmd: list[str]) -> tuple[str, str]:
    """Run a subprocess; return (combined-output, status)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        return f"command not found: {e}", "unavailable"
    out = (p.stdout + p.stderr).strip()
    status = "ran" if p.returncode == 0 else "failed"
    return out, status
