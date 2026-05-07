"""workspace-project sync: minimal awareness of external project working dirs.

A personalOS project onepage may declare an external working directory via
frontmatter:

    ---
    kind: project
    name: watermark
    upstream:
      local_dir: ~/workspace/projects/watermark/
      git_remote: https://github.com/...   # optional, human metadata
      status_sources:
        - REPORT.md
        - docs/ver1_plan.md
      staleness_days: 7         # v0.5: optional, default 7
    last_synced:
      commit: <git HEAD hash at last sync>
      at: <ISO timestamp>
      dirty_count: 24           # v0.5: number of porcelain entries at sync
      dirty_hash: <sha256>      # v0.5: sha256 of `git status --porcelain` text
    ---

This module:

  - parses project onepages (find / read frontmatter)
  - probes upstream state via subprocess git
  - builds a capture markdown for `forge capture --workspace-project <name>`
  - rewrites the onepage frontmatter to inject `last_synced` after a PR closes

It deliberately only shells out to `git` (no GitPython etc.) and never makes
network calls (no `git fetch`). State signals are local: HEAD hash, working
tree status (count + sha256 of porcelain output), `status_sources` mtimes,
and time-since-last-sync staleness.

v0.5 (working-tree-aware monitor): HEAD-only drift detection is blind to long
uncommitted dev sessions. We add (a) a hash of the `git status --porcelain`
output recorded at last sync so monitor can detect content drift in the
working tree, and (b) a staleness reminder for projects whose last_synced.at
is older than `staleness_days` (default 7).

Backward compat: onepages without `kind: project` or without `upstream:` are
silently ignored. Onepages without dirty_hash (v0.4.x format) are treated as
"never synced for working-tree purposes" — capture is suggested.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml


# v0.5: default time-since-last-sync threshold (in days) for the staleness
# reminder. Per-project override via `upstream.staleness_days: N` in onepage.
DEFAULT_STALENESS_DAYS = 7


# ---------- frontmatter helpers ----------


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, rest). frontmatter_dict is None if absent.

    Uses YAML — we need nested dicts (`upstream:`, `last_synced:`), the simple
    key:value parser used by the older `_read_frontmatter` in cli.py is too
    flat for project onepages.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError:
        return None, text
    if not isinstance(data, dict):
        return None, text
    return data, text[m.end():]


def join_frontmatter(fm: dict, body: str) -> str:
    """Inverse of split_frontmatter. Preserves YAML key order via sort_keys=False."""
    dumped = yaml.safe_dump(
        fm, sort_keys=False, allow_unicode=True, default_flow_style=False
    ).rstrip("\n")
    if body and not body.startswith("\n"):
        body = "\n" + body
    return f"---\n{dumped}\n---{body}"


# ---------- discovery ----------


@dataclass
class ProjectOnepage:
    """A loaded project onepage with its upstream metadata."""

    path: Path                           # absolute path to onepage.md
    name: str                            # `name:` field, or directory name fallback
    local_dir: Path | None               # resolved upstream.local_dir, or None
    git_remote: str = ""
    status_sources: list[str] = field(default_factory=list)
    last_synced_commit: str = ""
    last_synced_at: str = ""
    last_synced_dirty_hash: str = ""     # v0.5: sha256 of porcelain at last sync
    last_synced_dirty_count: int = 0     # v0.5: porcelain line count at last sync
    has_dirty_hash_field: bool = False   # v0.5: distinguish "missing field" vs "empty hash"
    staleness_days: int = DEFAULT_STALENESS_DAYS  # v0.5: per-project override
    frontmatter: dict = field(default_factory=dict)

    @property
    def has_upstream(self) -> bool:
        return self.local_dir is not None


def _expand(path_str: str) -> Path:
    """Expand `~` and env vars; do NOT resolve symlinks (keep original path semantic)."""
    return Path(os.path.expandvars(os.path.expanduser(path_str)))


def load_project_onepage(path: Path) -> ProjectOnepage | None:
    """Parse `path` as a project onepage. Return None if not `kind: project`.

    Tolerates malformed frontmatter (yaml errors → None, with no exception).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm, _body = split_frontmatter(text)
    if fm is None:
        return None
    if str(fm.get("kind") or "").strip() != "project":
        return None

    upstream = fm.get("upstream") or {}
    if not isinstance(upstream, dict):
        upstream = {}
    last_synced = fm.get("last_synced") or {}
    if not isinstance(last_synced, dict):
        last_synced = {}

    local_dir_raw = upstream.get("local_dir")
    local_dir: Path | None = None
    if isinstance(local_dir_raw, str) and local_dir_raw.strip():
        local_dir = _expand(local_dir_raw.strip())

    status_sources_raw = upstream.get("status_sources") or []
    if not isinstance(status_sources_raw, list):
        status_sources_raw = []
    status_sources = [str(s).strip() for s in status_sources_raw if str(s).strip()]

    name = str(fm.get("name") or "").strip() or path.parent.name

    # v0.5: optional staleness override (per-project)
    staleness_raw = upstream.get("staleness_days")
    try:
        staleness_days = (
            int(staleness_raw) if staleness_raw is not None else DEFAULT_STALENESS_DAYS
        )
    except (TypeError, ValueError):
        staleness_days = DEFAULT_STALENESS_DAYS
    if staleness_days <= 0:
        staleness_days = DEFAULT_STALENESS_DAYS

    # v0.5: optional dirty_hash / dirty_count
    has_dirty_hash_field = "dirty_hash" in last_synced
    dirty_hash = str(last_synced.get("dirty_hash") or "").strip()
    dirty_count_raw = last_synced.get("dirty_count")
    try:
        dirty_count = int(dirty_count_raw) if dirty_count_raw is not None else 0
    except (TypeError, ValueError):
        dirty_count = 0

    return ProjectOnepage(
        path=path,
        name=name,
        local_dir=local_dir,
        git_remote=str(upstream.get("git_remote") or "").strip(),
        status_sources=status_sources,
        last_synced_commit=str(last_synced.get("commit") or "").strip(),
        last_synced_at=_stringify_timestamp(last_synced.get("at")),
        last_synced_dirty_hash=dirty_hash,
        last_synced_dirty_count=dirty_count,
        has_dirty_hash_field=has_dirty_hash_field,
        staleness_days=staleness_days,
        frontmatter=fm,
    )


