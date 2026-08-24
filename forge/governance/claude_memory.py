"""Agent memory/history as first-class governed sources.

Claude Code writes auto-memory markdown files under
`~/.claude/projects/<slug>/memory/*.md`. These files persist across sessions
and are injected into every new Claude session's context — they directly
shape future agent behavior. Per forge's review-gated thesis, any source
that becomes long-term agent context must go through the same
capture → inbox → PR → review pipeline as workspace-project drift, web
clippings, and internal content changes.

Codex writes its durable memory and history under `~/.codex/`, including
`memories/`, rollout summaries, `history.jsonl`, `session_index.jsonl`, and
archived-session jsonl files. Those are also agent-authored long-term
behavior/history surfaces and therefore belong in the same governed monitor.

This module wires that path. Pattern mirrors `web_clipping.py` and
`workspace_project.py`:

  - discover memory/history files for a workspace's matched Claude project
    and global Codex installation
  - hash-diff against a sidecar state file at `.forge/agent_memory_state.json`
  - report new / modified files via `format_monitor_lines(workspace)`
  - first activation establishes a baseline (no inbox flood — the user has
    been operating without monitor coverage; existing memory is taken as the
    starting state, going forward only deltas surface)
  - baseline is not treated as reviewed import: if a provider has no matching
    capture/import evidence yet, monitor keeps an explicit import-pending
    action so historical corpus can still be distilled through review.

State file vs in-source frontmatter (deviation from web_clipping /
workspace_project): Claude rewrites memory files autonomously, so any
state we wrote into a memory file's frontmatter would be overwritten on
the next agent edit. We keep the state in `.forge/agent_memory_state.json`
(workspace-local, gitignored, alongside `manifest.json`).

Scope:
  - Claude Code: the Claude project slug matching the personalOS workspace path
    (slug = absolute path with `/` → `-`, e.g. `/Users/<user>/personalOS`
    becomes `-Users-<user>-personalOS`). Other Claude project slugs are not
    watched by default.
  - Codex: global durable Codex memory/history under `~/.codex/`.

Forge runtime outputs (`~/.claude/CLAUDE.md`, `~/.codex/AGENTS.md`) and Codex
generated state databases are NOT watched — they're forge-authored or runtime
state, and watching them would create self-loops / constant churn.

Convention: `MEMORY.md` (the index file written by Claude's auto-memory
system) is silently excluded — it's an index, not feedback content, and
fluctuates whenever any feedback file is added or removed.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


# Memory files that are indexes, not content. Excluded from monitor reports
# and from baseline tracking.
_EXCLUDED_NAMES = frozenset({"MEMORY.md"})


def _claude_projects_root() -> Path:
    """Where Claude Code stores per-project memory + transcripts."""
    return Path.home() / ".claude" / "projects"


def _codex_root() -> Path:
    """Where Codex stores durable memory and local history."""
    return Path.home() / ".codex"


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
    """A single agent-authored memory/history artifact."""

    path: Path                 # absolute path
    slug: str                  # source scope (e.g. -Users... or codex/memories)
    name: str                  # filename (basename)
    size: int                  # bytes
    sha256: str                # content hash
    modified_at: float = 0.0   # source mtime; used to separate new vs historical

    @property
    def display(self) -> str:
        """Concise label for monitor output (`<slug>/<name>`)."""
        return f"{self.slug}/{self.name}"


@dataclass(frozen=True)
class MemoryReviewUnit:
    """One bounded semantic unit that can receive an independent disposition."""

    id: str
    title: str
    kind: str
    source_path: Path
    start_line: int
    end_line: int
    size: int
    sha256: str
    content: str = ""
    legacy_parent_id: str = ""
    legacy_parent_sha256: str = ""

    @property
    def display(self) -> str:
        if self.start_line == self.end_line:
            location = f"L{self.start_line}"
        else:
            location = f"L{self.start_line}-L{self.end_line}"
        return f"{self.title} · {self.source_path}#{location}"

    def to_batch_item(self, category: str) -> dict[str, object]:
        item: dict[str, object] = {
            "unit_id": self.id,
            "title": self.title,
            "unit_kind": self.kind,
            "path": str(self.source_path),
            "start_line": self.start_line,
            "end_line": self.end_line,
            "display": self.display,
            "digest": self.sha256,
            "category": category,
            "size": self.size,
        }
        if self.content:
            item["content"] = self.content
        if self.legacy_parent_id:
            item["legacy_parent_id"] = self.legacy_parent_id
        return item


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
            stat = p.stat()
            size = stat.st_size
        except OSError:
            continue
        h = _hash_file(p)
        if not h:
            continue
        out.append(
            MemoryFile(
                path=p, slug=slug, name=p.name, size=size, sha256=h,
                modified_at=stat.st_mtime,
            )
        )
    return out


def discover_codex_files() -> list[MemoryFile]:
    """List Codex-authored memory/history artifacts.

    We intentionally keep this to textual durable artifacts:
      - `~/.codex/memories/**/*.md` (including registry/summary files and
        rollout summaries), excluding `.git/`
      - `~/.codex/history.jsonl`, `session_index.jsonl`
      - `~/.codex/archived_sessions/*.jsonl`

    Excludes forge-authored runtime output (`AGENTS.md`) and sqlite/log/cache
    files that churn without being reviewable memory/history content. Also
    excludes live `~/.codex/sessions/**/*.jsonl`: those mutate during the
    current conversation and are too noisy for review-gated monitor. Codex
    rollout summaries under `memories/rollout_summaries/` are the stable
    distilled history surface.
    """
    root = _codex_root()
    if not root.exists():
        return []

    candidates: list[tuple[Path, str]] = []
    memories = root / "memories"
    if memories.is_dir():
        for p in memories.rglob("*.md"):
            if not p.is_file():
                continue
            if ".git" in p.relative_to(memories).parts:
                continue
            candidates.append((p, "codex/memories"))

    for rel in ("history.jsonl", "session_index.jsonl"):
        p = root / rel
        if p.is_file():
            candidates.append((p, "codex/history"))

    archived = root / "archived_sessions"
    if archived.is_dir():
        for p in archived.rglob("*.jsonl"):
            if p.is_file():
                candidates.append((p, "codex/archived_sessions"))

    out: list[MemoryFile] = []
    for p, slug in sorted(candidates, key=lambda item: str(item[0])):
        try:
            stat = p.stat()
            size = stat.st_size
        except OSError:
            continue
        h = _hash_file(p)
        if not h:
            continue
        try:
            name = str(p.relative_to(root))
        except ValueError:
            name = p.name
        out.append(
            MemoryFile(
                path=p, slug=slug, name=name, size=size, sha256=h,
                modified_at=stat.st_mtime,
            )
        )
    return out


_TASK_GROUP_RE = re.compile(r"^# Task Group:\s*(.+?)\s*$", re.MULTILINE)
_TASK_RE = re.compile(r"^## Task\s+(\d+)\s*:\s*(.+?)\s*$", re.MULTILINE)
_LEVEL_TWO_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_CODEX_AGGREGATE_NAMES = frozenset(
    {"memory_summary.md", "raw_memories.md"}
)


def _codex_task_units(
    group_text: str,
    *,
    title: str,
    group_identity: str,
    legacy_parent_id: str,
    source_path: Path,
    group_start_offset: int,
    line_number,
) -> list[MemoryReviewUnit]:
    """Split one curated Task Group into Tasks plus any unassigned summary."""
    headings = list(_LEVEL_TWO_RE.finditer(group_text))
    tasks = [heading for heading in headings if _TASK_RE.fullmatch(heading.group(0))]
    if not tasks:
        return []
    first_task = tasks[0]
    prefix = group_text[:first_task.start()].rstrip()
    group_sections: list[tuple[str, str]] = []
    for index, heading in enumerate(headings):
        if _TASK_RE.fullmatch(heading.group(0)):
            continue
        section_end = headings[index + 1].start() if index + 1 < len(headings) else len(group_text)
        group_sections.append((heading.group(0).strip(), group_text[heading.end():section_end]))

    task_numbers = {
        parsed.group(1)
        for heading in tasks
        if (parsed := _TASK_RE.fullmatch(heading.group(0))) is not None
    }
    units: list[MemoryReviewUnit] = []
    for task in tasks:
        parsed = _TASK_RE.fullmatch(task.group(0))
        assert parsed is not None
        task_number, task_title = parsed.group(1), parsed.group(2).strip()
        heading_index = headings.index(task)
        task_end = (
            headings[heading_index + 1].start()
            if heading_index + 1 < len(headings)
            else len(group_text)
        )
        task_body = group_text[task.start():task_end].rstrip()
        tagged_sections: list[str] = []
        tag = re.compile(rf"\[Task\s+{re.escape(task_number)}\]")
        for section_heading, section_body in group_sections:
            blocks = _markdown_bullet_blocks(section_body)
            selected = [block for block in blocks if tag.search(block)]
            if selected:
                tagged_sections.append(
                    section_heading + "\n\n" + "\n".join(selected).strip()
                )
        assembled_parts = [prefix, task_body, *tagged_sections]
        assembled = "\n\n".join(part for part in assembled_parts if part).rstrip() + "\n"
        identity = hashlib.sha1(
            f"{group_identity}\0task:{task_number}".encode("utf-8")
        ).hexdigest()[:16]
        absolute_start = group_start_offset + task.start()
        absolute_end = group_start_offset + max(task.start(), task_end - 1)
        units.append(
            MemoryReviewUnit(
                id=f"codex-task:{identity}",
                title=f"{title} · Task {task_number}: {task_title}",
                kind="codex-task",
                source_path=source_path,
                start_line=line_number(absolute_start),
                end_line=line_number(absolute_end),
                size=len(assembled.encode("utf-8")),
                sha256=hashlib.sha256(assembled.encode("utf-8")).hexdigest(),
                content=assembled,
                legacy_parent_id=legacy_parent_id,
                legacy_parent_sha256=hashlib.sha256(group_text.encode("utf-8")).hexdigest(),
            )
        )
    unassigned_sections: list[str] = []
    for section_heading, section_body in group_sections:
        preamble, blocks = _markdown_section_parts(section_body)
        unassigned_blocks = [
            block
            for block in blocks
            if not any(
                re.search(rf"\[Task\s+{re.escape(number)}\]", block)
                for number in task_numbers
            )
        ]
        unassigned_body = "\n\n".join(
            part for part in (preamble, *unassigned_blocks) if part
        ).strip()
        if unassigned_body:
            unassigned_sections.append(
                section_heading + "\n\n" + unassigned_body
            )
    if unassigned_sections:
        assembled = "\n\n".join((prefix, *unassigned_sections)).rstrip() + "\n"
        identity = hashlib.sha1(
            f"{group_identity}\0summary".encode("utf-8")
        ).hexdigest()[:16]
        units.append(
            MemoryReviewUnit(
                id=f"codex-task-group-summary:{identity}",
                title=f"{title} · Group summary",
                kind="codex-task-group-summary",
                source_path=source_path,
                start_line=line_number(group_start_offset),
                end_line=line_number(
                    group_start_offset + max(0, len(group_text) - 1)
                ),
                size=len(assembled.encode("utf-8")),
                sha256=hashlib.sha256(assembled.encode("utf-8")).hexdigest(),
                content=assembled,
                legacy_parent_id=legacy_parent_id,
                legacy_parent_sha256=hashlib.sha256(
                    group_text.encode("utf-8")
                ).hexdigest(),
            )
        )
    return units


def _markdown_section_parts(text: str) -> tuple[str, list[str]]:
    preamble: list[str] = []
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
        else:
            preamble.append(line)
    if current:
        blocks.append(current)
    return (
        "\n".join(preamble).strip(),
        ["\n".join(block).rstrip() for block in blocks],
    )


def _markdown_bullet_blocks(text: str) -> list[str]:
    return _markdown_section_parts(text)[1]


def discover_codex_review_units(
) -> tuple[list[MemoryReviewUnit], dict[str, int]]:
    """Return bounded Codex selection units and explicit non-unit diagnostics.

    When the curated registry exists, one Task Group is the semantic boundary;
    rollout summaries and raw sessions remain evidence pointers.  A provider
    without a registry falls back to individual stable summary markdown files.
    """
    root = _codex_root()
    memories = root / "memories"
    registry = memories / "MEMORY.md"
    units: list[MemoryReviewUnit] = []
    excluded: dict[str, int] = {}

    if registry.is_file():
        try:
            text = registry.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""
        matches = list(_TASK_GROUP_RE.finditer(text))
        line_offsets = [0]
        for match in re.finditer(r"\n", text):
            line_offsets.append(match.end())

        def line_number(offset: int) -> int:
            import bisect

            return bisect.bisect_right(line_offsets, offset)

        title_occurrences: dict[str, int] = {}
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            body = text[match.start():end].rstrip() + "\n"
            title = match.group(1).strip()
            title_occurrences[title] = title_occurrences.get(title, 0) + 1
            occurrence = title_occurrences[title]
            identity = hashlib.sha1(
                f"{title}\0{occurrence}".encode("utf-8")
            ).hexdigest()[:16]
            legacy_parent_id = f"codex-task-group:{identity}"
            task_units = _codex_task_units(
                body,
                title=title,
                group_identity=identity,
                legacy_parent_id=legacy_parent_id,
                source_path=registry.resolve(),
                group_start_offset=match.start(),
                line_number=line_number,
            )
            if task_units:
                units.extend(task_units)
            else:
                units.append(
                    MemoryReviewUnit(
                        id=legacy_parent_id,
                        title=title,
                        kind="codex-task-group",
                        source_path=registry.resolve(),
                        start_line=line_number(match.start()),
                        end_line=line_number(max(match.start(), end - 1)),
                        size=len(body.encode("utf-8")),
                        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
                        content=body,
                    )
                )
        referenced = 0
        for directory in (
            memories / "rollout_summaries",
            memories / "extensions",
        ):
            if directory.is_dir():
                referenced += sum(
                    1 for path in directory.rglob("*.md")
                    if path.is_file() and ".git" not in path.parts
                )
        if referenced:
            excluded["referenced-evidence-files"] = referenced
    elif memories.is_dir():
        fallback_paths = list((memories / "rollout_summaries").rglob("*.md")) \
            if (memories / "rollout_summaries").is_dir() else []
        extensions = memories / "extensions"
        if extensions.is_dir():
            fallback_paths.extend(extensions.rglob("*.md"))
        for path in sorted({p.resolve() for p in fallback_paths if p.is_file()}):
            try:
                data = path.read_bytes()
                stat = path.stat()
            except OSError:
                continue
            digest = hashlib.sha256(data).hexdigest()
            identity = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
            units.append(
                MemoryReviewUnit(
                    id=f"codex-summary:{identity}",
                    title=path.stem,
                    kind="codex-summary-file",
                    source_path=path,
                    start_line=1,
                    end_line=max(1, data.count(b"\n") + 1),
                    size=stat.st_size,
                    sha256=digest,
                    content=data.decode("utf-8"),
                )
            )

    aggregate_count = sum(
        1 for name in _CODEX_AGGREGATE_NAMES if (memories / name).is_file()
    )
    if aggregate_count:
        excluded["aggregate-memory-files"] = aggregate_count
    history_count = sum(
        1 for name in ("history.jsonl", "session_index.jsonl")
        if (root / name).is_file()
    )
    if history_count:
        excluded["history-indexes"] = history_count
    archived = root / "archived_sessions"
    archived_count = (
        sum(1 for path in archived.rglob("*.jsonl") if path.is_file())
        if archived.is_dir() else 0
    )
    if archived_count:
        excluded["archived-sessions"] = archived_count
    return units, excluded


def discover_review_units(
    workspace: Path,
) -> tuple[list[MemoryReviewUnit], dict[str, int]]:
    """Discover every eligible semantic unit for the workspace's providers."""
    units: list[MemoryReviewUnit] = []
    slug = workspace_to_slug(workspace)
    for memory_file in discover_memory_files(slug):
        identity = hashlib.sha1(str(memory_file.path).encode("utf-8")).hexdigest()[:16]
        units.append(
            MemoryReviewUnit(
                id=f"claude-memory:{identity}",
                title=memory_file.name,
                kind="claude-memory-file",
                source_path=memory_file.path.resolve(),
                start_line=1,
                end_line=max(1, memory_file.path.read_bytes().count(b"\n") + 1),
                size=memory_file.size,
                sha256=memory_file.sha256,
                content=memory_file.path.read_text(encoding="utf-8"),
            )
        )
    codex_units, excluded = discover_codex_review_units()
    units.extend(codex_units)
    return units, excluded


