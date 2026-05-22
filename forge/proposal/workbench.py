"""Staged workbench for large context imports.

`proposal.md` is the final approval surface. Large agent-memory imports need a
smaller-grained, resumable artifact before that final PR exists: first list
items, then triage in batches, cross-review, self-check, and only later produce
the final proposal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from forge.proposal.scaffold import (
    _capture_files_from_inbox_source,
    _monitor_info_from_inbox,
    _read_yaml_frontmatter,
    derive_pr_id,
)


TASK_GROUP_RE = re.compile(r"^# Task Group:\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class WorkbenchItem:
    id: str
    title: str
    source: str
    initial_domain: str = "unclassified"
    batch: str = "A"
    status: str = "untriaged"


def extract_workbench_items(capture_text: str, *, source_label: str) -> list[WorkbenchItem]:
    """Extract review items from a raw capture.

    Codex memory captures include a generated MEMORY.md with `# Task Group:`
    headings. Use those as item boundaries. Fallback to one item for the whole
    capture when no task-group index exists.
    """
    titles = [m.group(1).strip() for m in TASK_GROUP_RE.finditer(capture_text)]
    if not titles:
        return [
            WorkbenchItem(
                id="01",
                title=source_label,
                source=source_label,
                batch="A",
            )
        ]

    out: list[WorkbenchItem] = []
    for idx, title in enumerate(titles, start=1):
        out.append(
            WorkbenchItem(
                id=f"{idx:02d}",
                title=title,
                source=source_label,
                initial_domain=_guess_domain(title),
                batch=_batch_for_index(idx),
            )
        )
    return out


def _batch_for_index(idx: int, *, batch_size: int = 5) -> str:
    return chr(ord("A") + ((idx - 1) // batch_size))


def _guess_domain(title: str) -> str:
    t = title.lower()
    if "forge" in t:
        return "forge workflow"
    if "project" in t or "workspace" in t:
        return "project"
    if "portfolio" in t or "fund" in t or "qdii" in t or "a-share" in t:
        return "finance"
    if "health" in t or "insomnia" in t or "cbd" in t:
        return "private health"
    if "opc" in t or "registration" in t or "retirement" in t or "insurance" in t:
        return "policy / private planning"
    if "writing" in t or "documentation" in t:
        return "workflow / writing"
    return "unclassified"


def scaffold_workbench(
    workspace: Path,
    inbox_files: list[Path],
    *,
    title: str = "context-import-workbench",
    now: datetime | None = None,
) -> Path:
    """Create `system/pr/<id>/workbench.md` for staged import triage."""
    if not inbox_files:
        raise ValueError("scaffold_workbench: no inbox files given")
    now = now or datetime.now().astimezone()
    workbench_id = derive_pr_id(now, title)
    wb_dir = workspace / "system" / "pr" / workbench_id
    if wb_dir.exists():
        i = 1
        while True:
            candidate = workspace / "system" / "pr" / f"{workbench_id}-{i}"
            if not candidate.exists():
                wb_dir = candidate
                break
            i += 1
    wb_dir.mkdir(parents=True, exist_ok=False)

    inbox_sources: list[str] = []
    capture_paths: list[Path] = []
    for ip in inbox_files:
        inbox_sources.append(ip.relative_to(workspace).as_posix())
        fm, _body = _read_yaml_frontmatter(ip)
        sources = fm.get("source", []) or []
        if isinstance(sources, str):
            sources = [sources]
        for s in sources:
            capture_paths.extend(_capture_files_from_inbox_source(workspace, str(s)))

    seen: set[str] = set()
    unique_captures: list[Path] = []
    for p in capture_paths:
        key = p.resolve().as_posix()
        if key not in seen:
            seen.add(key)
            unique_captures.append(p)

    items: list[WorkbenchItem] = []
    for capture in unique_captures:
        rel = capture.relative_to(workspace).as_posix()
        text = capture.read_text(encoding="utf-8", errors="ignore")
        items.extend(extract_workbench_items(text, source_label=rel))
    if not items:
        for idx, ip in enumerate(inbox_files, start=1):
            items.append(
                WorkbenchItem(
                    id=f"{idx:02d}",
                    title=_monitor_info_from_inbox(ip),
                    source=ip.relative_to(workspace).as_posix(),
                    batch=_batch_for_index(idx),
                )
            )

    out_path = wb_dir / "workbench.md"
    out_path.write_text(
        render_workbench(
            workbench_id=wb_dir.name,
            created_at=now.isoformat(timespec="seconds"),
            inbox_sources=inbox_sources,
            capture_sources=[p.relative_to(workspace).as_posix() for p in unique_captures],
            items=items,
        ),
        encoding="utf-8",
    )
    return out_path


def render_workbench(
    *,
    workbench_id: str,
    created_at: str,
    inbox_sources: list[str],
    capture_sources: list[str],
    items: list[WorkbenchItem],
) -> str:
    fm: dict[str, Any] = {
        "kind": "memory-import-workbench",
        "status": "step-1-item-list-ready",
        "created_at": created_at,
        "workbench_id": workbench_id,
        "inbox_sources": inbox_sources,
        "capture_sources": capture_sources,
        "current_batch": "A",
        "final_pr_ready": False,
    }
    lines: list[str] = [
        "---",
        yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip(),
        "---",
        "",
        "# Memory import workbench",
        "",
        "This is a resumable staged workbench. It is not the final approval PR.",
        "",
        "## Process",
        "",
        "1. Process inbox: list collected information items.",
        "2. Understand item-by-item: extract notable preferences, project-state updates, plan changes, workflow rules, and failures.",
        "3. Recommend disposition for each item.",
        "4. Cross-review item decisions with another agent/reviewer.",
        "5. Self-check and revise.",
        "6. User review item-by-item.",
        "7. Apply user judgment.",
        "8. Finalize accepted changes into a real proposal, then build/doctor/diff.",
        "",
        "## Required Item Fields",
        "",
        "- `source_evidence`",
        "- `canonical_sink_status`: `verified-existing` / `candidate` / `missing` / `not-applicable`",
        "- `fact_volatility`: `stable preference` / `project state` / `policy` / `market` / `private case`",
        "- `live_verify_required`",
        "- `privacy_level`",
        "- `apply_scope`: `mechanism` / `canonical-source` / `runtime` / `no-op`",
        "- `covered_by` for every `COVERED` item",
        "- `user_review_payload`: source, proposed change, exact diff intent, propagation chain, reason, alternatives",
        "",
        "## Dispositions",
        "",
        "- `IGNORE`: no durable value, obsolete, too noisy, or unsafe to import.",
        "- `COVERED`: already represented in a verified canonical sink.",
        "- `APPLY`: introduce a concrete change, with scope stated explicitly.",
        "- `SPLIT`: item contains multiple independent dispositions.",
        "- `NEEDS-LIVE-VERIFY`: useful but current truth depends on external/repo state.",
        "",
        "## Step 1: Information Items",
        "",
        "| id | item | initial domain | batch | status |",
        "|---:|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            f"| {item.id} | {item.title} | {item.initial_domain} | {item.batch} | {item.status} |"
        )

    lines.extend(
        [
            "",
            "## Batch Template",
            "",
            "```markdown",
            "### Item NN: <title>",
            "",
            "- source_evidence:",
            "- notable_content:",
            "- existing_canonical_sink:",
            "- canonical_sink_status:",
            "- fact_volatility:",
            "- live_verify_required:",
            "- privacy_level:",
            "- proposed_disposition:",
            "- apply_scope:",
            "- proposed_change:",
            "- propagation_chain:",
            "- why:",
            "- alternatives:",
            "- cross_review:",
            "- self_check:",
            "- user_decision:",
            "- final_action:",
            "```",
            "",
            "## Cross-review",
            "",
            "Pending.",
            "",
        ]
    )
    return "\n".join(lines)
