"""self-install: bind forge-as-skill into agent runtime entrypoints.

This is **not** content sync (canonical → compiled view → ~/.claude/CLAUDE.md);
that lives in `forge/gate/sync.py` + `forge target install`. This module's
concern is the inverse: telling the agent runtime *how to drive forge*. It
writes forge's own SKILL.md (or runtime equivalent) to a discoverable global
location so the agent can pick it up.

Currently supports: claude-code (~/.claude/skills/forge/SKILL.md). Other
runtimes (codex AGENTS.md, cursor .cursor/rules) are detected and surfaced
in the summary but not auto-written — those entrypoints are project-level or
require opt-in semantics that aren't yet designed.

Manifest: ~/.forge/manifest.json. Tracks each runtime binding so re-runs are
idempotent and `forge update` can refresh deterministically.

Managed marker: every file we write carries

    <!-- managed-by: forge -->
    <!-- forge-runtime: <name> -->

A file with the marker is ours to overwrite; a file without it is the user's
and we report conflict instead of clobbering.
"""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from forge import __version__


MANAGED_MARKER_RE = re.compile(r"<!--\s*managed-by:\s*forge\s*-->")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _packaged_skill_source() -> Path:
    """Path to packaged SKILL.md asset shipped with the wheel."""
    return Path(__file__).parent / "assets" / "skills" / "forge" / "SKILL.md"


def _inject_marker(skill_text: str, runtime_name: str) -> str:
    """Insert managed-marker comments right after the frontmatter close.

    SKILL.md begins with `---\\n...---\\n`; we put the marker between that
    block and the body, separated by a blank line. If frontmatter is missing
    we prepend the marker at the top.
    """
    marker = (
        f"<!-- managed-by: forge -->\n"
        f"<!-- forge-runtime: {runtime_name} -->\n"
        f"<!-- forge-version: {__version__} -->\n"
    )
    m = re.match(r"^---\n.*?\n---\n", skill_text, re.DOTALL)
    if not m:
        return marker + "\n" + skill_text
    end = m.end()
    return skill_text[:end] + marker + "\n" + skill_text[end:]


# ---------- Runtime adapters ----------


@dataclass
class RuntimeAction:
    """Outcome of a single runtime install pass."""
    runtime: str
    target: Path
    status: str  # detected | installed | updated | unchanged | skipped | conflict
    detail: str = ""


class SkillRuntime(ABC):
    """One agent-runtime adapter for forge-as-skill."""
    name: str = ""

    @abstractmethod
    def detect(self, home: Path) -> bool:
        """Return True if the runtime appears installed for this user."""

    @abstractmethod
    def target_path(self, home: Path) -> Path:
        """Where the skill file should live for this runtime."""

    @abstractmethod
    def render(self) -> str:
        """Skill content with managed marker applied."""


class ClaudeCodeRuntime(SkillRuntime):
    name = "claude-code"

    def detect(self, home: Path) -> bool:
        return (home / ".claude").is_dir()

    def target_path(self, home: Path) -> Path:
        return home / ".claude" / "skills" / "forge" / "SKILL.md"

    def render(self) -> str:
        src = _packaged_skill_source()
        if not src.exists():
            raise FileNotFoundError(
                f"packaged skill asset missing at {src}. "
                "Reinstall forge from a release wheel or `pip install -e .` from source."
            )
        return _inject_marker(src.read_text(encoding="utf-8"), self.name)


# Registry of supported runtimes. To add a new one, subclass SkillRuntime
# and append here.
RUNTIMES: list[SkillRuntime] = [
    ClaudeCodeRuntime(),
]


# ---------- Manifest ----------


def manifest_path(home: Path) -> Path:
    return home / ".forge" / "manifest.json"


def _read_manifest(home: Path) -> dict:
    p = manifest_path(home)
    if not p.exists():
        return {"version": 1, "runtimes": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "runtimes": {}}
    data.setdefault("version", 1)
    data.setdefault("runtimes", {})
    return data


def _write_manifest(home: Path, data: dict) -> None:
    p = manifest_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ---------- Core install ----------