# ---------- state file (.forge/agent_memory_state.json) ----------


_STATE_REL_PATH = (".forge", "agent_memory_state.json")
_STATE_SCHEMA_VERSION = 2
RUN_BATCH_LIMIT = 10
RUN_BATCH_BYTE_LIMIT = 128 * 1024


def state_path(workspace: Path) -> Path:
    return workspace.joinpath(*_STATE_REL_PATH)


@dataclass
class MemoryState:
    """Persisted view of which memory files we've already snapshotted."""

    schema_version: int = _STATE_SCHEMA_VERSION
    # Keyed by absolute path string. Value: {"hash": ..., "size": ..., "seen_at": ...}
    last_seen: dict[str, dict] = field(default_factory=dict)
    # Source scopes already baseline-initialized. Lets new providers be added
    # without flooding old workspaces with every historical file.
    baselined_sources: list[str] = field(default_factory=list)
    # Review Unit checkpoint. File-level last_seen is monitor compatibility,
    # not proof that semantic candidate selection was completed.
    settled_units: dict[str, dict] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": self.schema_version,
                "last_seen": self.last_seen,
                "baselined_sources": sorted(set(self.baselined_sources)),
                "settled_units": self.settled_units,
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
        baselined_sources_raw = data.get("baselined_sources") or []
        if not isinstance(baselined_sources_raw, list):
            baselined_sources_raw = []
        settled_units_raw = data.get("settled_units") or {}
        if not isinstance(settled_units_raw, dict):
            settled_units_raw = {}
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
            schema_version=_STATE_SCHEMA_VERSION,
            last_seen=last_seen,
            baselined_sources=[
                str(s) for s in baselined_sources_raw if isinstance(s, str)
            ],
            settled_units={
                str(k): {
                    "hash": str(v.get("hash") or ""),
                    "size": int(v.get("size") or 0),
                    "seen_at": str(v.get("seen_at") or ""),
                    "source_path": str(v.get("source_path") or ""),
                }
                for k, v in settled_units_raw.items()
                if isinstance(k, str) and isinstance(v, dict)
            },
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
    _mark_seen_in_state(state, files)
    for source_id in _source_ids_for_files(files):
        if source_id not in state.baselined_sources:
            state.baselined_sources.append(source_id)
    save_state(workspace, state)


