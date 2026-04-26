"""Compose a one-screen review: origin + semantic summary + affects + bench + raw diff.

The point: when the user runs `forge review`, they should see in one screen
WHY the change happened, WHAT it does (semantically), WHO will read it
(which agents/runtimes), how big the change is (bench), AND the raw diff
to verify the story.

This module produces structured data; rendering lives in cli.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.compiler.renderer import render
from forge.gate.actions import diff_summary
from forge.gate.origin import read_pending
from forge.gate.state import GateState


# Adapter name → human-readable description (which agent reads this view)
ADAPTER_DESCRIPTIONS: dict[str, str] = {
    "claude-code": "Claude Code (every session)",
    "agents-md": "Codex / OpenCode / any AGENTS.md-aware tool",
    "cursor": "Cursor IDE",
    "codex-cli": "OpenAI Codex CLI",
    "rulesync-bridge": "rulesync (multi-tool fanout)",
}


@dataclass
class SectionChange:
    """One section's semantic story."""
    name: str  # section file name without .md
    summary: str  # one-line human-readable description
    bytes_before: int
    bytes_after: int
    lines_added: int
    lines_removed: int

    @property
    def bytes_delta(self) -> int:
        return self.bytes_after - self.bytes_before

    @property
    def growth_pct(self) -> float:
        if self.bytes_before == 0:
            return float("inf") if self.bytes_after else 0.0
        return (self.bytes_after - self.bytes_before) / self.bytes_before * 100


@dataclass
class OutputChange:
    """One compiled config's output delta."""
    config_name: str
    adapter: str
    filename: str  # e.g. CLAUDE.md
    bytes_before: int
    bytes_after: int
    lines_added: int
    lines_removed: int
    runtime_description: str  # human-readable: "Claude Code (every session)"

    @property
    def bytes_delta(self) -> int:
        return self.bytes_after - self.bytes_before


@dataclass
class TargetBinding:
    """One configured external sync target (e.g. ~/.claude/CLAUDE.md)."""
    adapter: str
    path: str
    mode: str


@dataclass
class ReviewSummary:
    """Everything needed to render one review screen."""
    has_changes: bool
    origin_events: list  # list[OriginEvent]
    section_changes: list[SectionChange] = field(default_factory=list)
    output_changes: list[OutputChange] = field(default_factory=list)
    target_bindings: list[TargetBinding] = field(default_factory=list)
    diff_result: object | None = None  # the gate.DiffResult used for raw-diff rendering


def build_review(root: Path) -> ReviewSummary:
    """Collect everything for one review screen."""
    state = GateState(root)
    diff = diff_summary(root)

    if not diff.changed:
        return ReviewSummary(has_changes=False, origin_events=[])

    section_changes = _section_changes(state)
    output_changes = _output_changes(state, diff)
    targets = _target_bindings(state)
    origin_events = read_pending(root)

    return ReviewSummary(
        has_changes=True,
        origin_events=origin_events,
        section_changes=section_changes,
        output_changes=output_changes,
        target_bindings=targets,
        diff_result=diff,
    )


# ---------- section semantic summary ----------

def _section_changes(state: GateState) -> list[SectionChange]:
    """Walk every section file and produce one SectionChange per modified one."""
    approved_files = _read_section_dir_at_head(state)
    current_files = _read_section_dir(state.current_sp)
    changes: list[SectionChange] = []
    for name in sorted(set(approved_files) | set(current_files)):
        a = approved_files.get(name, "")
        b = current_files.get(name, "")
        if a == b:
            continue
        a_lines = a.splitlines()
        b_lines = b.splitlines()
        # crude but effective: line set difference
        added = sum(1 for ln in b_lines if ln not in a_lines)
        removed = sum(1 for ln in a_lines if ln not in b_lines)
        summary = _semantic_summary(name, a, b)
        changes.append(
            SectionChange(
                name=name,
                summary=summary,
                bytes_before=len(a),
                bytes_after=len(b),
                lines_added=added,
                lines_removed=removed,
            )
        )
    return changes


def _read_section_dir(sp_dir: Path) -> dict[str, str]:
    """Read sp_dir/section/*.md → {section-name (no .md): content}."""
    out: dict[str, str] = {}
    section_dir = sp_dir / "section"
    if not section_dir.exists():
        return out
    for f in sorted(section_dir.glob("*.md")):
        out[f.stem] = f.read_text(encoding="utf-8")
    return out


