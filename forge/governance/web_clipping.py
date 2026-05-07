"""web-clipping synthesize: feed external evidence into KB topic pages.

Web clippings sit under `capture/web clipping/*.md`. They are external evidence:
agent may ingest them, but the user does not review the clipping itself — only
the resulting KB topic update. This module supports the v0.6 "synthesize-
clipping" loop:

    monitor → synthesize-clipping <file> → inbox(web-clipping-synthesize)
    → proposal new → fill schema → review → approve
        ↳ on approve: KB topic file is committed (the proposal touched it)
                     + clipping frontmatter gets `synthesized_at` + `synthesized_into`

Lifecycle states (lifted from §3.10 of the personalOS data placement note):

  captured → indexed → cited/synthesized → archived/expired

This module covers the captured → synthesized step only. Archive/expire is a
manual user concern; we never delete clipping files.

Design constraints:

  - No LLM API. The agent decides which KB topic a clipping belongs to while
    filling the proposal schema. forge only enumerates candidate topics and
    ferries the work item through the standard inbox/PR flow.
  - The synthesized marker lives on the clipping file itself (frontmatter
    `synthesized_at` / `synthesized_into`). One source of truth, follows the
    file if it moves, no parallel manifest to keep in sync.
  - Clippings without frontmatter are tolerated — we skip them silently from
    the "pending" report (we have no way to tell synth status without
    frontmatter, so they are out of scope until the user adds one).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml


# ---------- frontmatter helpers ----------


_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def split_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, rest). frontmatter_dict is None if absent or
    malformed. Mirrors the helper in workspace_project.py."""
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


# ---------- data ----------


@dataclass
class WebClipping:
    """A loaded web clipping under `capture/web clipping/`."""

    path: Path                          # absolute path to the .md file
    slug: str                           # filename stem (sans suffix)
    title: str = ""                     # frontmatter `title` if present
    source_url: str = ""                # frontmatter `source` if present
    captured_at: str = ""               # frontmatter `created` / `published`
    synthesized_at: str = ""            # frontmatter `synthesized_at` if set
    synthesized_into: list[str] = field(default_factory=list)
    frontmatter: dict = field(default_factory=dict)
    body: str = ""

    @property
    def is_synthesized(self) -> bool:
        return bool(self.synthesized_at)


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value).strip()