def _stringify_timestamp(value: object) -> str:
    """YAML auto-parses unquoted ISO 8601 strings into datetime objects.

    Normalize back to an ISO string so downstream comparisons / display are
    stable regardless of whether the user quoted the value in their onepage.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        # YAML strips the `T`; restore it for ISO 8601 conformance.
        return value.isoformat()
    return str(value).strip()


def discover_project_onepages(workspace: Path) -> list[ProjectOnepage]:
    """Scan a personalOS workspace for project onepages.

    Looks under `workspace/project/*/onepage.md`. Skips files that don't have
    `kind: project` frontmatter — they're plain narrative onepages, not the
    new schema.

    Sorted by name for deterministic output.
    """
    out: list[ProjectOnepage] = []
    project_root = workspace / "workspace" / "project"
    if not project_root.is_dir():
        return out
    for sub in sorted(project_root.iterdir()):
        if not sub.is_dir():
            continue
        op = sub / "onepage.md"
        if not op.is_file():
            continue
        loaded = load_project_onepage(op)
        if loaded is not None:
            out.append(loaded)
    return sorted(out, key=lambda p: p.name)


# ---------- upstream probing ----------


def _git(local_dir: Path, args: list[str]) -> tuple[int, str, str]:
    """Run `git <args>` in local_dir; return (returncode, stdout, stderr).

    Never raises. Caller decides what to do with non-zero.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(local_dir),
            capture_output=True,
            text=True,
        )
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)
    return proc.returncode, proc.stdout, proc.stderr