def _mark_seen_in_state(state: MemoryState, files: list[MemoryFile]) -> None:
    now = _now_iso()
    for f in files:
        state.last_seen[str(f.path)] = {
            "hash": f.sha256,
            "size": f.size,
            "seen_at": now,
        }


def _source_ids_for_files(files: list[MemoryFile]) -> list[str]:
    out: list[str] = []
    for f in files:
        source_id = "codex" if f.slug.startswith("codex/") else f"claude:{f.slug}"
        if source_id not in out:
            out.append(source_id)
    return out


def _captured_agent_sources(workspace: Path) -> set[str]:
    """Return provider ids whose historical corpus has raw capture evidence.

    Baseline state is only a noise-control mechanism. A source counts as
    imported only after raw evidence exists under capture/import/.
    """
    capture_root = workspace / "capture" / "import"
    if not capture_root.is_dir():
        return set()

    captured: set[str] = set()
    for p in capture_root.glob("*/*.md"):
        try:
            head = p.read_text(encoding="utf-8", errors="ignore")[:2048]
        except OSError:
            continue
        if (
            "source: \"codex-memory-history:all\"" in head
            or "source: codex-memory-history:all" in head
        ):
            captured.add("codex")
        if "source: \"claude-code-memory:" in head or "source: claude-code-memory:" in head:
            captured.add("claude")
    return captured


