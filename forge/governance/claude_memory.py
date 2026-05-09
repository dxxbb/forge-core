"""Claude Code auto-memory as a first-class governed source.

Claude Code writes auto-memory markdown files under
`~/.claude/projects/<slug>/memory/*.md`. These files persist across sessions
and are injected into every new Claude session's context — they directly
shape future agent behavior. Per forge's review-gated thesis, any source
that becomes long-term agent context must go through the same
capture → inbox → PR → review pipeline as workspace-project drift, web
clippings, and internal content changes.

This module wires that path. Pattern mirrors `web_clipping.py` and
`workspace_project.py`:

  - discover memory files for a workspace's matched Claude project
  - hash-diff against a sidecar state file at `.forge/agent_memory_state.json`
  - report new / modified files via `format_monitor_lines(workspace)`
  - first activation establishes a baseline (no inbox flood — the user has
    been operating without monitor coverage; existing memory is taken as the
    starting state, going forward only deltas surface)

State file vs in-source frontmatter (deviation from web_clipping /
workspace_project): Claude rewrites memory files autonomously, so any
state we wrote into a memory file's frontmatter would be overwritten on
the next agent edit. We keep the state in `.forge/agent_memory_state.json`
(workspace-local, gitignored, alongside `manifest.json`).

Scope: only the Claude project slug matching the personalOS workspace path
(slug = absolute path with `/` → `-`, e.g. `/Users/<user>/personalOS` becomes
`-Users-<user>-personalOS`). Other Claude project slugs are not watched by
default. Cross-slug coverage is a future option.

Forge runtime outputs (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`) are NOT
watched — they're forge-authored, not agent-written, and watching them
would create a self-loop.

Convention: `MEMORY.md` (the index file written by Claude's auto-memory
system) is silently excluded — it's an index, not feedback content, and
fluctuates whenever any feedback file is added or removed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Memory files that are indexes, not content. Excluded from monitor reports
# and from baseline tracking.
_EXCLUDED_NAMES = frozenset({"MEMORY.md"})


def _claude_projects_root() -> Path:
    """Where Claude Code stores per-project memory + transcripts."""
    return Path.home() / ".claude" / "projects"


def workspace_to_slug(workspace: Path) -> str:
    """Convert an absolute personalOS workspace path to its Claude project slug.

    Claude Code derives project slugs by replacing `/` with `-` in the
    absolute workspace path, e.g.:
      /Users/<user>/personalOS  →  -Users-<user>-personalOS
    """
    abs_path = str(workspace.resolve())
    return abs_path.replace("/", "-")


def memory_dir_for_slug(slug: str) -> Path:
    return _claude_projects_root() / slug / "memory"


# ---------- data ----------


@dataclass
class MemoryFile:
    """A single auto-memory file under `~/.claude/projects/<slug>/memory/`."""

    path: Path                 # absolute path
    slug: str                  # project slug (e.g. -Users-alice-personalOS)
    name: str                  # filename (basename)
    size: int                  # bytes
    sha256: str                # content hash

    @property
    def display(self) -> str:
        """Concise label for monitor output (`<slug>/<name>`)."""
        return f"{self.slug}/{self.name}"


def _hash_file(path: Path) -> str:
    """sha256 hex of file content. Empty / unreadable → empty string."""
    try:
        data = path.read_bytes()
    except (OSError, UnicodeDecodeError):
        return ""
    return hashlib.sha256(data).hexdigest()


def discover_memory_files(slug: str) -> list[MemoryFile]:
    """List all auto-memory files for a Claude project slug.

    Excludes `MEMORY.md` (index, not content). Returns empty list if the
    slug's memory dir doesn't exist (legitimate: user has never had a
    Claude session in that workspace).

    Files are sorted by name for stable output.
    """
    out: list[MemoryFile] = []
    mem_dir = memory_dir_for_slug(slug)
    if not mem_dir.is_dir():
        return out
    for p in sorted(mem_dir.glob("*.md")):
        if not p.is_file():
            continue
        if p.name in _EXCLUDED_NAMES:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        h = _hash_file(p)
        if not h:
            continue
        out.append(MemoryFile(path=p, slug=slug, name=p.name, size=size, sha256=h))
    return out


# ---------- state file (.forge/agent_memory_state.json) ----------


_STATE_REL_PATH = (".forge", "agent_memory_state.json")
_STATE_SCHEMA_VERSION = 1


def state_path(workspace: Path) -> Path:
    return workspace.joinpath(*_STATE_REL_PATH)


@dataclass
class MemoryState:
    """Persisted view of which memory files we've already snapshotted."""

    schema_version: int = _STATE_SCHEMA_VERSION
    # Keyed by absolute path string. Value: {"hash": ..., "size": ..., "seen_at": ...}
    last_seen: dict[str, dict] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "last_seen": self.last_seen,
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "MemoryState":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        last_seen_raw = data.get("last_seen") or {}
        if not isinstance(last_seen_raw, dict):
            last_seen_raw = {}
        # Sanitize entries
        last_seen: dict[str, dict] = {}
        for k, v in last_seen_raw.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            last_seen[k] = {
                "hash": str(v.get("hash") or ""),
                "size": int(v.get("size") or 0) if isinstance(v.get("size"), (int, float)) else 0,
                "seen_at": str(v.get("seen_at") or ""),
            }
        return cls(
            schema_version=int(data.get("schema_version") or _STATE_SCHEMA_VERSION),
            last_seen=last_seen,
        )