def is_git_repo(local_dir: Path) -> bool:
    if not local_dir.is_dir():
        return False
    rc, out, _ = _git(local_dir, ["rev-parse", "--is-inside-work-tree"])
    return rc == 0 and out.strip() == "true"


def head_hash(local_dir: Path) -> str | None:
    rc, out, _ = _git(local_dir, ["rev-parse", "HEAD"])
    if rc != 0:
        return None
    return out.strip() or None


def commits_between(local_dir: Path, base: str, head: str = "HEAD") -> int:
    """Count commits in (base..head]. Returns 0 if base or head missing."""
    rc, out, _ = _git(local_dir, ["rev-list", "--count", f"{base}..{head}"])
    if rc != 0:
        return 0
    try:
        return int(out.strip() or "0")
    except ValueError:
        return 0


# ---------- v0.5: working-tree (dirty) snapshot helpers ----------


def porcelain_status(local_dir: Path) -> tuple[str, int, int]:
    """Return (raw_porcelain_text, modified_count, untracked_count).

    `raw_porcelain_text` is the verbatim stdout of `git status --porcelain`.
    Counts are derived by inspecting the two-character XY status code:

      - "??" → untracked
      - everything else with a non-blank XY → modified

    Empty / failed runs return ("", 0, 0). Caller distinguishes "clean tree"
    from "couldn't run git" via current_hash etc.

    -uall: list every untracked file individually, not just the parent dir.
    Otherwise an untracked dir collapses to one entry and our drift hash
    misses inner edits.
    """
    rc, out, _ = _git(local_dir, ["status", "--porcelain", "-uall"])
    if rc != 0:
        return "", 0, 0
    modified = 0
    untracked = 0
    for line in out.splitlines():
        if not line:
            continue
        xy = line[:2]
        if xy == "??":
            untracked += 1
        elif xy.strip():
            modified += 1
    return out, modified, untracked


def compute_dirty_hash(porcelain_text: str) -> str:
    """sha256 hex of porcelain output. Empty input → empty string.

    We hash the raw bytes verbatim (no normalization). This keeps the hash
    sensitive to filename encoding, ordering, and even trailing newlines —
    any working-tree change is reflected.
    """
    if not porcelain_text:
        return ""
    return hashlib.sha256(porcelain_text.encode("utf-8")).hexdigest()


def working_tree_snapshot(local_dir: Path) -> tuple[str, int]:
    """Convenience: return (dirty_hash, dirty_count) for write-back.

    dirty_count = modified + untracked (total porcelain entry count).
    A clean tree returns ("", 0).
    """
    raw, modified, untracked = porcelain_status(local_dir)
    if not raw:
        return "", 0
    return compute_dirty_hash(raw), modified + untracked