def is_memory_file(path: Path) -> bool:
    """True if `path` is a governed agent memory/history artifact.

    Recognizes Claude Code auto-memory and Codex durable memory/history files.
    Used by capture to decide whether to mark-seen.

    Tolerates both absolute and resolved paths; uses parent chain.
    """
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if _is_claude_memory_file(resolved):
        return True
    return _is_codex_file(resolved)


def _is_claude_memory_file(path: Path) -> bool:
    if path.name in _EXCLUDED_NAMES:
        return False
    if path.suffix != ".md":
        return False
    parent = path.parent
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


def _is_codex_file(path: Path) -> bool:
    root = _codex_root()
    try:
        rel = path.relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    parts = rel.parts
    if not parts:
        return False
    if parts[0] == "memories":
        return path.suffix == ".md" and ".git" not in parts
    if rel.as_posix() in {"history.jsonl", "session_index.jsonl"}:
        return True
    if parts[0] == "archived_sessions":
        return path.suffix == ".jsonl"
    return False


def slug_for_memory_path(path: Path) -> str:
    """Extract the project slug from a memory file path.
    `<...>/.claude/projects/<slug>/memory/foo.md` → "<slug>".
    Empty string if the path doesn't fit the layout.
    """
    if not is_memory_file(path):
        return ""
    resolved = path.resolve()
    if _is_claude_memory_file(resolved):
        return resolved.parent.parent.name
    if _is_codex_file(resolved):
        try:
            rel = resolved.relative_to(_codex_root().resolve())
        except ValueError:
            return "codex"
        if rel.parts and rel.parts[0] == "memories":
            return "codex/memories"
        if rel.parts and rel.parts[0] == "archived_sessions":
            return f"codex/{rel.parts[0]}"
        return "codex/history"
    return ""


