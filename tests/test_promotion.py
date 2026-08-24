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


def _observation_admission(label: str = "该模式") -> dict[str, str]:
    return {
        "signal_type": "observed-failure",
        "source_context": f"真实任务中实际出现了{label}。",
        "repeat_if": f"另一个独立事件再次实际出现{label}。",
        "route_gap": "现有资产未覆盖；一次事件不足以晋升，且没有更合适的代码、状态或关闭去向。",
    }


def test_observation_admission_requires_an_actual_unresolved_signal(
    tmp_path: Path,
) -> None:
    common = {
        "theme": "可行性回答先给实现条件",
        "event_ids": ["codex-thread:session-a"],
        "evidence": ["rollout/session-a.md"],
        "source_context": "用户实际纠正了只讲风险却没有回答怎么实现的回复。",
        "repeat_if": "另一个独立任务中，用户再次纠正回答缺少实现条件或主要障碍。",
        "route_gap": "现有长期偏好尚未覆盖；一次事件不足以晋升，且这不是代码缺陷或项目状态。",
    }

    with pytest.raises(ValueError, match="signal type"):
        record_observation(tmp_path, signal_type="successful-task", **common)

    for field in ("source_context", "repeat_if", "route_gap"):
        invalid = {**common, field: ""}
        with pytest.raises(ValueError, match=field.replace("_", " ")):
            record_observation(tmp_path, signal_type="owner-correction", **invalid)

    observation = record_observation(
        tmp_path,
        signal_type="owner-correction",
        **common,
    )

    assert observation.signal_type == "owner-correction"
    assert observation.source_contexts == [common["source_context"]]
    assert observation.repeat_if == common["repeat_if"]
    assert observation.route_gap == common["route_gap"]
    stored = list_observations(tmp_path)[0]
    assert stored.signal_type == "owner-correction"
    assert stored.source_contexts == [common["source_context"]]


def test_observation_merges_independent_evidence_and_expires_without_deleting_it(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)

    first = record_observation(
        tmp_path,
        theme="一次性 Bug 不应晋升为长期规则",
        **_observation_admission("把一次性 Bug 晋升为长期规则"),
        event_ids=["codex-thread:session-a"],
        evidence=["capture/session-a.md"],
        note="第一次出现",
        expires_days=30,
        now=now,
    )
    second = record_observation(
        tmp_path,
        theme="一次性 Bug 不应晋升为长期规则",
        **_observation_admission("把一次性 Bug 晋升为长期规则"),
        event_ids=["codex-thread:session-b", "codex-thread:session-a"],
        evidence=["capture/session-b.md", "capture/session-a.md"],
        note="独立场景再次出现",
        expires_days=30,
        now=now + timedelta(days=2),
    )

    assert second.id == first.id
    assert second.event_ids == ["codex-thread:session-a", "codex-thread:session-b"]
    assert second.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert second.independent_events == 2

    expired = expire_observations(tmp_path, now=now + timedelta(days=33))

    assert expired == [first.id]
    stored = list_observations(tmp_path, include_closed=True)[0]
    assert stored.state == "closed"
    assert stored.closed_reason == "expired"
    assert stored.event_ids == ["codex-thread:session-a", "codex-thread:session-b"]
    assert stored.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert stored.path is not None and stored.path.is_file()