@dataclass
class ProjectStatus:
    """Probe outcome for one project onepage."""

    onepage: ProjectOnepage
    issue: str = ""           # set when local_dir missing / not git → WARN
    commit_drift: str = ""    # set when current HEAD != last_synced.commit
    dirty_drift: str = ""     # v0.5: working tree drift since last_synced
    status_drift: list[str] = field(default_factory=list)  # status_source files newer than last_synced.at
    staleness: str = ""       # v0.5: time-since-last-sync reminder
    current_hash: str = ""    # current git HEAD (when probe succeeded)


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        # python's fromisoformat handles +00:00; strip trailing Z
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def probe_project(
    onepage: ProjectOnepage,
    *,
    now: datetime | None = None,
) -> ProjectStatus:
    """Compute drift signals for one project onepage.

    - If local_dir is unset/missing/not a git repo: status.issue is set.
    - Otherwise (priority order, strongest signal first):
        1. commit_drift  — HEAD differs from last_synced.commit
        2. dirty_drift   — git status --porcelain hash differs from
           last_synced.dirty_hash (catches long uncommitted dev work)
        3. status_drift  — declared status_sources files mtime > last_synced.at
        4. staleness     — last_synced.at older than `staleness_days` (default 7)

    All four fields populate independently so callers can surface multiple
    concerns; format_monitor_lines() picks the right priority for display.

    `now` is injectable for deterministic staleness tests; defaults to
    datetime.now(timezone.utc).

    last_synced fields being empty (i.e. never synced) counts as a commit
    drift — we report "N commits ahead since last_synced" (with N from the
    full commit count if base is unknown).
    """
    status = ProjectStatus(onepage=onepage)
    local_dir = onepage.local_dir
    if local_dir is None:
        status.issue = "upstream.local_dir not set"
        return status
    if not local_dir.exists():
        status.issue = f"local_dir does not exist: {local_dir}"
        return status
    if not is_git_repo(local_dir):
        status.issue = f"local_dir is not a git repo: {local_dir}"
        return status

    h = head_hash(local_dir)
    if h is None:
        status.issue = f"local_dir has no HEAD: {local_dir}"
        return status
    status.current_hash = h

    last_commit = onepage.last_synced_commit
    if not last_commit:
        # never synced; count whole HEAD lineage as "ahead"
        rc, out, _ = _git(local_dir, ["rev-list", "--count", "HEAD"])
        n = 0
        if rc == 0:
            try:
                n = int(out.strip() or "0")
            except ValueError:
                n = 0
        status.commit_drift = f"never synced (HEAD {h[:7]}, {n} commits)"
    elif last_commit != h:
        n = commits_between(local_dir, last_commit, "HEAD")
        if n > 0:
            status.commit_drift = (
                f"{n} commit(s) ahead since last_synced ({last_commit[:7]} → {h[:7]})"
            )
        else:
            # base might be unreachable from current HEAD (rebased / squashed)
            status.commit_drift = (
                f"HEAD differs from last_synced ({last_commit[:7]} → {h[:7]})"
            )

    # v0.5: working tree drift via porcelain hash
    raw_porcelain, modified_count, untracked_count = porcelain_status(local_dir)
    current_dirty_hash = compute_dirty_hash(raw_porcelain)
    if onepage.has_dirty_hash_field:
        if current_dirty_hash != onepage.last_synced_dirty_hash:
            status.dirty_drift = (
                f"working tree drift: {modified_count} modified, "
                f"{untracked_count} untracked since last_synced"
            )
    else:
        # Legacy v0.4.x onepage with last_synced but no dirty_hash. If the
        # working tree currently has anything, treat as drift — we have no
        # baseline so can't claim clean. If empty, stay silent (the project
        # legitimately had a clean tree at sync, common case).
        if last_commit and (modified_count + untracked_count) > 0:
            status.dirty_drift = (
                f"working tree drift: {modified_count} modified, "
                f"{untracked_count} untracked (legacy onepage, no dirty_hash baseline)"
            )

    # status_sources mtime check
    last_at = _parse_iso(onepage.last_synced_at)
    for rel in onepage.status_sources:
        f = local_dir / rel
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if last_at is None or mtime > last_at:
            status.status_drift.append(rel)

    # v0.5: staleness reminder (only when nothing else changed)
    if last_at is not None:
        if now is None:
            now = datetime.now(timezone.utc)
        # Normalize to aware datetime in UTC for safe subtraction
        if last_at.tzinfo is None:
            last_at_aware = last_at.replace(tzinfo=timezone.utc)
        else:
            last_at_aware = last_at
        if now.tzinfo is None:
            now_aware = now.replace(tzinfo=timezone.utc)
        else:
            now_aware = now
        delta_days = (now_aware - last_at_aware).total_seconds() / 86400.0
        if delta_days > onepage.staleness_days:
            status.staleness = (
                f"stale: last sync {int(delta_days)} days ago, "
                f"consider running forge capture --workspace-project {onepage.name}"
            )

    return status


