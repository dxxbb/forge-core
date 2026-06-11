"""Amnesty migration: settle the historical backlog once (AC-MIG-*).

Workbench items with a concrete patch are settled mechanically — state-zone
patches land through the ledger; rule-zone patches are written to disk where
the compile gate holds them as ask items for the next run. Everything else
(no patch, untriaged) leaves a trace in the report and the archived workbench.
The migration must never rebuild a queue: nothing here waits for the owner
except what surfaces in `forge run ask`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from forge import ledger as ledgerlib
from forge.audit.graph import build_audit_graph


@dataclass
class AmnestyReport:
    applied: int = 0
    rule_candidates: int = 0
    held_conflicts: int = 0
    skipped_no_patch: int = 0
    skipped_untriaged: int = 0
    failed: list[str] = field(default_factory=list)
    archived: list[str] = field(default_factory=list)


def migrate_amnesty(root: Path) -> AmnestyReport:
    root = Path(root).resolve()
    report = AmnestyReport()
    graph = build_audit_graph(root)
    for wb in graph.workbenches:
        if str(wb.status).startswith("archived"):
            continue
        migrated_ids: list[str] = []
        for item in wb.items:
            key = f"{wb.id}:{item.id}"
            if "triaged" not in str(item.status) or str(item.status) == "untriaged":
                report.skipped_untriaged += 1
                continue
            if item.patch is None:
                report.skipped_no_patch += 1
                continue
            result = ledgerlib.apply_write(
                root,
                target=item.patch.target,
                anchor=item.patch.anchor,
                mode=item.patch.mode if item.patch.mode != "unlocated" else "append",
                proposed_text=item.patch.proposed_text,
                origin=f"amnesty:{key}",
                evidence=[e.path for e in item.evidence] or [wb.path],
                title=item.title,
            )
            if result.state == "applied":
                migrated_ids.append(result.entry_id)
                from forge.zone import load_zones

                if load_zones(root).zone_for(item.patch.target) == "rule":
                    report.rule_candidates += 1
                else:
                    report.applied += 1
            elif result.state == "held":
                report.held_conflicts += 1
                migrated_ids.append(result.entry_id)
            else:
                report.failed.append(f"{key}: {result.error}")
        _archive_workbench(root, wb.path, migrated_ids)
        try:
            from forge.gate import _git

            _git.add(root, [wb.path])
            _git.commit(root, f"migrate: archive workbench {wb.id}")
        except Exception:  # noqa: BLE001 — archive still holds without git
            pass
        report.archived.append(wb.id)
    return report


def _archive_workbench(root: Path, relpath: str, migrated_ids: list[str]) -> None:
    path = root / relpath
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"^status: .*$", "status: archived-migrated", text, count=1, flags=re.MULTILINE)
    if migrated_ids and "migrated_to:" not in text:
        listing = "\n".join(f"  - {mid}" for mid in migrated_ids)
        text = re.sub(
            r"^status: archived-migrated$",
            "status: archived-migrated\nmigrated_to:\n" + listing,
            text,
            count=1,
            flags=re.MULTILINE,
        )
    path.write_text(text, encoding="utf-8")