def _read_section_dir_at_head(state: GateState) -> dict[str, str]:
    """Read sp/section/*.md from git HEAD."""
    from forge.gate import _git

    head = _git.head_hash(state.root)
    if head is None:
        return {}
    files = _git.list_files_at_ref(state.root, head, "sp/section/")
    out: dict[str, str] = {}
    for relpath in files:
        if not relpath.endswith(".md"):
            continue
        name = Path(relpath).stem
        out[name] = _git.show_at_ref(state.root, head, relpath)
    return out


_TODO_RE = re.compile(r"\[TODO:.*?\]")
_BULLET_RE = re.compile(r"^[\s]*[-*]\s+")


def _semantic_summary(name: str, before: str, after: str) -> str:
    """One-line plain-language description of what changed in this section.

    v0.1: heuristics over (TODO marker, bullet count, H1/H2 count, body size).
    v0.2 might call an LLM for richer summaries, but heuristics carry far.
    """
    if not before.strip():
        return f"new section (was empty)"
    if not after.strip():
        return f"section emptied (consider whether you meant to delete it)"

    todos_before = len(_TODO_RE.findall(before))
    todos_after = len(_TODO_RE.findall(after))

    bullets_before = sum(1 for ln in before.splitlines() if _BULLET_RE.match(ln))
    bullets_after = sum(1 for ln in after.splitlines() if _BULLET_RE.match(ln))

    h1_before = sum(1 for ln in before.splitlines() if ln.startswith("# "))
    h1_after = sum(1 for ln in after.splitlines() if ln.startswith("# "))
    h2_before = sum(1 for ln in before.splitlines() if ln.startswith("## "))
    h2_after = sum(1 for ln in after.splitlines() if ln.startswith("## "))

    parts: list[str] = []

    # Big signal: TODO placeholder filled in
    if todos_before > 0 and todos_after < todos_before:
        delta = todos_before - todos_after
        parts.append(f"filled {delta} TODO placeholder{'s' if delta > 1 else ''}")
    elif todos_after > todos_before:
        parts.append(f"added {todos_after - todos_before} TODO marker(s)")

    # Bullets
    bd = bullets_after - bullets_before
    if bd > 0:
        parts.append(f"+{bd} bullet rule{'s' if bd > 1 else ''}")
    elif bd < 0:
        parts.append(f"−{-bd} bullet rule{'s' if -bd > 1 else ''}")

    # Section structure
    sd = (h1_after + h2_after) - (h1_before + h2_before)
    if sd > 0:
        parts.append(f"+{sd} subsection{'s' if sd > 1 else ''}")
    elif sd < 0:
        parts.append(f"−{-sd} subsection{'s' if -sd > 1 else ''}")

    if not parts:
        # Fallback: just report byte delta
        bytes_delta = len(after) - len(before)
        sign = "+" if bytes_delta >= 0 else ""
        parts.append(f"body edits ({sign}{bytes_delta}B)")

    return ", ".join(parts)


# ---------- output / affects ----------

def _output_changes(state: GateState, diff) -> list[OutputChange]:
    """For each config affected, compute byte/line delta + adapter description."""
    from forge.gate.actions import _load_sections_at_head, _load_configs_at_head
    from forge.targets import get_adapter

    approved_sections = _load_sections_at_head(state)
    approved_configs = _load_configs_at_head(state)
    current_sections = load_sections(state.root)
    current_configs = load_all_configs(state.root)

    out: list[OutputChange] = []
    for cname in diff.output_diffs:
        a_text = render(approved_sections, approved_configs[cname]) if cname in approved_configs else ""
        b_text = render(current_sections, current_configs[cname]) if cname in current_configs else ""
        adapter_name = (current_configs.get(cname) or approved_configs.get(cname)).target
        adapter = get_adapter(adapter_name)
        filename = adapter.filename(current_configs.get(cname) or approved_configs[cname])
        added = sum(1 for ln in b_text.splitlines() if ln not in a_text.splitlines())
        removed = sum(1 for ln in a_text.splitlines() if ln not in b_text.splitlines())
        out.append(
            OutputChange(
                config_name=cname,
                adapter=adapter_name,
                filename=filename,
                bytes_before=len(a_text),
                bytes_after=len(b_text),
                lines_added=added,
                lines_removed=removed,
                runtime_description=ADAPTER_DESCRIPTIONS.get(
                    adapter_name, f"unknown adapter `{adapter_name}`"
                ),
            )
        )
    return out


def _target_bindings(state: GateState) -> list[TargetBinding]:
    """Read manifest.targets → list of TargetBinding."""
    if not state.initialized():
        return []
    manifest = state.read_manifest()
    return [
        TargetBinding(adapter=t["adapter"], path=t["path"], mode=t.get("mode", "copy"))
        for t in manifest.get("targets", [])
    ]