def format_monitor_lines(status: ProjectStatus) -> list[str]:
    """Format ProjectStatus into monitor "next:" action lines.

    Matches the existing monitor "- workspace-project changed: <name> · ..."
    convention. Returns one line per concern.

    v0.5 priority (strongest signal first; a stronger signal suppresses
    weaker ones to keep the user's monitor surface clean):

      1. issue (warn)            — upstream broken
      2. commit_drift            — HEAD moved
      3. dirty_drift             — working tree changed since last sync
      4. status_drift            — declared status file mtime drift
      5. staleness               — time-since-last-sync reminder

    Rationale: HEAD movement implies working-tree work also happened, and
    staleness only matters when nothing more concrete is reported.
    """
    out: list[str] = []
    name = status.onepage.name
    if status.issue:
        out.append(f"workspace-project warn: {name} · {status.issue}")
        return out
    if status.commit_drift:
        out.append(f"workspace-project changed: {name} · {status.commit_drift}")
        return out
    if status.dirty_drift:
        out.append(f"workspace-project changed: {name} · {status.dirty_drift}")
        return out
    if status.status_drift:
        for rel in status.status_drift:
            out.append(
                f"workspace-project changed: {name} · status file {rel} modified"
            )
        return out
    if status.staleness:
        out.append(f"workspace-project changed: {name} · {status.staleness}")
        return out
    return out


# ---------- capture builder ----------


