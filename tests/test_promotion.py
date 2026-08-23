"""Evidence-to-Asset Promotion: observations, candidates, and run review."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess

import pytest

from forge import run
from forge.promotion import (
    create_candidate,
    expire_observations,
    list_candidates,
    list_observations,
    record_asset_feedback,
    record_observation,
    revise_candidate,
)


def test_observation_merges_independent_evidence_and_expires_without_deleting_it(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)

    first = record_observation(
        tmp_path,
        theme="一次性 Bug 不应晋升为长期规则",
        evidence=["capture/session-a.md"],
        note="第一次出现",
        expires_days=30,
        now=now,
    )
    second = record_observation(
        tmp_path,
        theme="一次性 Bug 不应晋升为长期规则",
        evidence=["capture/session-b.md", "capture/session-a.md"],
        note="独立场景再次出现",
        expires_days=30,
        now=now + timedelta(days=2),
    )

    assert second.id == first.id
    assert second.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert second.independent_events == 2

    expired = expire_observations(tmp_path, now=now + timedelta(days=33))

    assert expired == [first.id]
    stored = list_observations(tmp_path, include_closed=True)[0]
    assert stored.state == "closed"
    assert stored.closed_reason == "expired"
    assert stored.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert stored.path is not None and stored.path.is_file()


def test_candidate_admission_requires_a_real_promotion_ground(tmp_path: Path) -> None:
    common = {
        "title": "把一次性 Bug 留在代码层解决",
        "ground": "repeated",
        "problem": "多个独立任务把一次性缺陷直接写成了永久行为规则。",
        "proposal": "一次性缺陷默认修代码并增加回归测试，不晋升为长期规则。",
        "scope": "由实现缺陷导致、可通过代码或测试确定性解决的问题。",
        "exclusions": ["用户明确要求长期遵守", "跨项目重复出现的协作模式"],
        "target": "context build/sections/preference.md",
        "anchor": "## 工作边界",
        "mode": "replace",
        "proposed_text": "## 工作边界\n\n- 一次性缺陷默认在代码和测试层闭环。",
        "verification": "后续同类缺陷不再产生新的永久规则。",
    }

    with pytest.raises(ValueError, match="two independent evidence"):
        create_candidate(tmp_path, evidence=["capture/session-a.md"], **common)

    candidate = create_candidate(
        tmp_path,
        evidence=["capture/session-a.md", "capture/session-b.md"],
        **common,
    )

    assert candidate.state == "pending"
    assert candidate.ground == "repeated"
    assert candidate.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert list_candidates(tmp_path)[0].id == candidate.id


def test_run_asks_for_at_most_three_candidates_and_never_for_freshness(
    tmp_path: Path,
) -> None:
    from forge.zone import certify, zone_init

    sections = tmp_path / "context build" / "sections"
    sections.mkdir(parents=True)
    (sections / "preference.md").write_text("# Preference\n", encoding="utf-8")
    (sections / "alpha.md").write_text("# Alpha\n\nold\n", encoding="utf-8")
    (tmp_path / "context build" / "zones.yaml").write_text(
        'rule_zone:\n  - "context build/sections/preference.md"\n', encoding="utf-8"
    )
    zone_init(tmp_path)
    certify(tmp_path, "context build/sections/alpha.md")
    (sections / "alpha.md").write_text("# Alpha\n\nnew\n", encoding="utf-8")

    for index in range(4):
        create_candidate(
            tmp_path,
            title=f"候选 {index}",
            ground="explicit",
            evidence=[f"capture/session-{index}.md"],
            problem=f"问题 {index}",
            proposal=f"建议 {index}",
            scope="明确范围",
            exclusions=["范围之外"],
            target=f"public knowledge base/topic/candidate-{index}.md",
            anchor="",
            mode="create",
            proposed_text=f"# Candidate {index}",
            verification="确认后续任务是否实际使用",
        )

    items = run.ask(tmp_path)

    assert len(items) == 3
    assert all(item.type == "candidate" for item in items)
    assert all("问题" in item.detail and "适用范围" in item.detail for item in items)
    assert run.status(tmp_path)["candidate_counts"] == {
        "pending": 4,
        "promoted": 0,
        "rejected": 0,
        "observing": 0,
    }


def _run_workspace(root: Path) -> Path:
    sections = root / "context build" / "sections"
    config = root / "context build" / "config"
    sections.mkdir(parents=True)
    config.mkdir(parents=True)
    (sections / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 原规则。\n", encoding="utf-8"
    )
    (sections / "alpha.md").write_text(
        "---\nname: alpha\ntype: project\n---\n\nAlpha。\n", encoding="utf-8"
    )
    (config / "agents-md.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - preference\n  - alpha\n---\n",
        encoding="utf-8",
    )
    (root / "context build" / "zones.yaml").write_text(
        'rule_zone:\n  - "context build/sections/preference.md"\n', encoding="utf-8"
    )
    from forge.zone import zone_init

    zone_init(root)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@example.com"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True)
    return root


def test_approving_candidate_promotes_it_through_the_existing_ledger(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    run.open_run(ws)
    candidate = create_candidate(
        ws,
        title="记录稳定的测试原则",
        ground="explicit",
        evidence=["capture/owner-request.md"],
        problem="测试原则目前没有正式资产。",
        proposal="建立一份经过确认的测试原则。",
        scope="Forge 的实现测试。",
        exclusions=["一次性实验"],
        target="public knowledge base/topic/forge-testing.md",
        anchor="",
        mode="create",
        proposed_text="# Forge testing\n\n测试 observable behavior。",
        verification="下一轮实现能引用该原则。",
    )

    outcome = run.decide(ws, candidate.id, "approve")

    assert outcome["state"] == "promoted"
    assert (ws / "public knowledge base" / "topic" / "forge-testing.md").is_file()
    stored = list_candidates(ws, include_decided=True)[0]
    assert stored.state == "promoted"
    assert stored.ledger_entry == outcome["entry"]


def test_reject_or_observe_closes_review_without_losing_evidence(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    run.open_run(ws)

    def candidate(title: str, evidence: str):
        return create_candidate(
            ws,
            title=title,
            ground="explicit",
            evidence=[evidence],
            problem=f"{title} 是否值得长期保留尚未确定。",
            proposal=f"把 {title} 写入知识资产。",
            scope="明确范围",
            exclusions=["一次性场景"],
            target=f"public knowledge base/topic/{title}.md",
            anchor="",
            mode="create",
            proposed_text=f"# {title}",
            verification="等待真实使用反馈。",
        )

    rejected = candidate("reject-me", "capture/reject.md")
    observing = candidate("observe-me", "capture/observe.md")

    assert run.decide(ws, rejected.id, "reject", "过于具体")["state"] == "rejected"
    observed = run.decide(ws, observing.id, "observe", "等待第二个独立事件")

    stored = {c.id: c for c in list_candidates(ws, include_decided=True)}
    assert stored[rejected.id].state == "rejected"
    assert stored[rejected.id].evidence == ["capture/reject.md"]
    assert stored[observing.id].state == "observing"
    observation = list_observations(ws)[0]
    assert observed["observation"] == observation.id
    assert observation.evidence == ["capture/observe.md"]


def test_run_next_stops_after_three_candidate_decisions(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    run.open_run(ws)
    candidates = [
        create_candidate(
            ws,
            title=f"candidate-{index}",
            ground="explicit",
            evidence=[f"capture/owner-{index}.md"],
            problem="需要判断是否形成长期资产。",
            proposal=f"记录候选 {index}。",
            scope="Forge 测试。",
            exclusions=["一次性实验"],
            target=f"public knowledge base/topic/candidate-{index}.md",
            anchor="",
            mode="create",
            proposed_text=f"# Candidate {index}",
            verification="后续真实任务验证。",
        )
        for index in range(4)
    ]

    for remaining in (3, 2, 1):
        contract = run.next_contract(ws)
        assert contract["action"] == "decide-candidate"
        assert contract["review_budget_remaining"] == remaining
        run.decide(ws, contract["ask_id"], "reject", "test budget")

    assert run.next_contract(ws)["action"] == "close"
    pending = [
        candidate
        for candidate in list_candidates(ws)
        if candidate.state == "pending"
    ]
    assert [candidate.id for candidate in pending] == [candidates[3].id]


def test_run_next_respects_zero_candidate_budget(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    run.open_run(ws)
    create_candidate(
        ws,
        title="not-now",
        ground="explicit",
        evidence=["capture/owner.md"],
        problem="候选存在但 owner 本轮没有 review 时间。",
        proposal="保留候选到以后。",
        scope="Forge 测试。",
        exclusions=["当前 Run"],
        target="public knowledge base/topic/not-now.md",
        anchor="",
        mode="create",
        proposed_text="# Not now",
        verification="后续 Run 再审。",
    )

    assert run.next_contract(ws, budget=0)["action"] == "close"


def test_approved_rule_candidate_updates_verified_runtime_without_prior_rule_drift(
    tmp_path: Path,
) -> None:
    from forge.gate.actions import build
    from forge.zone import gate_drifts

    ws = _run_workspace(tmp_path)
    build(ws)
    run.open_run(ws)
    candidate = create_candidate(
        ws,
        title="加入经过质检的长期规则",
        ground="explicit",
        evidence=["capture/owner-request.md"],
        problem="owner 明确提出了一项长期要求。",
        proposal="在规则区增加经过质检的要求。",
        scope="Forge 协作。",
        exclusions=["其他项目"],
        target="context build/sections/preference.md",
        anchor="- 原规则。",
        mode="replace",
        proposed_text="- 原规则。\n- 新的质检规则。",
        verification="runtime 中出现新规则且 gate 无 drift。",
    )

    assert gate_drifts(ws) == []
    outcome = run.decide(ws, candidate.id, "approve")

    assert outcome["state"] == "promoted"
    assert gate_drifts(ws) == []
    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "新的质检规则" in runtime.read_text(encoding="utf-8")


def test_run_cannot_close_until_every_new_input_has_an_explicit_disposition(
    tmp_path: Path,
) -> None:
    ws = _run_workspace(tmp_path)
    capture = ws / "capture" / "session.md"
    capture.parent.mkdir()
    capture.write_text("可能重复出现的问题。\n", encoding="utf-8")
    opened = run.open_run(ws)

    with pytest.raises(RuntimeError, match="unclassified input"):
        run.close_run(ws)

    observation = record_observation(
        ws,
        theme="可能重复出现的问题",
        evidence=["capture/session.md"],
    )
    disposition = run.record_disposition(
        ws,
        "capture/session.md",
        "observe",
        sink=observation.id,
        note="等待第二个独立事件",
    )
    report = run.close_run(ws)

    assert disposition["kind"] == "observe"
    assert report["dispositions"] == {"observe": 1}
    assert capture.is_file()
    assert opened.inputs[0]["path"] == "capture/session.md"


def test_cli_records_observation_candidate_and_input_disposition(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from forge.cli import main

    ws = _run_workspace(tmp_path)
    capture = ws / "capture" / "session.md"
    capture.parent.mkdir()
    capture.write_text("明确长期要求。\n", encoding="utf-8")
    proposed = ws / "candidate-body.md"
    proposed.write_text("# Reviewed asset\n", encoding="utf-8")
    cli = CliRunner()

    assert cli.invoke(main, ["run", "open", "--root", str(ws)]).exit_code == 0
    observed = cli.invoke(
        main,
        [
            "observation",
            "record",
            "--root",
            str(ws),
            "--theme",
            "长期要求",
            "--evidence",
            "capture/session.md",
        ],
    )
    assert observed.exit_code == 0 and "obs-" in observed.output

    created = cli.invoke(
        main,
        [
            "candidate",
            "create",
            "--root",
            str(ws),
            "--title",
            "Reviewed asset",
            "--ground",
            "explicit",
            "--evidence",
            "capture/session.md",
            "--problem",
            "长期要求尚未进入资产。",
            "--proposal",
            "建立正式资产。",
            "--scope",
            "Forge",
            "--exclusion",
            "其他项目",
            "--target",
            "public knowledge base/topic/reviewed.md",
            "--mode",
            "create",
            "--proposed-file",
            str(proposed),
            "--verification",
            "后续任务能够引用。",
        ],
    )
    assert created.exit_code == 0 and "cand-" in created.output
    candidate_id = created.output.strip().split()[0]

    disposed = cli.invoke(
        main,
        [
            "run",
            "disposition",
            "capture/session.md",
            "--as",
            "candidate",
            "--sink",
            candidate_id,
            "--root",
            str(ws),
        ],
    )
    assert disposed.exit_code == 0 and "candidate" in disposed.output


def test_promoted_asset_records_real_use_feedback_in_status_metrics(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    run.open_run(ws)
    candidate = create_candidate(
        ws,
        title="可验证资产",
        ground="explicit",
        evidence=["capture/request.md"],
        problem="需要验证资产是否真实产生作用。",
        proposal="记录使用后的有效、修正或退役信号。",
        scope="正式资产",
        exclusions=["尚未晋升的候选"],
        target="public knowledge base/topic/verified-use.md",
        anchor="",
        mode="create",
        proposed_text="# Verified use",
        verification="真实任务完成后记录反馈。",
    )
    run.decide(ws, candidate.id, "approve")

    feedback = record_asset_feedback(
        ws,
        candidate.id,
        outcome="effective",
        evidence=["system/run/real-task.md"],
        note="真实任务引用并改变了处理方式",
    )

    assert feedback["outcome"] == "effective"
    metrics = run.status(ws)["promotion_metrics"]
    assert metrics["decided"] == 1
    assert metrics["acceptance_rate"] == 1.0
    assert metrics["used_assets"] == 1
    assert metrics["feedback_counts"] == {"effective": 1}
    message = subprocess.run(
        ["git", "-C", str(ws), "log", "-1", "--format=%s"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert message.startswith("asset feedback:")


def test_open_run_automatically_closes_expired_observations(tmp_path: Path) -> None:
    ws = _run_workspace(tmp_path)
    old = datetime(2020, 1, 1, tzinfo=timezone.utc)
    observation = record_observation(
        ws,
        theme="长期没有再次出现的主题",
        evidence=["capture/old.md"],
        expires_days=1,
        now=old,
    )

    opened = run.open_run(ws)

    assert opened.expired_observations == [observation.id]
    stored = list_observations(ws, include_closed=True)[0]
    assert stored.state == "closed" and stored.closed_reason == "expired"


def test_portal_embeds_complete_read_only_candidate_card(tmp_path: Path) -> None:
    import json

    from forge.audit.portal import write_portal

    ws = _run_workspace(tmp_path)
    candidate = create_candidate(
        ws,
        title="只读候选卡",
        ground="explicit",
        evidence=["capture/request.md"],
        problem="Owner 需要看到候选解决的普遍问题。",
        proposal="Portal 展示完整候选卡。",
        scope="只读审计面",
        exclusions=["Portal 内直接写入"],
        target="public knowledge base/topic/card.md",
        anchor="",
        mode="create",
        proposed_text="# Card",
        verification="页面包含范围和验证方法。",
    )

    html_path, json_path = write_portal(ws, tmp_path / "portal")

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    item = next(i for i in payload["ask_items"] if i["id"] == candidate.id)
    assert item["type"] == "candidate"
    assert "适用范围:只读审计面" in item["detail"]
    html = html_path.read_text(encoding="utf-8")
    assert "只读候选卡" in html
    assert "一次只审一张候选卡" in html


def test_failed_rule_promotion_restores_rule_and_verified_snapshot(tmp_path: Path) -> None:
    from forge.zone import gate_drifts

    ws = _run_workspace(tmp_path)
    run.open_run(ws)
    preference = ws / "context build" / "sections" / "preference.md"
    original = preference.read_text(encoding="utf-8")
    candidate = create_candidate(
        ws,
        title="原子规则晋升",
        ground="explicit",
        evidence=["capture/request.md"],
        problem="规则写入失败时不能留下半套状态。",
        proposal="规则、snapshot、runtime 和 ledger 原子提交。",
        scope="规则区晋升",
        exclusions=["状态区"],
        target="context build/sections/preference.md",
        anchor="- 原规则。",
        mode="replace",
        proposed_text="- 原规则。\n- 不应残留的规则。",
        verification="提交失败后所有字节恢复。",
    )
    hook = ws / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    outcome = run.decide(ws, candidate.id, "approve")

    assert outcome["state"] == "failed"
    assert preference.read_text(encoding="utf-8") == original
    assert gate_drifts(ws) == []
    assert list_candidates(ws)[0].state == "pending"


def test_pending_candidate_pauses_observation_expiry_and_reject_closes_it(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    observation = record_observation(
        tmp_path,
        theme="跨事件主题",
        evidence=["capture/a.md", "capture/b.md"],
        expires_days=1,
        now=now,
    )
    candidate = create_candidate(
        tmp_path,
        title="跨事件候选",
        ground="repeated",
        evidence=observation.evidence,
        problem="两个独立事件显示了同一问题。",
        proposal="建立受限资产。",
        scope="明确范围",
        exclusions=["其他范围"],
        target="public knowledge base/topic/cross-event.md",
        anchor="",
        mode="create",
        proposed_text="# Cross event",
        verification="真实任务验证。",
        observation_id=observation.id,
        now=now,
    )

    assert expire_observations(tmp_path, now=now + timedelta(days=2)) == []
    from forge.promotion import transition_candidate

    transition_candidate(tmp_path, candidate.id, "rejected", note="抽象仍不成立", now=now)

    stored = list_observations(tmp_path, include_closed=True)[0]
    assert stored.state == "closed"
    assert stored.closed_reason == "candidate-rejected"


def test_pending_candidate_can_be_revised_without_creating_a_second_card(
    tmp_path: Path,
) -> None:
    candidate = create_candidate(
        tmp_path,
        title="需要缩限的候选",
        ground="explicit",
        evidence=["capture/request.md"],
        problem="初稿范围太宽。",
        proposal="建立一条受限规则。",
        scope="所有项目",
        exclusions=["暂无"],
        target="context build/sections/preference.md",
        anchor="## 工作边界",
        mode="replace",
        proposed_text="## 工作边界\n\n- 所有项目都必须执行。",
        verification="真实任务验证。",
    )

    revised = revise_candidate(
        tmp_path,
        candidate.id,
        scope="仅 Forge 的规则区变更",
        exclusions=["其他项目", "一次性缺陷"],
        proposed_text="## 工作边界\n\n- Forge 规则区变更必须经过候选质检。",
        note="按 owner 意见缩小范围",
    )

    assert revised.id == candidate.id
    assert revised.state == "pending"
    assert revised.scope == "仅 Forge 的规则区变更"
    assert revised.exclusions == ["其他项目", "一次性缺陷"]
    assert revised.revisions[0]["note"] == "按 owner 意见缩小范围"
    assert len(list_candidates(tmp_path)) == 1


def test_close_run_never_reports_success_when_its_scoped_commit_fails(
    tmp_path: Path,
) -> None:
    ws = _run_workspace(tmp_path)
    capture = ws / "capture" / "import" / "failure.md"
    capture.parent.mkdir(parents=True)
    capture.write_text("material run input\n", encoding="utf-8")
    opened = run.open_run(ws)
    run.record_disposition(
        ws, "capture/import/failure.md", "closed", note="test commit failure"
    )
    hook = ws / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    with pytest.raises(RuntimeError, match="failed to commit run close"):
        run.close_run(ws)

    assert run.status(ws)["open_run"] == opened.id
    record = (ws / "system" / "run" / f"{opened.id}.md").read_text(encoding="utf-8")
    assert "status: open" in record