def test_repeated_candidate_counts_events_not_evidence_pointers(tmp_path: Path) -> None:
    common = {
        "title": "把一次性 Bug 留在代码层解决",
        "ground": "repeated",
        "source_context": "两个独立任务都把一次性缺陷直接写成了永久行为规则。",
        "existing_coverage": "现有边界只禁止未核实事实，没有规定一次性缺陷的沉淀去向。",
        "asset_fit": "这是跨任务复现的协作模式，不是单次代码缺陷、易变项目状态或平台通用底线；工作偏好是改变未来处理方式的权威落点。",
        "promotion_rationale": "两个不同任务暴露了同一跨场景错误，规则只约束可由代码确定性修复的缺陷。",
        "expected_effect": "以后同类缺陷优先修代码和回归测试，不再制造永久提示词补丁。",
        "decision_question": "是否把这条跨任务处理原则写入长期协作规则？",
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

    with pytest.raises(ValueError, match="two independent events"):
        create_candidate(
            tmp_path,
            event_ids=["codex-thread:session-a"],
            evidence=["capture/session-a.md", "rollout/session-a.md"],
            **common,
        )

    candidate = create_candidate(
        tmp_path,
        event_ids=["codex-thread:session-a", "codex-thread:session-b"],
        evidence=["capture/session-a.md", "capture/session-b.md"],
        **common,
    )

    assert candidate.state == "pending"
    assert candidate.ground == "repeated"
    assert candidate.event_ids == ["codex-thread:session-a", "codex-thread:session-b"]
    assert candidate.evidence == ["capture/session-a.md", "capture/session-b.md"]
    assert list_candidates(tmp_path)[0].id == candidate.id

    without_fit = {**common, "asset_fit": ""}
    with pytest.raises(ValueError, match="asset_fit"):
        create_candidate(
            tmp_path,
            event_ids=["codex-thread:session-c", "codex-thread:session-d"],
            evidence=["capture/session-c.md", "capture/session-d.md"],
            **without_fit,
        )


def test_owner_directed_candidate_requires_a_long_term_owner_quote(tmp_path: Path) -> None:
    common = {
        "title": "医疗回答采用分层结构",
        "ground": "owner-directed",
        "event_ids": ["codex-thread:medical-a"],
        "evidence": ["rollout/medical-a.md"],
        "source_context": "用户在一次无痰调研中要求先判断是否需要排痰，再给教程。",
        "existing_coverage": "现有规则要求核实外部事实，但没有规定医疗回答结构。",
        "asset_fit": "Owner 明确要求把回答结构作为长期偏好；它不是本次病情事实或一次性教程。",
        "promotion_rationale": "只有 owner 明确要求未来长期采用该结构时，才足以从一次事件晋升。",
        "expected_effect": "以后所有医疗调研默认采用分层结构。",
        "decision_question": "是否让未来所有医疗调研默认采用这一结构？",
        "problem": "医疗回答结构尚未形成长期资产。",
        "proposal": "使用分层医疗回答结构。",
        "scope": "医疗资料调研。",
        "exclusions": ["个人诊断"],
        "target": "context build/sections/preference.md",
        "anchor": "",
        "mode": "append",
        "proposed_text": "- 医疗问题采用分层结构。",
        "verification": "运行时规则出现该结构。",
    }

    with pytest.raises(ValueError, match="exact long-term owner request"):
        create_candidate(tmp_path, owner_request="", **common)

    candidate = create_candidate(
        tmp_path,
        owner_request="以后所有医疗问题都按这个方式回答。",
        **common,
    )

    assert candidate.ground == "owner-directed"
    assert candidate.owner_request == "以后所有医疗问题都按这个方式回答。"


def test_high_risk_signal_does_not_bypass_candidate_promotion_ground(
    tmp_path: Path,
) -> None:
    common = {
        "title": "禁止未批准的生产删除",
        "ground": "high-risk",
        "event_ids": ["incident:production-delete-a"],
        "evidence": ["system/incidents/production-delete-a.md"],
        "source_context": "一次生产删除请求缺少 owner 批准。",
        "existing_coverage": "现有规则要求谨慎，但没有可验证的批准门禁。",
        "promotion_rationale": "这是可在执行前确定性检查的高风险不变量。",
        "expected_effect": "没有批准记录时，生产删除会被阻止。",
        "decision_question": "是否把生产删除批准门禁设为长期不变量？",
        "problem": "生产删除缺少可验证门禁。",
        "proposal": "执行生产删除前校验 owner 批准记录。",
        "scope": "生产环境删除。",
        "exclusions": ["本地可恢复临时文件"],
        "target": "context build/sections/preference.md",
        "anchor": "",
        "mode": "append",
        "proposed_text": "- 生产删除必须有 owner 批准记录。",
        "verification": "缺少批准记录的删除命令被门禁拒绝。",
    }

    with pytest.raises(
        ValueError,
        match=r"ground must be repeated\|owner-directed",
    ):
        create_candidate(
            tmp_path,
            risk_invariant="生产删除前必须存在匹配目标和范围的 owner 批准记录。",
            risk_failure="无批准、批准目标不匹配或批准已过期时拒绝执行。",
            **common,
        )


def test_review_card_explains_why_now_gap_ground_effect_question_and_patch(
    tmp_path: Path,
) -> None:
    run.open_run(tmp_path)
    candidate = create_candidate(
        tmp_path,
        title="跨任务缺陷在代码层闭环",
        ground="repeated",
        event_ids=["codex-thread:a", "codex-thread:b"],
        evidence=["rollout/a.md", "rollout/b.md"],
        source_context="任务 A 和任务 B 都把一次性缺陷写成了永久规则。",
        existing_coverage="现有规则只要求事实核验，未规定一次性缺陷的去向。",
        asset_fit="这是跨任务协作规则，工作偏好是权威落点；代码修复、状态记录和平台通用底线都不能表达这项 owner 行为选择。",
        promotion_rationale="两个独立任务暴露同一模式，且范围限定为可确定性修复的缺陷。",
        expected_effect="未来同类问题先修代码和测试，不再增加提示词补丁。",
        decision_question="是否把这项跨任务处理原则写入长期规则？",
        problem="一次性缺陷被错误沉淀成长期规则。",
        proposal="一次性缺陷默认在代码和回归测试层闭环。",
        scope="可确定性复现和修复的实现缺陷。",
        exclusions=["owner 明确要求长期约束的行为"],
        target="context build/sections/preference.md",
        anchor="## 工作边界",
        mode="replace",
        proposed_text="## 工作边界\n\n- 一次性缺陷在代码和测试层闭环。",
        verification="同类回归不再生成新的长期规则。",
    )

    [item] = run.ask(tmp_path)

    assert item.id == candidate.id
    for label in (
        "为什么现在提出",
        "现有资产对照",
        "为什么值得成为长期资产",
        "晋升为什么成立",
        "写入后的影响",
        "请你决定",
        "准确写入内容",
    ):
        assert label in item.detail
    assert "任务 A 和任务 B" in item.detail
    assert "一次性缺陷在代码和测试层闭环" in item.detail

    contract = run.next_contract(tmp_path)
    assert contract["action"] == "decide-candidate"
    assert contract["constraints"] == [
        "present the complete card in simple language, including why now, actual source events, existing coverage, why this belongs in an owner-governed durable asset, promotion ground, future effect, exact patch, and decision question",
        "do not collapse the card into only the proposed rule",
        "do not decide for the owner",
    ]


def _owner_directed_review(event: str) -> dict[str, object]:
    return {
        "ground": "owner-directed",
        "event_ids": [f"owner-request:{event}"],
        "source_context": "Owner 在一次任务中明确要求把该行为作为长期规则。",
        "existing_coverage": "已检查目标资产；当前没有覆盖这项长期要求。",
        "asset_fit": "这是 owner 明确要求的长期行为选择，目标资产是它的权威落点；它不属于一次性实现修复、易变状态或平台通用底线。",
        "promotion_rationale": "一次事件能够晋升，是因为 owner 明确要求未来长期遵守。",
        "expected_effect": "批准后，未来匹配范围的任务都会受这项规则约束。",
        "decision_question": "是否把这项 owner 明确要求写入长期资产？",
        "owner_request": "以后匹配范围的任务都按这项要求执行。",
    }


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
            **_owner_directed_review(f"candidate-{index}"),
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
        **_owner_directed_review("stable-testing-principle"),
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
            **_owner_directed_review(title),
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
            **_owner_directed_review(f"budget-{index}"),
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
        **_owner_directed_review("not-now"),
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
        **_owner_directed_review("approved-rule"),
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
        **_observation_admission("可能重复出现的问题"),
        event_ids=["capture-event:session"],
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
            "--signal-type",
            "owner-correction",
            "--source-context",
            "Owner 实际纠正了当前行为。",
            "--repeat-if",
            "另一个独立任务中再次发生相同纠正。",
            "--route-gap",
            "现有资产未覆盖，一次事件不足以晋升。",
            "--event-id",
            "owner-request:cli-test",
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
            "owner-directed",
            "--event-id",
            "owner-request:cli-test",
            "--evidence",
            "capture/session.md",
            "--source-context",
            "Owner 明确要求长期建立该资产。",
            "--existing-coverage",
            "现有资产没有覆盖。",
            "--asset-fit",
            "这是 owner 明确要求的长期资产，目标知识文件是权威落点。",
            "--promotion-rationale",
            "Owner 明确要求未来长期遵守。",
            "--expected-effect",
            "未来任务能够引用该资产。",
            "--decision-question",
            "是否写入该长期资产？",
            "--owner-request",
            "以后都按该资产执行。",
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
        **_owner_directed_review("verified-use"),
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
        **_observation_admission("长期没有再次出现的主题"),
        event_ids=["capture-event:old"],
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
        **_owner_directed_review("portal-card"),
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
        **_owner_directed_review("atomic-rule"),
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
        **_observation_admission("跨事件主题"),
        event_ids=["codex-thread:a", "codex-thread:b"],
        evidence=["capture/a.md", "capture/b.md"],
        expires_days=1,
        now=now,
    )
    common = {
        "title": "跨事件候选",
        "ground": "repeated",
        "evidence": observation.evidence,
        "source_context": "两个独立事件都显示了同一问题。",
        "existing_coverage": "现有资产没有覆盖该跨事件问题。",
        "asset_fit": "这是两个事件共同支持的长期资产，不属于单次修复、易变状态或平台通用底线。",
        "promotion_rationale": "两个独立事件支持相同的受限抽象。",
        "expected_effect": "未来匹配范围的事件应用该资产。",
        "decision_question": "是否把该跨事件模式写入长期资产？",
        "problem": "两个独立事件显示了同一问题。",
        "proposal": "建立受限资产。",
        "scope": "明确范围",
        "exclusions": ["其他范围"],
        "target": "public knowledge base/topic/cross-event.md",
        "anchor": "",
        "mode": "create",
        "proposed_text": "# Cross event",
        "verification": "真实任务验证。",
        "observation_id": observation.id,
        "now": now,
    }

    with pytest.raises(ValueError, match="event ids must be present on its observation"):
        create_candidate(
            tmp_path,
            event_ids=["codex-thread:a", "codex-thread:not-observed"],
            **common,
        )

    candidate = create_candidate(
        tmp_path,
        event_ids=observation.event_ids,
        **common,
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
        **_owner_directed_review("revise-scope"),
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

    with pytest.raises(ValueError, match="exact long-term owner request"):
        revise_candidate(tmp_path, candidate.id, owner_request="")


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