def build_capture_markdown(onepage: ProjectOnepage, captured_at: str) -> str:
    """Render the capture-import markdown body for one project onepage.

    Sections:
      - frontmatter (kind: raw import + provenance)
      - ## Summary  (basic identifiers + last_synced + current HEAD)
      - ## Commits since last_synced  (git log oneline)
      - ## Diff stat since last_synced (git diff --stat)
      - ## Working tree status         (git status --short)
      - ## Status sources              (per file: head 50 lines + mtime)

    On any sub-step failure (e.g. last_synced unreachable), we degrade
    gracefully — write a `(unavailable)` note rather than abort the capture.
    """
    local_dir = onepage.local_dir
    assert local_dir is not None, "build_capture_markdown requires upstream.local_dir"

    head = head_hash(local_dir) or ""
    body_parts: list[str] = []

    body_parts.append(f"# workspace-project capture: {onepage.name}\n")
    body_parts.append("## Summary\n")
    body_parts.append(f"- name: {onepage.name}")
    body_parts.append(f"- local_dir: {local_dir}")
    if onepage.git_remote:
        body_parts.append(f"- git_remote: {onepage.git_remote}")
    body_parts.append(
        f"- last_synced.commit: {onepage.last_synced_commit or '(never)'}"
    )
    body_parts.append(
        f"- last_synced.at: {onepage.last_synced_at or '(never)'}"
    )
    body_parts.append(f"- current HEAD: {head or '(unavailable)'}")
    body_parts.append("")

    base = onepage.last_synced_commit
    rev_range = f"{base}..HEAD" if base else "HEAD"

    body_parts.append("## Commits since last_synced\n")
    if base:
        rc, log_out, log_err = _git(local_dir, ["log", "--oneline", rev_range])
        if rc == 0 and log_out.strip():
            body_parts.append("```")
            body_parts.append(log_out.rstrip())
            body_parts.append("```")
        elif rc == 0:
            body_parts.append("(no new commits)")
        else:
            body_parts.append(f"(unavailable: {log_err.strip() or 'git log failed'})")
    else:
        rc, log_out, _ = _git(local_dir, ["log", "--oneline", "-n", "20"])
        if rc == 0 and log_out.strip():
            body_parts.append("(no last_synced.commit; showing last 20 commits)")
            body_parts.append("```")
            body_parts.append(log_out.rstrip())
            body_parts.append("```")
        else:
            body_parts.append("(no commit history available)")
    body_parts.append("")

    body_parts.append("## Diff stat since last_synced\n")
    if base:
        rc, diff_out, diff_err = _git(local_dir, ["diff", "--stat", rev_range])
        if rc == 0 and diff_out.strip():
            body_parts.append("```")
            body_parts.append(diff_out.rstrip())
            body_parts.append("```")
        elif rc == 0:
            body_parts.append("(no diff)")
        else:
            body_parts.append(
                f"(unavailable: {diff_err.strip() or 'git diff failed'})"
            )
    else:
        body_parts.append("(no last_synced.commit; skipping diff stat)")
    body_parts.append("")

    body_parts.append("## Working tree status\n")
    rc, st_out, st_err = _git(local_dir, ["status", "--short"])
    if rc == 0:
        if st_out.strip():
            body_parts.append("```")
            body_parts.append(st_out.rstrip())
            body_parts.append("```")
        else:
            body_parts.append("(clean)")
    else:
        body_parts.append(f"(unavailable: {st_err.strip() or 'git status failed'})")
    body_parts.append("")

    body_parts.append("## Status sources\n")
    if not onepage.status_sources:
        body_parts.append("(none declared)")
    else:
        for rel in onepage.status_sources:
            f = local_dir / rel
            body_parts.append(f"### {rel}")
            if not f.is_file():
                body_parts.append("(missing)")
                body_parts.append("")
                continue
            try:
                mtime_iso = datetime.fromtimestamp(
                    f.stat().st_mtime, tz=timezone.utc
                ).isoformat(timespec="seconds")
            except OSError:
                mtime_iso = "(stat failed)"
            body_parts.append(f"mtime: {mtime_iso}")
            body_parts.append("")
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as e:
                body_parts.append(f"(read failed: {e})")
                body_parts.append("")
                continue
            head_lines = lines[:50]
            body_parts.append("```")
            body_parts.extend(head_lines)
            if len(lines) > 50:
                body_parts.append(f"... (+{len(lines) - 50} more lines)")
            body_parts.append("```")
            body_parts.append("")

    body = "\n".join(body_parts).rstrip() + "\n"

    fm_lines = [
        "---",
        "kind: raw import",
        "type: workspace-project-update",
        f'source: "workspace-project:{onepage.name}"',
        f"workspace_project: {onepage.name}",
        f"local_dir: {local_dir}",
        f"current_hash: {head}",
        f"last_synced_commit: {onepage.last_synced_commit}",
        f"captured_at: {captured_at}",
        "status: unreviewed",
        "---",
        "",
    ]
    return "\n".join(fm_lines) + body


# ---------- last_synced write-back ----------


def update_last_synced(
    onepage_path: Path,
    *,
    commit: str,
    at: str,
    dirty_hash: str | None = None,
    dirty_count: int | None = None,
) -> bool:
    """Inject `last_synced.{commit,at,dirty_hash,dirty_count}` into a project onepage.

    Returns True if the file was modified, False if the path is not a
    project onepage (silently skipped). Preserves frontmatter key order
    (PyYAML default sort=False) and body verbatim.

    v0.5: when dirty_hash / dirty_count are provided they are written
    alongside commit + at, so a future monitor pass can detect working-tree
    drift via porcelain hash comparison. Callers without an upstream working
    tree (rare; legacy v0.4 paths) can omit them and stay v0.4-compatible.
    """
    try:
        text = onepage_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fm, body = split_frontmatter(text)
    if fm is None:
        return False
    if str(fm.get("kind") or "").strip() != "project":
        return False

    fm = dict(fm)  # shallow copy; we mutate
    new_last_synced: dict = {"commit": commit, "at": at}
    if dirty_hash is not None:
        new_last_synced["dirty_hash"] = dirty_hash
        new_last_synced["dirty_count"] = (
            dirty_count if dirty_count is not None else 0
        )
    fm["last_synced"] = new_last_synced
    new_text = join_frontmatter(fm, body)
    onepage_path.write_text(new_text, encoding="utf-8")
    return True


