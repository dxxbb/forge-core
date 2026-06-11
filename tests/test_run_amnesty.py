"""Amnesty migration: clear the backlog once, never rebuild the graveyard.

Acceptance mapping: AC-MIG-* in docs/run-acceptance-spec.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge import ledger
from forge.migrate import migrate_amnesty
from forge.zone import gate_drifts, zone_init


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _workspace(root: Path) -> Path:
    sections = root / "context build" / "sections"
    config = root / "context build" / "config"
    sections.mkdir(parents=True)
    config.mkdir(parents=True)
    (sections / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled context.\n", encoding="utf-8"
    )
    (sections / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n", encoding="utf-8"
    )
    (sections / "alpha.md").write_text(
        "---\nname: alpha\ntype: project\n---\n\n## 当前状态\n\nAlpha 项目状态:进行中。\n",
        encoding="utf-8",
    )
    (config / "agents-md.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - _preface\n  - preference\n  - alpha\n---\n",
        encoding="utf-8",
    )
    (root / "context build" / "zones.yaml").write_text(
        'rule_zone:\n  - "context build/sections/preference.md"\n', encoding="utf-8"
    )
    zone_init(root)

    wb = root / "system" / "pr" / "20260609-memory-import" / "workbench.md"
    wb.parent.mkdir(parents=True)
    wb.write_text(
        "---\n"
        "kind: memory-import-workbench\n"
        "status: batch-A-user-review-required\n"
        "workbench_id: 20260609-memory-import\n"
        "current_batch: A\n"
        "final_pr_ready: false\n"
        "---\n\n"
        "# wb\n\n"
        "## Step 1: Information Items\n\n"
        "| id | item | initial domain | batch | status |\n"
        "|---:|---|---|---|---|\n"
        "| 01 | alpha 状态更新 | project | A | triaged-awaiting-user |\n"
        "| 02 | 新工作规则 | rule | A | triaged-awaiting-user |\n"
        "| 03 | 没有 patch 的条目 | misc | A | triaged-awaiting-user |\n"
        "| 04 | 未分诊旧闻 | misc | B | untriaged |\n\n"
        "## Batch A Triage\n\n"
        "### Item 01: alpha 状态更新\n\n"
        "- proposed_disposition: APPLY\n"
        "- proposed_patch_target: context build/sections/alpha.md\n"
        "- proposed_patch_anchor: ## 当前状态\n"
        "- proposed_patch_text:\n"
        "  ## 当前状态\n"
        "  Alpha 项目状态:进行中。\n"
        "  补充:历史积压里的有效更新。\n\n"
        "### Item 02: 新工作规则\n\n"
        "- proposed_disposition: APPLY\n"
        "- proposed_patch_target: context build/sections/preference.md\n"
        "- proposed_patch_anchor: \n"
        "- proposed_patch_text:\n"
        "  - 历史积压里的规则候选。\n\n"
        "### Item 03: 没有 patch 的条目\n\n"
        "- proposed_disposition: APPLY\n"
        "- notable_content: 只有解释没有 patch。\n",
        encoding="utf-8",
    )

    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def test_amnesty_settles_state_items_and_routes_rules_to_the_gate(tmp_path: Path) -> None:
    """AC-MIG-1/2/4: state patches land as ledger entries; rule patches become
    gate drift (ask items); no-patch and untriaged items only leave traces."""
    ws = _workspace(tmp_path)

    report = migrate_amnesty(ws)

    # State item applied through the ledger.
    alpha = ws / "context build" / "sections" / "alpha.md"
    assert "历史积压里的有效更新" in alpha.read_text(encoding="utf-8")
    assert report.applied == 1
    booked = [e for e in ledger.list_entries(ws) if e.origin.startswith("amnesty:")]
    assert len(booked) >= 1

    # Rule item written to disk but held by the compiler gate -> ask item.
    assert report.rule_candidates == 1
    drifts = gate_drifts(ws)
    assert any("preference.md" in d.relpath for d in drifts)
    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "历史积压里的规则候选" not in runtime.read_text(encoding="utf-8")

    # No-patch + untriaged leave traces only; no new queue is rebuilt.
    assert report.skipped_no_patch == 1
    assert report.skipped_untriaged == 1

    # Workbench is archived and stops being a decision surface.
    wb_text = (ws / "system" / "pr" / "20260609-memory-import" / "workbench.md").read_text(
        encoding="utf-8"
    )
    assert "status: archived-migrated" in wb_text


def test_amnesty_is_idempotent(tmp_path: Path) -> None:
    """AC-MIG-3: re-running books nothing twice."""
    ws = _workspace(tmp_path)
    first = migrate_amnesty(ws)
    entries_after_first = len(ledger.list_entries(ws))

    second = migrate_amnesty(ws)

    assert first.applied == 1 and second.applied == 0
    assert len(ledger.list_entries(ws)) == entries_after_first