def mark_path_seen(workspace: Path, memory_path: Path) -> bool:
    """Convenience wrapper for capture-time mark-seen. Hashes the file at
    `memory_path` and records it in state.

    Returns True on success, False if the path isn't a memory file or is
    unreadable. Does NOT raise — capture should proceed even on failure.
    """
    if not is_memory_file(memory_path):
        return False
    try:
        stat = memory_path.stat()
        size = stat.st_size
    except OSError:
        return False
    h = _hash_file(memory_path)
    if not h:
        return False
    slug = slug_for_memory_path(memory_path)
    f = MemoryFile(
        path=memory_path.resolve(),
        slug=slug,
        name=(
            str(memory_path.resolve().relative_to(_codex_root().resolve()))
            if slug.startswith("codex/")
            else memory_path.name
        ),
        size=size,
        sha256=h,
        modified_at=stat.st_mtime,
    )
    mark_seen(workspace, [f])
    return True


# ---------- diff: report new / modified files ----------


@dataclass
class MemoryDiff:
    """Result of comparing current files to state baseline."""

    new: list[MemoryFile] = field(default_factory=list)
    modified: list[MemoryFile] = field(default_factory=list)
    historical: list[MemoryFile] = field(default_factory=list)
    # Note: deleted files are silent — we don't surface them in monitor
    # (they're not actionable; the agent removed them, that's a normal
    # workflow event). They DO get cleaned out of state on the next sync
    # via `prune_state_for_slug`.


def compute_diff(workspace: Path, slug: str, state: MemoryState) -> MemoryDiff:
    """Diff current memory files for `slug` against `state.last_seen`."""
    diff = MemoryDiff()
    baseline_at = _source_baseline_epoch(state, f"claude:{slug}")
    for f in discover_memory_files(slug):
        key = str(f.path)
        prev = state.last_seen.get(key)
        if prev is None:
            (diff.historical if _predates_baseline(f, baseline_at) else diff.new).append(f)
        elif prev.get("hash") != f.sha256:
            diff.modified.append(f)
    return diff


def compute_codex_diff(state: MemoryState) -> MemoryDiff:
    """Diff global Codex memory/history files against `state.last_seen`."""
    diff = MemoryDiff()
    baseline_at = _source_baseline_epoch(state, "codex")
    for f in discover_codex_files():
        key = str(f.path)
        prev = state.last_seen.get(key)
        if prev is None:
            (diff.historical if _predates_baseline(f, baseline_at) else diff.new).append(f)
        elif prev.get("hash") != f.sha256:
            diff.modified.append(f)
    return diff