def load_state(workspace: Path) -> MemoryState | None:
    """Load `.forge/agent_memory_state.json`. Return None if missing
    (signals "first activation"). Return empty MemoryState if present but
    unreadable / malformed (we don't crash monitor on a bad state file).
    """
    p = state_path(workspace)
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return MemoryState()
    return MemoryState.from_json(raw)


def save_state(workspace: Path, state: MemoryState) -> None:
    """Atomic-ish write of state file. Creates `.forge/` if needed."""
    p = state_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(state.to_json() + "\n", encoding="utf-8")
    tmp.replace(p)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mark_seen(workspace: Path, files: list[MemoryFile]) -> None:
    """Record current hashes for `files` in the state file (creating it if
    needed). Existing entries for unrelated files are preserved.

    Used by:
      - first-activation baseline (all current files snapshotted at once)
      - capture-time mark-seen (a single file when user runs
        `forge capture --from <memory file>`)
    """
    state = load_state(workspace) or MemoryState()
    now = _now_iso()
    for f in files:
        state.last_seen[str(f.path)] = {
            "hash": f.sha256,
            "size": f.size,
            "seen_at": now,
        }
    save_state(workspace, state)


def is_memory_file(path: Path) -> bool:
    """True if `path` lives under `~/.claude/projects/*/memory/` and isn't
    in the excluded names. Used by capture to decide whether to mark-seen.

    Tolerates both absolute and resolved paths; uses parent chain.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if resolved.name in _EXCLUDED_NAMES:
        return False
    if resolved.suffix != ".md":
        return False
    parent = resolved.parent
    if parent.name != "memory":
        return False
    grandparent = parent.parent
    if not grandparent.exists():
        return False
    great = grandparent.parent
    try:
        return great.resolve() == _claude_projects_root().resolve()
    except OSError:
        return False


def slug_for_memory_path(path: Path) -> str:
    """Extract the project slug from a memory file path.
    `<...>/.claude/projects/<slug>/memory/foo.md` → "<slug>".
    Empty string if the path doesn't fit the layout.
    """
    if not is_memory_file(path):
        return ""
    return path.resolve().parent.parent.name


def mark_path_seen(workspace: Path, memory_path: Path) -> bool:
    """Convenience wrapper for capture-time mark-seen. Hashes the file at
    `memory_path` and records it in state.

    Returns True on success, False if the path isn't a memory file or is
    unreadable. Does NOT raise — capture should proceed even on failure.
    """
    if not is_memory_file(memory_path):
        return False
    try:
        size = memory_path.stat().st_size
    except OSError:
        return False
    h = _hash_file(memory_path)
    if not h:
        return False
    slug = slug_for_memory_path(memory_path)
    f = MemoryFile(
        path=memory_path.resolve(),
        slug=slug,
        name=memory_path.name,
        size=size,
        sha256=h,
    )
    mark_seen(workspace, [f])
    return True


# ---------- diff: report new / modified files ----------


@dataclass
class MemoryDiff:
    """Result of comparing current files to state baseline."""

    new: list[MemoryFile] = field(default_factory=list)
    modified: list[MemoryFile] = field(default_factory=list)
    # Note: deleted files are silent — we don't surface them in monitor
    # (they're not actionable; the agent removed them, that's a normal
    # workflow event). They DO get cleaned out of state on the next sync
    # via `prune_state_for_slug`.


def compute_diff(workspace: Path, slug: str, state: MemoryState) -> MemoryDiff:
    """Diff current memory files for `slug` against `state.last_seen`."""
    diff = MemoryDiff()
    for f in discover_memory_files(slug):
        key = str(f.path)
        prev = state.last_seen.get(key)
        if prev is None:
            diff.new.append(f)
        elif prev.get("hash") != f.sha256:
            diff.modified.append(f)
    return diff


def prune_state_for_slug(state: MemoryState, slug: str) -> int:
    """Drop state entries for files under `slug`'s memory dir that no longer
    exist on disk. Returns count pruned. Mutates `state` in place.

    Other slugs' entries are untouched.
    """
    target_dir = memory_dir_for_slug(slug)
    target_str = str(target_dir.resolve()) if target_dir.exists() else str(target_dir)
    drop: list[str] = []
    for key in list(state.last_seen.keys()):
        # Only consider keys under this slug's memory dir
        try:
            kp = Path(key)
        except (OSError, ValueError):
            continue
        if str(kp.parent) != target_str and str(kp.parent.resolve() if kp.parent.exists() else kp.parent) != target_str:
            continue
        if not kp.exists():
            drop.append(key)
    for k in drop:
        del state.last_seen[k]
    return len(drop)


# ---------- monitor formatting ----------


def format_monitor_lines(workspace: Path) -> tuple[list[str], list[str]]:
    """Return (issue_lines, action_lines) for `forge monitor` agent-memory section.

    Behavior:

      1. Resolve the Claude project slug from `workspace` path.
      2. If state file does NOT exist (first activation): snapshot all
         current memory files into state and return a one-line info issue
         (`agent-memory: initialized baseline (N files tracked)`). No
         per-file actions — the user has been operating without monitor
         coverage; existing files are NOT retroactively pushed through PR.
      3. Otherwise, diff current files against state. Surface new and
         modified files as inbox-worthy actions.
      4. If no Claude project dir exists for this workspace's slug, return
         empty (silent).
      5. State pruning (deleted files) happens silently as a side-effect of
         the diff/save cycle — no monitor noise.

    Returns ([], []) when:
      - the workspace has no matching Claude project, OR
      - the state file exists and there's no drift since last seen.
    """
    slug = workspace_to_slug(workspace)
    mem_dir = memory_dir_for_slug(slug)
    if not mem_dir.is_dir():
        return [], []

    state = load_state(workspace)

    if state is None:
        # First activation: baseline current files, do not flood inbox.
        current = discover_memory_files(slug)
        if not current:
            # Empty memory dir; still write an empty state so subsequent
            # additions are detected as new (not as another baseline).
            save_state(workspace, MemoryState())
            return [], []
        mark_seen(workspace, current)
        n = len(current)
        files_label = "file" if n == 1 else "files"
        return (
            [f"agent-memory: initialized baseline ({n} {files_label} tracked)"],
            [],
        )

    diff = compute_diff(workspace, slug, state)
    if not diff.new and not diff.modified:
        # Opportunistic pruning: drop state entries for deleted files.
        if prune_state_for_slug(state, slug) > 0:
            save_state(workspace, state)
        return [], []

    issues: list[str] = []
    actions: list[str] = []
    total = len(diff.new) + len(diff.modified)
    parts: list[str] = []
    if diff.new:
        parts.append(f"new {len(diff.new)}")
    if diff.modified:
        parts.append(f"modified {len(diff.modified)}")
    issues.append(f"agent-memory updates: {total} ({', '.join(parts)})")

    # Cap at 5 per category to keep monitor surface readable
    for f in diff.new[:5]:
        actions.append(f'agent-memory NEW: {f.display} · forge capture --from "{f.path}"')
    if len(diff.new) > 5:
        actions.append(f"  ... and {len(diff.new) - 5} more new agent-memory files")
    for f in diff.modified[:5]:
        actions.append(f'agent-memory MODIFIED: {f.display} · forge capture --from "{f.path}"')
    if len(diff.modified) > 5:
        actions.append(f"  ... and {len(diff.modified) - 5} more modified agent-memory files")

    return issues, actions


# ---------- compatibility shims (used by `forge ingest --detect` etc.) ----------
# These mirror the cli.py helpers they replaced, so existing callers keep working.


def scan_all_projects() -> list[tuple[str, int, int]]:
    """Return [(project_slug, file_count, total_bytes), ...] across ALL
    Claude projects (not scoped to current workspace). Used by
    `forge ingest --detect`. Sorted by file_count desc.

    Excludes `MEMORY.md`. Skips slugs with zero non-excluded files.
    """
    base = _claude_projects_root()
    if not base.exists():
        return []
    out: list[tuple[str, int, int]] = []
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        files = [
            f for f in memory_dir.glob("*.md")
            if f.is_file() and f.name not in _EXCLUDED_NAMES
        ]
        if not files:
            continue
        try:
            total_bytes = sum(f.stat().st_size for f in files)
        except OSError:
            continue
        out.append((project_dir.name, len(files), total_bytes))
    out.sort(key=lambda t: -t[1])
    return out


def read_all_projects(project_filter: str | None) -> tuple[str, Path | None, int]:
    """Read all Claude Code auto-memory markdown files into one text blob.

    Returns (concatenated_text, representative_source_path, file_count).
    Each file is prefixed with a `--- from: <project>/<file> ---` header so
    a downstream classifier knows provenance.

    `MEMORY.md` (index file) is excluded. `project_filter` restricts to one
    slug; None reads all projects.
    """
    base = _claude_projects_root()
    if not base.exists():
        return "", None, 0
    parts: list[str] = []
    count = 0
    repr_path: Path | None = None
    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_filter and project_dir.name != project_filter:
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        for f in sorted(memory_dir.glob("*.md")):
            if f.name in _EXCLUDED_NAMES:
                continue
            try:
                content = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if not content.strip():
                continue
            parts.append(f"--- from: {project_dir.name}/{f.name} ---\n{content}\n")
            count += 1
            if repr_path is None:
                repr_path = f
    return "\n".join(parts), repr_path, count


def count_transcripts() -> int:
    """Count Claude Code transcripts (jsonl). Used by `forge ingest --detect`
    to surface the "v0.4 transcript-distill not done yet" hint.
    """
    base = _claude_projects_root()
    if not base.exists():
        return 0
    return sum(1 for _ in base.glob("*/*.jsonl"))
