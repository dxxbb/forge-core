from forge.eval import (
    default_tasks,
    run_eval,
    SimulationRunner,
    AnswerPair,
)
from forge.eval.judge import sim_judge, judge_pair


def test_default_tasks_nonempty() -> None:
    tasks = default_tasks()
    assert len(tasks) >= 4
    for t in tasks:
        assert t.id
        assert t.prompt
        assert isinstance(t.exercises, list)


def test_run_eval_with_simulation_runner() -> None:
    tasks = default_tasks()[:2]
    report = run_eval(
        context_a="context A content",
        context_b="context B content",
        tasks=tasks,
        runner=SimulationRunner(),
        version_a="dxyos-current",
        version_b="forge-produced",
    )
    assert report.version_a == "dxyos-current"
    assert report.version_b == "forge-produced"
    assert len(report.pairs) == 2
    for pair in report.pairs:
        assert isinstance(pair, AnswerPair)
        # Simulation runner's answers differ because contexts differ
        assert pair.answer_a != pair.answer_b


def test_judge_sim() -> None:
    task = default_tasks()[0]
    verdict = judge_pair(task, "answer A", "answer B", sim_judge)
    assert verdict.winner == "tie"
    assert verdict.task_id == task.id


def test_report_summary_empty() -> None:
    report = run_eval("", "", [], SimulationRunner())
    assert report.summary()["tasks"] == 0