def load_clipping(path: Path) -> WebClipping | None:
    """Parse `path` as a web clipping. Returns None if the file is not
    readable or has no parseable frontmatter (we treat it as out of scope).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    fm, body = split_frontmatter(text)
    if fm is None:
        return None

    synthesized_into_raw = fm.get("synthesized_into") or []
    if isinstance(synthesized_into_raw, str):
        synthesized_into = [synthesized_into_raw]
    elif isinstance(synthesized_into_raw, list):
        synthesized_into = [str(s).strip() for s in synthesized_into_raw if str(s).strip()]
    else:
        synthesized_into = []

    captured_at = _stringify(fm.get("created") or fm.get("published") or "")

    return WebClipping(
        path=path,
        slug=path.stem,
        title=_stringify(fm.get("title") or ""),
        source_url=_stringify(fm.get("source") or ""),
        captured_at=captured_at,
        synthesized_at=_stringify(fm.get("synthesized_at") or ""),
        synthesized_into=synthesized_into,
        frontmatter=fm,
        body=body,
    )


def clippings_dir(workspace: Path) -> Path:
    return workspace / "capture" / "web clipping"


def discover_clippings(workspace: Path) -> list[WebClipping]:
    """Scan `capture/web clipping/*.md` and return loaded WebClipping objects.

    Files without parseable frontmatter are silently skipped (out of scope —
    user must add a frontmatter to opt in). Sorted by slug for deterministic
    output.
    """
    out: list[WebClipping] = []
    root = clippings_dir(workspace)
    if not root.is_dir():
        return out
    for p in sorted(root.glob("*.md")):
        if not p.is_file():
            continue
        loaded = load_clipping(p)
        if loaded is not None:
            out.append(loaded)
    return sorted(out, key=lambda c: c.slug)


def pending_clippings(workspace: Path) -> list[WebClipping]:
    """Clippings that have NOT been synthesized into any KB topic yet."""
    return [c for c in discover_clippings(workspace) if not c.is_synthesized]


# ---------- KB topic discovery ----------


# We treat `index.md` / `log.md` directly under `topic/` as meta files (KB
# index + changelog), not topic pages. Per-topic pages live one or more dirs
# down (e.g. `topic/tech/ai/claude-code.md`).
_KB_TOPIC_META = {"index.md", "log.md"}


def kb_topic_root(workspace: Path) -> Path:
    return workspace / "public knowledge base" / "topic"


def discover_kb_topic_files(workspace: Path) -> list[Path]:
    """List every `*.md` under `public knowledge base/topic/`, excluding the
    KB-level meta files (`index.md`, `log.md`) at the topic root.

    Sorted by relative path (posix) for stable display.
    """
    root = kb_topic_root(workspace)
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*.md"):
        if not p.is_file():
            continue
        # Skip top-level meta (index.md / log.md) but keep nested files even
        # if they happen to be named index/log (rare).
        if p.parent == root and p.name in _KB_TOPIC_META:
            continue
        out.append(p)
    return sorted(out, key=lambda f: f.relative_to(root).as_posix())


# ---------- capture builder ----------


def _truncate_lines(text: str, max_lines: int) -> tuple[str, int]:
    """Return (head_text, total_lines)."""
    lines = text.splitlines()
    head = "\n".join(lines[:max_lines])
    return head, len(lines)


def build_synthesize_capture_markdown(
    clipping: WebClipping,
    kb_topic_files: list[Path],
    workspace: Path,
    captured_at: str,
) -> str:
    """Render the capture-import markdown for a `synthesize-clipping` flow.

    Sections:
      - frontmatter (kind: raw import + provenance)
      - ## Clipping summary  (title, source url, captured_at)
      - ## Candidate KB topics (workspace-relative paths the agent picks from)
      - ## Clipping body (head)  (first 80 lines of clipping body for grounding)
      - ## Filling guidance       (prose for agent on what to do next)
    """
    rel_clipping = clipping.path.relative_to(workspace).as_posix()
    body_parts: list[str] = []

    body_parts.append(f"# web-clipping synthesize: {clipping.slug}\n")
    body_parts.append("## Clipping summary\n")
    body_parts.append(f"- file: {rel_clipping}")
    if clipping.title:
        body_parts.append(f"- title: {clipping.title}")
    if clipping.source_url:
        body_parts.append(f"- source: {clipping.source_url}")
    if clipping.captured_at:
        body_parts.append(f"- captured_at: {clipping.captured_at}")
    body_parts.append("")

    body_parts.append("## Candidate KB topics\n")
    if not kb_topic_files:
        body_parts.append(
            "(no `public knowledge base/topic/*.md` files exist yet — "
            "agent may propose creating a new one in the proposal `propagation`.)"
        )
    else:
        body_parts.append(
            "Agent picks one or more of the following (or proposes a new "
            "topic page) when filling the proposal `propagation` field:"
        )
        body_parts.append("")
        kb_root = kb_topic_root(workspace)
        for f in kb_topic_files:
            try:
                rel = f.relative_to(workspace).as_posix()
            except ValueError:
                rel = str(f)
            body_parts.append(f"- {rel}")
    body_parts.append("")

    body_parts.append("## Clipping body (head)\n")
    head_text, total_lines = _truncate_lines(clipping.body.strip(), 80)
    if head_text:
        body_parts.append("```")
        body_parts.append(head_text)
        if total_lines > 80:
            body_parts.append(f"... (+{total_lines - 80} more lines)")
        body_parts.append("```")
    else:
        body_parts.append("(clipping body is empty)")
    body_parts.append("")

    body_parts.append("## Filling guidance\n")
    body_parts.append(
        "1. Decide which KB topic page (or pages) this clipping should update."
    )
    body_parts.append(
        "2. Fill the proposal `propagation` with `path:` pointing at the chosen"
    )
    body_parts.append(
        "   `public knowledge base/topic/...md` file(s); set `disposition: APPLY`"
    )
    body_parts.append(
        "   and describe the modification."
    )
    body_parts.append(
        "3. The clipping itself is NOT reviewed — only the KB topic change is."
    )
    body_parts.append(
        "4. After approve, forge stamps `synthesized_at` + `synthesized_into`"
    )
    body_parts.append(
        "   on the clipping frontmatter; the clipping file is not deleted."
    )
    body_parts.append("")

    body = "\n".join(body_parts).rstrip() + "\n"

    fm_lines = [
        "---",
        "kind: raw import",
        "type: web-clipping-synthesize",
        f"source: {yaml.safe_dump(rel_clipping, default_flow_style=True).strip()}",
        f"web_clipping: {rel_clipping}",
        f"clipping_slug: {clipping.slug}",
    ]
    if clipping.title:
        fm_lines.append(
            f"clipping_title: {yaml.safe_dump(clipping.title, default_flow_style=True, allow_unicode=True).strip()}"
        )
    if clipping.source_url:
        fm_lines.append(
            f"clipping_source_url: {yaml.safe_dump(clipping.source_url, default_flow_style=True).strip()}"
        )
    fm_lines.append(f"captured_at: {captured_at}")
    fm_lines.append("status: unreviewed")
    fm_lines.append("---")
    fm_lines.append("")
    return "\n".join(fm_lines) + body


# ---------- frontmatter write-back: mark as synthesized ----------


def mark_synthesized(
    clipping_path: Path,
    *,
    into: list[str],
    at: str,
) -> bool:
    """Stamp `synthesized_at` and `synthesized_into` on a clipping's frontmatter.

    Returns True when the frontmatter was modified, False when the file does
    not have a parseable frontmatter or path is missing. `into` is a list of
    workspace-relative paths the synthesize touched; if a previous
    synthesized_into already exists, the union (preserving order; new entries
    appended) is written.

    `at` is written verbatim — caller picks the timestamp format. Convention:
    ISO 8601 with a tz offset (matches v0.4/v0.5 last_synced.at).
    """
    try:
        text = clipping_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    fm, body = split_frontmatter(text)
    if fm is None:
        return False
    fm = dict(fm)

    # Merge synthesized_into: union of existing + new, preserving original order
    existing_raw = fm.get("synthesized_into") or []
    if isinstance(existing_raw, str):
        existing = [existing_raw]
    elif isinstance(existing_raw, list):
        existing = [str(s).strip() for s in existing_raw if str(s).strip()]
    else:
        existing = []
    merged: list[str] = list(existing)
    for entry in into:
        e = str(entry).strip()
        if e and e not in merged:
            merged.append(e)

    fm["synthesized_at"] = at
    fm["synthesized_into"] = merged
    new_text = join_frontmatter(fm, body)
    clipping_path.write_text(new_text, encoding="utf-8")
    return True


# ---------- monitor formatting ----------


def format_monitor_lines(workspace: Path) -> tuple[list[str], list[str]]:
    """Return (issues, actions) for `forge monitor` web-clipping section.

    `issues` lists summary lines (e.g. `web-clipping pending synthesize: 3`).
    `actions` lists per-clipping `next:` actions.

    Both lists are empty when no clippings are pending or the dir is missing.
    """
    pending = pending_clippings(workspace)
    if not pending:
        return [], []
    issues = [f"web-clipping pending synthesize: {len(pending)}"]
    actions: list[str] = []
    for c in pending[:5]:
        try:
            rel = c.path.relative_to(workspace).as_posix()
        except ValueError:
            rel = str(c.path)
        # Quote the path (it likely contains spaces — `web clipping/`)
        actions.append(f'forge synthesize-clipping "{rel}"')
    return issues, actions


# ---------- approve-time helpers ----------


def kb_topic_paths_from_propagation(
    workspace: Path,
    propagation: Iterable[dict],
) -> list[str]:
    """Extract every workspace-relative `public knowledge base/topic/...md`
    path mentioned anywhere in a proposal's propagation tree.

    `propagation` is the YAML-loaded list of `{branch, node, ...}` dicts (each
    `node` has a `path` and optional nested `children: [{branch, node}, ...]`).
    Walks the tree breadth-first and collects every node `path` that lives
    under `public knowledge base/topic/`.

    Returns posix paths in first-seen order, deduplicated.
    """
    seen: list[str] = []

    def _walk_node(node: dict | None) -> None:
        if not isinstance(node, dict):
            return
        path = str(node.get("path") or "").strip()
        if path and _is_kb_topic_path(path):
            if path not in seen:
                seen.append(path)
        for child in node.get("children") or []:
            if isinstance(child, dict):
                _walk_branch(child)

    def _walk_branch(branch: dict | None) -> None:
        if not isinstance(branch, dict):
            return
        node = branch.get("node")
        if isinstance(node, dict):
            _walk_node(node)

    for branch in propagation or []:
        _walk_branch(branch)
    return seen


def _is_kb_topic_path(path: str) -> bool:
    """Heuristic: a propagation `path` is a KB topic file iff it lives under
    `public knowledge base/topic/`. We keep this as a path-prefix string check
    rather than filesystem existence — proposals may legitimately propose
    creating a brand-new KB topic file that doesn't exist yet on disk.
    """
    norm = path.strip().lstrip("./")
    return norm.startswith("public knowledge base/topic/") and norm.endswith(".md")