def _source_baseline_epoch(state: MemoryState, source_id: str) -> float:
    """Best available activation time for a provider, including v1 state migration."""
    timestamps: list[float] = []
    for path, entry in state.last_seen.items():
        if source_id == "codex":
            if "/.codex/" not in path:
                continue
        else:
            slug = source_id.removeprefix("claude:")
            try:
                Path(path).relative_to(memory_dir_for_slug(slug))
            except ValueError:
                continue
        try:
            timestamps.append(datetime.fromisoformat(entry.get("seen_at", "")).timestamp())
        except (TypeError, ValueError):
            continue
    return max(timestamps, default=0.0)


def _predates_baseline(memory_file: MemoryFile, baseline_at: float) -> bool:
    # One-second tolerance avoids misclassifying a file created in the same
    # coarse filesystem clock tick immediately after baseline activation.
    return bool(baseline_at and memory_file.modified_at < baseline_at - 1.0)


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


def prune_state_for_codex(state: MemoryState) -> int:
    """Drop missing Codex entries from state. Mutates `state` in place."""
    root = _codex_root()
    drop: list[str] = []
    for key in list(state.last_seen.keys()):
        try:
            kp = Path(key)
            kp.relative_to(root.resolve())
        except (OSError, ValueError):
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

      1. Resolve watched sources: Claude project slug from `workspace` path
         and global Codex memory/history.
      2. If state file does NOT exist (first activation): snapshot all
         current memory files into state and return a one-line info issue
         (`agent-memory: initialized baseline (N files tracked)`). No
         per-file actions — the user has been operating without monitor
         coverage; existing files are NOT retroactively pushed through PR.
      3. Otherwise, diff current files against state. Surface unseen and
         modified files as inbox-worthy actions. "Unseen" deliberately does
         not claim the file was recently created.
      4. If neither Claude nor Codex watched sources exist, return empty.
      5. State pruning (deleted files) happens silently as a side-effect of
         the diff/save cycle — no monitor noise.

    Returns ([], []) when:
      - the workspace has no matching Claude project, OR
      - the state file exists and there's no drift since last seen.
    """
    slug = workspace_to_slug(workspace)
    mem_dir = memory_dir_for_slug(slug)
    has_claude = mem_dir.is_dir()
    codex_files = discover_codex_files()
    has_codex = bool(codex_files)
    if not has_claude and not has_codex:
        return [], []

    state = load_state(workspace)
    watched_sources: list[tuple[str, list[MemoryFile]]] = []
    if has_claude:
        watched_sources.append((f"claude:{slug}", discover_memory_files(slug)))
    if has_codex:
        watched_sources.append(("codex", codex_files))

    if state is None:
        # First activation: baseline current files, do not flood inbox.
        current: list[MemoryFile] = []
        source_ids: list[str] = []
        for source_id, files in watched_sources:
            current.extend(files)
            source_ids.append(source_id)
        if not current:
            # Empty watched dirs; still write an empty state so subsequent
            # additions are detected as new (not as another baseline).
            save_state(workspace, MemoryState(baselined_sources=source_ids))
            return [], []
        state = MemoryState(baselined_sources=source_ids)
        _mark_seen_in_state(state, current)
        save_state(workspace, state)
        n = len(current)
        files_label = "file" if n == 1 else "files"
        return (
            [f"agent-memory: initialized baseline ({n} {files_label} tracked)"],
            [],
        )

    new_provider_files: list[MemoryFile] = []
    initialized_sources: list[str] = []
    known_sources = set(state.baselined_sources)
    # Old v0.9 state files did not carry provider markers. If they already
    # contain Claude paths, treat the current Claude source as initialized.
    if not known_sources and any("/.claude/projects/" in k for k in state.last_seen):
        known_sources.add(f"claude:{slug}")
        state.baselined_sources.append(f"claude:{slug}")

    for source_id, files in watched_sources:
        if source_id not in known_sources:
            new_provider_files.extend(files)
            initialized_sources.append(source_id)
            state.baselined_sources.append(source_id)
    if initialized_sources:
        _mark_seen_in_state(state, new_provider_files)
        save_state(workspace, state)
        n = len(new_provider_files)
        files_label = "file" if n == 1 else "files"
        sources = ", ".join(initialized_sources)
        return (
            [f"agent-memory: initialized baseline ({sources}; {n} {files_label} tracked)"],
            [],
        )

    diff = MemoryDiff()
    if has_claude:
        claude_diff = compute_diff(workspace, slug, state)
        diff.new.extend(claude_diff.new)
        diff.modified.extend(claude_diff.modified)
        diff.historical.extend(claude_diff.historical)
    if has_codex:
        codex_diff = compute_codex_diff(state)
        diff.new.extend(codex_diff.new)
        diff.modified.extend(codex_diff.modified)
        diff.historical.extend(codex_diff.historical)

    if not diff.new and not diff.modified and not diff.historical:
        # Opportunistic pruning: drop state entries for deleted files.
        pruned = 0
        if has_claude:
            pruned += prune_state_for_slug(state, slug)
        if has_codex:
            pruned += prune_state_for_codex(state)
        if pruned > 0:
            save_state(workspace, state)
        return _historical_import_pending_lines(workspace, state)

    issues: list[str] = []
    actions: list[str] = []
    total = len(diff.new) + len(diff.modified)
    parts: list[str] = []
    if diff.new:
        parts.append(f"unseen {len(diff.new)}")
    if diff.modified:
        parts.append(f"modified {len(diff.modified)}")
    if total:
        issues.append(f"agent-memory updates: {total} ({', '.join(parts)})")
    if diff.historical:
        issues.append(f"agent-memory historical backlog: {len(diff.historical)}")

    # Cap at 5 per category to keep monitor surface readable
    for f in diff.new[:5]:
        actions.append(
            f'agent-memory UNSEEN: {f.display} · forge capture --from "{f.path}"'
        )
    if len(diff.new) > 5:
        actions.append(f"  ... and {len(diff.new) - 5} more unseen agent-memory files")
    for f in diff.modified[:5]:
        actions.append(f'agent-memory MODIFIED: {f.display} · forge capture --from "{f.path}"')
    if len(diff.modified) > 5:
        actions.append(f"  ... and {len(diff.modified) - 5} more modified agent-memory files")
    for f in diff.historical[:5]:
        actions.append(
            f'agent-memory HISTORICAL: {f.display} · forge capture --from "{f.path}"'
        )
    if len(diff.historical) > 5:
        actions.append(
            f"  ... and {len(diff.historical) - 5} more historical agent-memory files"
        )

    return issues, actions


def build_run_source_signal(
    workspace: Path,
    *,
    limit: int = RUN_BATCH_LIMIT,
    byte_limit: int = RUN_BATCH_BYTE_LIMIT,
) -> dict[str, object] | None:
    """Build the stable, bounded Source Batch used by ``forge run``.

    Review Units, not provider files, are the classification boundary. Codex
    uses curated Task Groups; Claude uses individual non-index memory files.
    The signal digest deliberately excludes the changing total count so later
    arrivals cannot invalidate an open batch.
    """
    units, excluded = discover_review_units(workspace)
    if not units:
        return None
    state = load_state(workspace)
    if state is None:
        state = MemoryState()
        save_state(workspace, state)
    modified: list[MemoryReviewUnit] = []
    unseen: list[MemoryReviewUnit] = []
    parent_counts: dict[str, int] = {}
    for unit in units:
        if unit.legacy_parent_id:
            parent_counts[unit.legacy_parent_id] = (
                parent_counts.get(unit.legacy_parent_id, 0) + 1
            )
    checkpoint_migrated = False
    for unit in units:
        previous = state.settled_units.get(unit.id)
        if (
            previous is None
            and unit.legacy_parent_id
            and parent_counts.get(unit.legacy_parent_id) == 1
        ):
            legacy = state.settled_units.get(unit.legacy_parent_id)
            if legacy and legacy.get("hash") == unit.legacy_parent_sha256:
                state.settled_units[unit.id] = {
                    "hash": unit.sha256,
                    "size": unit.size,
                    "seen_at": legacy.get("seen_at") or _now_iso(),
                    "source_path": str(unit.source_path),
                    "migrated_from": unit.legacy_parent_id,
                }
                previous = state.settled_units[unit.id]
                checkpoint_migrated = True
        if previous is None:
            unseen.append(unit)
        elif previous.get("hash") != unit.sha256:
            modified.append(unit)
    if checkpoint_migrated:
        save_state(workspace, state)
    categorized = (
        [("modified", item) for item in modified]
        + [("unseen", item) for item in unseen]
    )
    if not categorized:
        return None

    effective_limit = max(1, limit)
    effective_byte_limit = max(1, byte_limit)
    selected: list[tuple[str, MemoryReviewUnit]] = []
    selected_bytes = 0
    for category, unit in categorized:
        if len(selected) >= effective_limit:
            break
        if unit.size > effective_byte_limit:
            raise ValueError(
                f"agent-memory Review Unit exceeds {effective_byte_limit} bytes: "
                f"{unit.display}"
            )
        if selected and selected_bytes + unit.size > effective_byte_limit:
            break
        selected.append((category, unit))
        selected_bytes += unit.size
    batch_items = [item.to_batch_item(category) for category, item in selected]
    digest_material = "\n".join(
        f"{item['category']}\t{item.get('unit_id', item['path'])}\t{item['digest']}"
        for item in batch_items
    )
    digest = hashlib.sha1(
        f"agent-memory\n{digest_material}".encode("utf-8")
    ).hexdigest()[:16]
    total_count = len(categorized)
    selected_count = len(batch_items)
    remaining_count = total_count - selected_count
    summary = (
        f"agent-memory batch: {selected_count} of {total_count}; "
        f"remaining after batch: {remaining_count}"
    )
    detail = "\n".join(
        f"{item['category'].upper()}: {item['display']} · {item['path']}"
        for item in batch_items
    )
    return {
        "path": "source://agent-memory",
        "digest": digest,
        "type": "source-signal",
        "source_kind": "agent-memory",
        "handler": "bounded-memory-review",
        "summary": summary,
        "detail": detail,
        "batch_items": batch_items,
        "batch_size": selected_count,
        "total_count": total_count,
        "remaining_count": remaining_count,
        "batch_bytes": selected_bytes,
        "byte_limit": effective_byte_limit,
        "excluded_source_counts": excluded,
    }


def settle_run_source_batch(
    workspace: Path,
    batch_items: list[dict[str, object]],
) -> list[str]:
    """Advance the semantic checkpoint for exact Memory Review Units.

    Every item is stale-checked before any state is written.  The checkpoint
    means the item received a disposition; it does not claim that it became a
    promoted asset.
    """
    if batch_items and all(item.get("unit_id") for item in batch_items):
        current_units, _ = discover_review_units(workspace)
        current_by_id = {unit.id: unit for unit in current_units}
        state = load_state(workspace) or MemoryState()
        now = _now_iso()
        settled: list[str] = []
        for item in batch_items:
            unit_id = str(item.get("unit_id") or "")
            expected = str(item.get("digest") or "")
            current = current_by_id.get(unit_id)
            if current is None:
                raise ValueError(f"agent-memory Review Unit is missing: {unit_id}")
            if current.sha256 != expected:
                raise ValueError(f"agent-memory Review Unit drifted: {unit_id}")
            state.settled_units[unit_id] = {
                "hash": current.sha256,
                "size": current.size,
                "seen_at": now,
                "source_path": str(current.source_path),
            }
            settled.append(unit_id)
        save_state(workspace, state)
        return settled

    # Compatibility for an already-open v0.12 file-level batch.
    files: list[MemoryFile] = []
    for item in batch_items:
        path = Path(str(item.get("path") or ""))
        expected = str(item.get("digest") or "")
        if not is_memory_file(path):
            raise ValueError(f"memory batch item is outside governed sources: {path}")
        try:
            stat = path.stat()
        except OSError as exc:
            raise ValueError(f"memory batch item is missing: {path}") from exc
        current = _hash_file(path)
        if not current or current != expected:
            raise ValueError(f"memory batch item drifted: {path}")
        files.append(
            MemoryFile(
                path=path.resolve(),
                slug=slug_for_memory_path(path),
                name=path.name,
                size=stat.st_size,
                sha256=current,
                modified_at=stat.st_mtime,
            )
        )
    if not files:
        raise ValueError("agent-memory Source Signal has no settleable batch items")
    mark_seen(workspace, files)
    return [str(item.path) for item in files]


def _historical_import_pending_lines(
    workspace: Path,
    state: MemoryState,
) -> tuple[list[str], list[str]]:
    captured = _captured_agent_sources(workspace)
    baselined = set(state.baselined_sources)
    issues: list[str] = []
    actions: list[str] = []

    if "codex" in baselined and "codex" not in captured:
        issues.append("agent-memory import pending: codex baseline has not been captured")
        actions.append("agent-memory IMPORT: forge capture --from-codex-memory")

    claude_baselined = any(source.startswith("claude:") for source in baselined)
    if claude_baselined and "claude" not in captured:
        issues.append("agent-memory import pending: Claude baseline has not been captured")
        actions.append("agent-memory IMPORT: forge capture --from-claude-memory")

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


def scan_codex_sources() -> list[tuple[str, int, int]]:
    """Return grouped Codex source counts for detect/import UI."""
    groups: dict[str, tuple[int, int]] = {}
    for f in discover_codex_files():
        count, size = groups.get(f.slug, (0, 0))
        groups[f.slug] = (count + 1, size + f.size)
    out = [(slug, count, size) for slug, (count, size) in groups.items()]
    out.sort(key=lambda t: (-t[1], t[0]))
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


def read_codex_sources() -> tuple[str, Path | None, int]:
    """Read all Codex memory/history artifacts into one text blob."""
    root = _codex_root()
    parts: list[str] = []
    count = 0
    repr_path: Path | None = None
    for f in discover_codex_files():
        try:
            content = f.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not content.strip():
            continue
        try:
            rel = f.path.relative_to(root)
        except ValueError:
            rel = Path(f.path.name)
        parts.append(f"--- from: codex/{rel.as_posix()} ---\n{content}\n")
        count += 1
        if repr_path is None:
            repr_path = f.path
    return "\n".join(parts), repr_path, count


def count_transcripts() -> int:
    """Count Claude Code transcripts (jsonl). Used by `forge ingest --detect`
    to surface the "v0.4 transcript-distill not done yet" hint.
    """
    base = _claude_projects_root()
    if not base.exists():
        return 0
    return sum(1 for _ in base.glob("*/*.jsonl"))
