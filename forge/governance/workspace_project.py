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
    last_synced:
      commit: <git HEAD hash at last sync>
      at: <ISO timestamp>
    ---

This module:

  - parses project onepages (find / read frontmatter)
  - probes upstream state via subprocess git
  - builds a capture markdown for `forge capture --workspace-project <name>`
  - rewrites the onepage frontmatter to inject `last_synced` after a PR closes

It deliberately only shells out to `git` (no GitPython etc.) and never makes
network calls (no `git fetch`). State signals are local: HEAD hash, working
tree status, and `status_sources` mtimes.

Backward compat: onepages without `kind: project` or without `upstream:` are
silently ignored — old hand-written onepages keep working unchanged.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import yaml


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

    return ProjectOnepage(
        path=path,
        name=name,
        local_dir=local_dir,
        git_remote=str(upstream.get("git_remote") or "").strip(),
        status_sources=status_sources,
        last_synced_commit=str(last_synced.get("commit") or "").strip(),
        last_synced_at=_stringify_timestamp(last_synced.get("at")),
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


@dataclass
class ProjectStatus:
    """Probe outcome for one project onepage."""

    onepage: ProjectOnepage
    issue: str = ""           # set when local_dir missing / not git → WARN
    commit_drift: str = ""    # set when current HEAD != last_synced.commit
    status_drift: list[str] = field(default_factory=list)  # status_source files newer than last_synced.at
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


def probe_project(onepage: ProjectOnepage) -> ProjectStatus:
    """Compute drift signals for one project onepage.

    - If local_dir is unset/missing/not a git repo: status.issue is set.
    - Otherwise: compute commit drift (HEAD vs last_synced.commit) and
      status_sources mtime drift (file newer than last_synced.at).

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

    # status_sources mtime check
    last_at = _parse_iso(onepage.last_synced_at)
    for rel in onepage.status_sources:
        f = local_dir / rel
        if not f.is_file():
            continue
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if last_at is None or mtime > last_at:
            status.status_drift.append(rel)

    return status


def format_monitor_lines(status: ProjectStatus) -> list[str]:
    """Format ProjectStatus into monitor "next:" action lines.

    Matches the existing monitor "- workspace-project changed: <name> · ..."
    convention. Returns one line per concern (commit drift, status drift,
    or upstream issue).
    """
    out: list[str] = []
    name = status.onepage.name
    if status.issue:
        out.append(f"workspace-project warn: {name} · {status.issue}")
        return out
    if status.commit_drift:
        out.append(f"workspace-project changed: {name} · {status.commit_drift}")
    for rel in status.status_drift:
        out.append(f"workspace-project changed: {name} · status file {rel} modified")
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
) -> bool:
    """Inject `last_synced.commit` + `last_synced.at` into a project onepage.

    Returns True if the file was modified, False if the path is not a
    project onepage (silently skipped). Preserves frontmatter key order
    (PyYAML default sort=False) and body verbatim.
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
    fm["last_synced"] = {"commit": commit, "at": at}
    new_text = join_frontmatter(fm, body)
    onepage_path.write_text(new_text, encoding="utf-8")
    return True


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
