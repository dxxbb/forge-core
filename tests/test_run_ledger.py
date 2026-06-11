"""Ledger: every canonical write is recorded, scoped-committed, revertible.

Acceptance mapping: AC-LEDGER-* in docs/run-acceptance-spec.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge import ledger
from forge.zone import zone_init


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
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "base")
    return root


def test_state_write_lands_with_ledger_entry_and_scoped_commit(tmp_path: Path) -> None:
    """AC-LEDGER-1/2: one write -> one entry -> one scoped commit with trailer."""
    ws = _workspace(tmp_path)
    # An unrelated dirty file must NOT be swept into the scoped commit.
    bystander = ws / "context build" / "sections" / "_preface.md"
    bystander.write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled context. (本地未提交修改)\n",
        encoding="utf-8",
    )

    result = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已上线。",
        origin="run:test",
        evidence=["capture/session-0610.md"],
        title="alpha 上线",
    )

    assert result.state == "applied"
    assert result.entry_id.startswith("led-")
    # Target updated on disk.
    assert "已上线" in (ws / "context build" / "sections" / "alpha.md").read_text(encoding="utf-8")
    # Entry file exists and is committed.
    entry_path = ws / "system" / "ledger" / f"{result.entry_id}.md"
    assert entry_path.exists()
    # Commit is scoped: contains target + runtime + entry, not the bystander.
    committed = _git(ws, "show", "--name-only", "--format=", "HEAD").strip().splitlines()
    assert "context build/sections/alpha.md" in committed
    assert f"system/ledger/{result.entry_id}.md" in committed
    assert not any("_preface.md" in f for f in committed)
    # Trailer links commit <-> entry (AC-LEDGER-2).
    log = _git(ws, "log", "-1", "--format=%B")
    assert f"Ledger-Id: {result.entry_id}" in log
    # Bystander stays dirty in the working tree.
    assert "本地未提交修改" in bystander.read_text(encoding="utf-8")
    status = _git(ws, "status", "--porcelain")
    assert "_preface.md" in status


def test_stale_ledger_write_refuses_blind_apply(tmp_path: Path) -> None:
    """AC-LEDGER-4: base digest drift -> zero writes, no commit."""
    from forge.patch import block_digest, extract_block

    ws = _workspace(tmp_path)
    alpha = ws / "context build" / "sections" / "alpha.md"
    digest = block_digest(extract_block(alpha.read_text(encoding="utf-8"), "## 当前状态"))
    # Someone else moves the block before our patch lands.
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace("进行中", "已暂停"), encoding="utf-8"
    )
    _git(ws, "add", "-A")
    _git(ws, "commit", "-qm", "drift")
    head_before = _git(ws, "rev-parse", "HEAD").strip()

    result = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已上线。",
        origin="run:test",
        base_digest=digest,
    )

    assert result.state == "stale"
    assert "已暂停" in alpha.read_text(encoding="utf-8")  # untouched
    assert _git(ws, "rev-parse", "HEAD").strip() == head_before  # no commit


def test_failed_pipeline_restores_every_written_byte(tmp_path: Path) -> None:
    """AC-LEDGER-5: atomicity — a commit failure rolls back target and entry."""
    ws = _workspace(tmp_path)
    alpha = ws / "context build" / "sections" / "alpha.md"
    original = alpha.read_text(encoding="utf-8")
    hook = ws / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    head_before = _git(ws, "rev-parse", "HEAD").strip()

    result = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已上线。",
        origin="run:test",
    )

    assert result.state == "failed"
    assert alpha.read_text(encoding="utf-8") == original
    assert not list((ws / "system" / "ledger").glob("led-*.md")) if (
        ws / "system" / "ledger"
    ).exists() else True
    assert _git(ws, "rev-parse", "HEAD").strip() == head_before


def _applied_entry(ws: Path) -> str:
    result = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已上线。",
        origin="run:test",
        title="alpha online",
    )
    assert result.state == "applied"
    return result.entry_id


def test_ledger_revert_undoes_a_single_write(tmp_path: Path) -> None:
    """AC-LEDGER-6: one command reverses one entry, with its own commit."""
    ws = _workspace(tmp_path)
    entry_id = _applied_entry(ws)
    alpha = ws / "context build" / "sections" / "alpha.md"

    result = ledger.revert(ws, entry_id)

    assert result.state == "applied"
    assert "进行中" in alpha.read_text(encoding="utf-8")
    assert "已上线" not in alpha.read_text(encoding="utf-8")
    # The original entry is marked reverted; the revert itself is ledgered.
    original = next(e for e in ledger.list_entries(ws) if e.id == entry_id)
    assert original.state == "reverted"
    log = _git(ws, "log", "-1", "--format=%B")
    assert f"Ledger-Id: {result.entry_id}" in log


def test_ledger_revert_refuses_when_block_drifted(tmp_path: Path) -> None:
    """AC-LEDGER-6: never guess — drifted content is not blindly reverted."""
    ws = _workspace(tmp_path)
    entry_id = _applied_entry(ws)
    alpha = ws / "context build" / "sections" / "alpha.md"
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace("已上线", "已上线并完成验收"),
        encoding="utf-8",
    )

    result = ledger.revert(ws, entry_id)

    assert result.state == "failed"
    assert "并完成验收" in alpha.read_text(encoding="utf-8")  # untouched


def test_ledger_blame_answers_why_is_this_line_here(tmp_path: Path) -> None:
    """AC-LEDGER-8: a line traces back to the write that produced it."""
    ws = _workspace(tmp_path)
    entry_id = _applied_entry(ws)
    alpha = ws / "context build" / "sections" / "alpha.md"
    lines = alpha.read_text(encoding="utf-8").splitlines()
    line_no = next(i + 1 for i, ln in enumerate(lines) if "已上线" in ln)

    entry = ledger.blame(ws, "context build/sections/alpha.md", line_no)

    assert entry is not None
    assert entry.id == entry_id
    assert entry.origin == "run:test"


def test_reconcile_ledgers_state_edits_and_flags_rule_drift(tmp_path: Path) -> None:
    """AC-LEDGER-3: out-of-band edits get booked; rule-zone drift never auto-books."""
    ws = _workspace(tmp_path)
    alpha = ws / "context build" / "sections" / "alpha.md"
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace("进行中", "推进到 beta"), encoding="utf-8"
    )
    pref = ws / "context build" / "sections" / "preference.md"
    pref.write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 绕过 gate 的规则。\n",
        encoding="utf-8",
    )

    report = ledger.reconcile(ws)

    assert "context build/sections/alpha.md" in report.ledgered
    assert "context build/sections/preference.md" in report.rule_drifts
    # The state edit is now booked + committed with origin manual-reconciled.
    entries = ledger.list_entries(ws)
    booked = next(e for e in entries if e.target == "context build/sections/alpha.md")
    assert booked.origin == "manual-reconciled"
    status = _git(ws, "status", "--porcelain")
    assert "alpha.md" not in status
    # Rule drift stays uncommitted: the gate, not reconcile, owns that path.
    assert "preference.md" in status


def test_conflict_guard_holds_writes_that_contradict_certified_content(tmp_path: Path) -> None:
    """AC-LEDGER-7 / AC-CERT-3: certified truth is never silently overwritten,
    while additive updates keep flowing."""
    from forge.zone import certify

    ws = _workspace(tmp_path)
    certify(ws, "context build/sections/alpha.md")

    # Additive update: every certified line survives -> flows normally.
    additive = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:进行中。\n下一步:接入验收环境。",
        origin="run:test",
    )
    assert additive.state == "applied"

    # Contradicting update: a certified line disappears -> held, zero writes.
    before = (ws / "context build" / "sections" / "alpha.md").read_text(encoding="utf-8")
    conflicting = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已下线。",
        origin="run:test",
    )
    assert conflicting.state == "held"
    assert (ws / "context build" / "sections" / "alpha.md").read_text(encoding="utf-8") == before
    held = next(e for e in ledger.list_entries(ws) if e.id == conflicting.entry_id)
    assert held.state == "held-conflict"


def test_certify_stamps_date_and_state_show_highlights_uncertified(tmp_path: Path) -> None:
    """AC-CERT-1/2: certification snapshots the file; reading shows what's new."""
    from forge.zone import certified_info, certify, uncertified_diff

    ws = _workspace(tmp_path)
    certify(ws, "context build/sections/alpha.md")
    info = certified_info(ws, "context build/sections/alpha.md")
    assert info is not None and info.date

    # No changes yet.
    assert uncertified_diff(ws, "context build/sections/alpha.md") == []

    ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:进行中。\n新增:开始接入验收环境。",
        origin="run:test",
    )
    changed = uncertified_diff(ws, "context build/sections/alpha.md")
    assert any("接入验收环境" in line for line in changed)

    # Re-certify resets the baseline (AC-CERT-1).
    certify(ws, "context build/sections/alpha.md")
    assert uncertified_diff(ws, "context build/sections/alpha.md") == []


def test_cli_ledger_list_blame_and_reconcile(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from forge.cli import main

    ws = _workspace(tmp_path)
    entry_id = _applied_entry(ws)
    runner = CliRunner()

    listed = runner.invoke(main, ["ledger", "list", "--root", str(ws)])
    assert listed.exit_code == 0
    assert entry_id in listed.output

    blamed = runner.invoke(
        main,
        ["ledger", "blame", "context build/sections/alpha.md", "--line", "7", "--root", str(ws)],
    )
    assert blamed.exit_code == 0

    clean = runner.invoke(main, ["ledger", "reconcile", "--root", str(ws)])
    assert clean.exit_code == 0
    assert "clean" in clean.output