# ---------- v0.5.1: legacy schema auto-migration ----------


@dataclass
class MigrateOnepageOutcome:
    """Per-onepage result of `forge migrate-onepage`.

    status:
      "upgraded"     — was legacy, dirty_hash + dirty_count written
      "current"      — already on v0.5 schema (has dirty_hash field)
      "no-baseline"  — has no last_synced.commit (never synced); not a legacy
                       case. Capture/sync establishes the baseline; we don't
                       fabricate one.
      "warn"         — onepage has last_synced but upstream is unreachable
                       (local_dir missing / not a git repo / no HEAD). Skipped.
    """

    onepage_path: Path
    name: str
    status: str
    detail: str = ""           # human-readable note (e.g. computed dirty_count)
    dirty_hash: str = ""       # only set when status == "upgraded"
    dirty_count: int = 0       # only set when status == "upgraded"


@dataclass
class MigrateOnepageReport:
    """Aggregate result of a migration pass."""

    upgraded: list[MigrateOnepageOutcome] = field(default_factory=list)
    current: list[MigrateOnepageOutcome] = field(default_factory=list)
    no_baseline: list[MigrateOnepageOutcome] = field(default_factory=list)
    warns: list[MigrateOnepageOutcome] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            len(self.upgraded)
            + len(self.current)
            + len(self.no_baseline)
            + len(self.warns)
        )


def _is_legacy_onepage(op: ProjectOnepage) -> bool:
    """A onepage is "legacy" iff it has been synced (last_synced.commit set)
    but lacks the v0.5 dirty_hash field. Onepages that have never synced are
    NOT legacy — capture / approve will establish a v0.5 baseline naturally.
    """
    return bool(op.last_synced_commit) and not op.has_dirty_hash_field


def count_legacy_onepages(workspace: Path) -> int:
    """How many project onepages still use the v0.4.x schema (no dirty_hash).

    Used by `forge monitor` to suggest running `forge migrate-onepage`.
    Cheap: parses frontmatter only, no git calls.
    """
    n = 0
    for op in discover_project_onepages(workspace):
        if op.has_upstream and _is_legacy_onepage(op):
            n += 1
    return n