def self_install(
    home: Path | None = None,
    *,
    dry_run: bool = False,
    force: bool = False,
    only: list[str] | None = None,
) -> list[RuntimeAction]:
    """Idempotently install forge-as-skill into every detected runtime.

    Args:
        home: user HOME (defaults to Path.home()). Overridable for tests.
        dry_run: report what would happen, write nothing.
        force: overwrite even when the existing file lacks a managed marker.
        only: restrict to a subset of runtime names.

    Returns: per-runtime action list.

    Status values:
      - detected: runtime detected, would install (dry-run only)
      - installed: file did not exist, freshly written
      - updated: file existed with managed marker, content rewritten
      - unchanged: file already up-to-date (content sha matches)
      - skipped: runtime not detected on this machine
      - conflict: file exists without managed marker; not overwritten
    """
    home = home or Path.home()
    manifest = _read_manifest(home)
    runtimes = [r for r in RUNTIMES if not only or r.name in only]
    actions: list[RuntimeAction] = []

    for rt in runtimes:
        target = rt.target_path(home)
        if not rt.detect(home):
            actions.append(RuntimeAction(rt.name, target, "skipped", "runtime not detected"))
            continue

        try:
            new_content = rt.render()
        except FileNotFoundError as e:
            actions.append(RuntimeAction(rt.name, target, "conflict", str(e)))
            continue

        existing = target.read_text(encoding="utf-8") if target.exists() else None

        # Migrate users from the old `forge install-skill`: that command wrote
        # the packaged asset verbatim (no marker). If existing content matches
        # the packaged source byte-for-byte, treat it as ours and auto-adopt.
        legacy_match = (
            existing is not None
            and not MANAGED_MARKER_RE.search(existing)
            and _matches_packaged_asset(existing)
        )

        if existing is None:
            status = "detected" if dry_run else "installed"
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_content, encoding="utf-8")
            actions.append(RuntimeAction(rt.name, target, status, "fresh install"))
        elif _sha256(existing) == _sha256(new_content):
            actions.append(RuntimeAction(rt.name, target, "unchanged", "already up-to-date"))
            # still record presence in manifest below
        elif MANAGED_MARKER_RE.search(existing) or _was_managed_previously(manifest, rt.name, target) or legacy_match or force:
            status = "detected" if dry_run else "updated"
            if not dry_run:
                target.write_text(new_content, encoding="utf-8")
            note = "managed file refreshed"
            if legacy_match:
                note = "migrated legacy `install-skill` output"
            elif force and not MANAGED_MARKER_RE.search(existing):
                note = "force-overwrote unmanaged file"
            actions.append(RuntimeAction(rt.name, target, status, note))
        else:
            actions.append(
                RuntimeAction(
                    rt.name,
                    target,
                    "conflict",
                    "file exists without managed-by marker; refusing to overwrite (use --force)",
                )
            )

        # Update manifest entry for any non-conflict outcome (including unchanged + dry-run)
        if not dry_run and actions[-1].status != "conflict":
            manifest["runtimes"][rt.name] = {
                "path": str(target),
                "forge_version": __version__,
                "content_sha": _sha256(new_content),
                "installed_at": _now_iso(),
            }

    if not dry_run and any(a.status not in ("skipped", "conflict") for a in actions):
        manifest["last_self_install_at"] = _now_iso()
        _write_manifest(home, manifest)

    return actions


def _matches_packaged_asset(existing: str) -> bool:
    """True if `existing` equals the packaged SKILL.md verbatim — i.e. it was
    written by the old `forge install-skill` command, before managed markers
    existed."""
    src = _packaged_skill_source()
    if not src.exists():
        return False
    try:
        return src.read_text(encoding="utf-8") == existing
    except OSError:
        return False


def _was_managed_previously(manifest: dict, runtime_name: str, target: Path) -> bool:
    """True if our manifest already claims this binding — implies we wrote it
    before the managed marker was introduced. Lets old `install-skill` users
    migrate cleanly to `self-install`."""
    entry = manifest.get("runtimes", {}).get(runtime_name)
    if not entry:
        return False
    return Path(entry.get("path", "")) == target


def format_summary(actions: list[RuntimeAction]) -> str:
    """One-screen text summary of an install run."""
    if not actions:
        return "no runtimes configured."
    width = max(len(a.runtime) for a in actions)
    lines = []
    for a in actions:
        lines.append(f"  {a.runtime:<{width}}  {a.status:<10}  {a.target}")
        if a.detail and a.status not in ("unchanged", "installed"):
            lines.append(f"  {' ':<{width}}  └─ {a.detail}")
    return "\n".join(lines)
