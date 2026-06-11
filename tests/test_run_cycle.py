"""The forge run cycle: open -> settle -> ask -> decide -> close.

Acceptance mapping: AC-RUN-* and AC-CERT-* in docs/run-acceptance-spec.md.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from forge import ledger, run
from forge.zone import certify, gate_drifts, zone_init


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


def test_run_open_fingerprints_inputs_and_resumes(tmp_path: Path) -> None:
    """AC-RUN-2/3: inputs keyed by fingerprint; reopening resumes; processed
    inputs never reappear."""
    ws = _workspace(tmp_path)
    capture = ws / "capture" / "import" / "memo.md"
    capture.parent.mkdir(parents=True)
    capture.write_text("# 会话残留\n\n一条新信息。\n", encoding="utf-8")

    record = run.open_run(ws)
    assert [i["path"] for i in record.inputs] == ["capture/import/memo.md"]
    # Reopen resumes the same run instead of double-collecting.
    assert run.open_run(ws).id == record.id

    run.close_run(ws)
    second = run.open_run(ws)
    assert second.id != record.id
    assert second.inputs == []  # same fingerprint not re-collected


def test_run_ask_orders_conflict_rule_cert_within_budget(tmp_path: Path) -> None:
    """AC-RUN-4: fixed order; conflicts never compressed; overflow deferred."""
    ws = _workspace(tmp_path)
    run.open_run(ws)
    # certification-due: certify then change additively
    certify(ws, "context build/sections/alpha.md")
    ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:进行中。\n新增:接入验收。",
        origin="run:test",
    )
    # conflict: drop a certified line
    held = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已下线。",
        origin="run:test",
    )
    assert held.state == "held"
    # rule-change: drift the rule file
    (ws / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 新规则候选。\n",
        encoding="utf-8",
    )

    items = run.ask(ws, budget=2)

    assert [i.type for i in items] == ["conflict", "rule-change", "certification-due"]
    assert not items[0].deferred and not items[1].deferred
    assert items[2].deferred  # over budget -> deferred, not lost
    assert "已下线" in items[0].detail and "新规则候选" in items[1].detail


def test_run_decide_rule_change_approve_then_reject(tmp_path: Path) -> None:
    """AC-RUN-5 / AC-GATE-3: approve updates the verified snapshot; reject
    restores the disk file."""
    ws = _workspace(tmp_path)
    run.open_run(ws)
    pref = ws / "context build" / "sections" / "preference.md"
    pref.write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 交付前跑 security-review。\n",
        encoding="utf-8",
    )

    outcome = run.decide(ws, "rule:context build/sections/preference.md", "approve")
    assert outcome["state"] == "approved"
    assert gate_drifts(ws) == []
    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "security-review" in runtime.read_text(encoding="utf-8")

    pref.write_text(
        pref.read_text(encoding="utf-8") + "- 不该有的规则。\n", encoding="utf-8"
    )
    outcome = run.decide(ws, "rule:context build/sections/preference.md", "reject")
    assert outcome["state"] == "rejected"
    assert "不该有的规则" not in pref.read_text(encoding="utf-8")
    assert gate_drifts(ws) == []


def test_run_decide_conflict_approve_applies_held_write(tmp_path: Path) -> None:
    """AC-RUN-5: an owner-approved conflict lands through the full pipeline."""
    ws = _workspace(tmp_path)
    record = run.open_run(ws)
    certify(ws, "context build/sections/alpha.md")
    held = ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:已下线。",
        origin="run:test",
        title="alpha 下线",
    )

    outcome = run.decide(ws, held.entry_id, "approve")

    assert outcome["state"] == "applied"
    alpha = ws / "context build" / "sections" / "alpha.md"
    assert "已下线" in alpha.read_text(encoding="utf-8")
    decided = next(e for e in ledger.list_entries(ws) if e.id == held.entry_id)
    assert decided.state == "decided-approved"
    applied = next(e for e in ledger.list_entries(ws) if e.id == outcome["entry"])
    assert applied.origin == f"run:{record.id}"


def test_run_close_reports_and_run_status_counts(tmp_path: Path) -> None:
    """AC-RUN-1/6: close writes the report; status answers without a run."""
    ws = _workspace(tmp_path)
    record = run.open_run(ws)
    ledger.apply_write(
        ws,
        target="context build/sections/alpha.md",
        anchor="## 当前状态",
        mode="replace",
        proposed_text="## 当前状态\n\nAlpha 项目状态:推进中。",
        origin=f"run:{record.id}",
    )

    report = run.close_run(ws)

    assert report["settled"] == 1
    text = (ws / "system" / "run" / f"{record.id}.md").read_text(encoding="utf-8")
    assert "status: closed" in text and "结算报告" in text

    info = run.status(ws)
    assert info["open_run"] is None
    assert info["days_since_last_run"] == 0
    assert info["ask_counts"]["conflict"] == 0


def test_cli_run_and_certify_smoke(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from forge.cli import main

    ws = _workspace(tmp_path)
    runner = CliRunner()

    assert runner.invoke(main, ["run", "open", "--root", str(ws)]).exit_code == 0
    status = runner.invoke(main, ["run", "status", "--root", str(ws)])
    assert status.exit_code == 0 and "open_run" in status.output

    certified = runner.invoke(
        main, ["certify", "context build/sections/alpha.md", "--root", str(ws)]
    )
    assert certified.exit_code == 0
    # Standalone certify commits its snapshot (AC-CERT-1).
    assert "certify: context build/sections/alpha.md" in _git(ws, "log", "-1", "--format=%s")

    shown = runner.invoke(
        main, ["state", "show", "context build/sections/alpha.md", "--root", str(ws)]
    )
    assert shown.exit_code == 0 and "无未认证变更" in shown.output

    closed = runner.invoke(main, ["run", "close", "--root", str(ws)])
    assert closed.exit_code == 0