def migrate_legacy_onepage_schema(
    workspace: Path,
    *,
    dry_run: bool = False,
    now_iso: str | None = None,
) -> MigrateOnepageReport:
    """Backfill v0.5 dirty_hash + dirty_count on every legacy project onepage.

    For each onepage under `workspace/project/*/onepage.md`:

      - If `last_synced.commit` is empty → status="no-baseline", skip.
        (Capture/sync will create the v0.5 baseline; nothing mechanical to do.)
      - If `last_synced.dirty_hash` is already present → status="current", skip.
      - Otherwise (legacy v0.4.x, has commit but no dirty_hash):
          - Probe `upstream.local_dir` for current porcelain snapshot.
          - If unreachable → status="warn", skip (user must fix local_dir).
          - Else → write back `last_synced.{commit, at, dirty_hash, dirty_count}`
            inline (no PR review). `commit` keeps its existing value;
            `at` is bumped to `now_iso` (or current UTC) so monitor's
            staleness reminder also resets.

    The onepage's frontmatter is mutated in place via `update_last_synced` —
    no PR proposal is created, no inbox event is logged. This is a pure
    mechanical schema upgrade with zero design decisions for the user to
    review (rationale: the user has no input that would change the result;
    we're just writing a hash of what's already on disk).

    `dry_run=True` performs all probes but writes nothing.
    """
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    report = MigrateOnepageReport()
    for op in discover_project_onepages(workspace):
        if not op.has_upstream:
            # No upstream declared → not in scope for this migration. Treat
            # as "current" (nothing to migrate) so totals stay sensible.
            report.current.append(
                MigrateOnepageOutcome(
                    onepage_path=op.path,
                    name=op.name,
                    status="current",
                    detail="no upstream declared",
                )
            )
            continue

        if op.has_dirty_hash_field:
            report.current.append(
                MigrateOnepageOutcome(
                    onepage_path=op.path,
                    name=op.name,
                    status="current",
                    detail="already on v0.5 schema",
                )
            )
            continue

        if not op.last_synced_commit:
            report.no_baseline.append(
                MigrateOnepageOutcome(
                    onepage_path=op.path,
                    name=op.name,
                    status="no-baseline",
                    detail="never synced; capture/sync will establish v0.5 baseline",
                )
            )
            continue

        # Legacy onepage. Probe upstream.
        local_dir = op.local_dir
        assert local_dir is not None  # has_upstream guarded
        if not local_dir.exists():
            report.warns.append(
                MigrateOnepageOutcome(
                    onepage_path=op.path,
                    name=op.name,
                    status="warn",
                    detail=f"local_dir does not exist: {local_dir}",
                )
            )
            continue
        if not is_git_repo(local_dir):
            report.warns.append(
                MigrateOnepageOutcome(
                    onepage_path=op.path,
                    name=op.name,
                    status="warn",
                    detail=f"local_dir is not a git repo: {local_dir}",
                )
            )
            continue

        dirty_hash, dirty_count = working_tree_snapshot(local_dir)
        outcome = MigrateOnepageOutcome(
            onepage_path=op.path,
            name=op.name,
            status="upgraded",
            detail=f"dirty_count={dirty_count}",
            dirty_hash=dirty_hash,
            dirty_count=dirty_count,
        )

        if not dry_run:
            ok = update_last_synced(
                op.path,
                commit=op.last_synced_commit,
                at=now_iso,
                dirty_hash=dirty_hash,
                dirty_count=dirty_count,
            )
            if not ok:
                # Should not happen — load_project_onepage already validated
                # `kind: project`, but be defensive.
                report.warns.append(
                    MigrateOnepageOutcome(
                        onepage_path=op.path,
                        name=op.name,
                        status="warn",
                        detail="update_last_synced refused (frontmatter mismatch)",
                    )
                )
                continue

        report.upgraded.append(outcome)

    return report


def find_modified_project_onepages(workspace: Path) -> list[Path]:
    """List project onepages currently changed in the working tree (vs HEAD).

    Returns absolute paths under `workspace/project/*/onepage.md` that:
      - have `kind: project` frontmatter, AND
      - show as modified or untracked in `git status --porcelain` (when
        `workspace` is a git repo).

    If `workspace` is NOT a git repo, returns an empty list (we have no
    cheap way to detect modification).
    """
    project_root = workspace / "workspace" / "project"
    if not project_root.is_dir():
        return []

    rc, out, _ = _git(workspace, ["rev-parse", "--is-inside-work-tree"])
    if rc != 0 or out.strip() != "true":
        return []

    # -uall: list every untracked file individually, not just the parent dir
    rc, status_out, _ = _git(workspace, ["status", "--porcelain", "-uall"])
    if rc != 0:
        return []

    modified: list[Path] = []
    for line in status_out.splitlines():
        if not line.strip():
            continue
        # porcelain v1: "XY <path>" or "XY <orig> -> <new>" for renames
        rel_part = line[3:]
        if " -> " in rel_part:
            rel_part = rel_part.split(" -> ", 1)[1]
        rel_part = rel_part.strip().strip('"')
        candidate = workspace / rel_part
        try:
            rel = candidate.resolve().relative_to(workspace.resolve())
        except (OSError, ValueError):
            continue
        # interested only in workspace/project/*/onepage.md
        parts = rel.parts
        if (
            len(parts) == 4
            and parts[0] == "workspace"
            and parts[1] == "project"
            and parts[3] == "onepage.md"
        ):
            absolute = workspace / rel
            loaded = load_project_onepage(absolute)
            if loaded is not None:
                modified.append(absolute)
    return modified
