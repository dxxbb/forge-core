"""Anthropic runner / judge 的接口契约测试。

不真调 API——只验证 class 能 import、__post_init__ 能在缺 key 时不爆、
和 run_eval / judge_pair 接口契合。

真跑 A/B 是 integration test，属于 `examples/dxyos-validation/validate.py`，
不在 CI 跑。
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from forge.eval import (
    Runner,
    CallableRunner,
    default_tasks,
    run_eval,
    JudgeVerdict,
)
from forge.eval.judge import judge_pair, sim_judge


def test_anthropic_runner_import_lazy() -> None:
    """如果没装 anthropic 包，import forge.eval 应该正常，用到时才爆。"""
    # forge.eval 里 AnthropicRunner 是通过 __getattr__ 按需 import 的
    from forge.eval import AnthropicRunner  # noqa: F401


def test_anthropic_runner_raises_without_api_key(monkeypatch) -> None:
    pytest.importorskip("anthropic")
    from forge.eval import AnthropicRunner

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = AnthropicRunner()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        r.run("system", "prompt")


def test_anthropic_judge_import_lazy() -> None:
    from forge.eval import AnthropicJudge  # noqa: F401


def test_anthropic_judge_raises_without_api_key(monkeypatch) -> None:
    pytest.importorskip("anthropic")
    from forge.eval import AnthropicJudge

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    j = AnthropicJudge()
    task = default_tasks()[0]
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        j.judge(task, "a", "b")


def test_anthropic_judge_json_extraction() -> None:
    """Judge 能从各种格式里抠出 JSON。"""
    pytest.importorskip("anthropic")
    from forge.eval.anthropic_judge import _extract_json

    # 纯 JSON
    assert _extract_json('{"winner": "1", "reason": "x"}') == {
        "winner": "1",
        "reason": "x",
    }
    # 带 markdown fence
    wrapped = '```json\n{"winner": "2", "reason": "y"}\n```'
    assert _extract_json(wrapped)["winner"] == "2"
    # 带前缀（模型有时啰嗦）
    assert _extract_json('Here you go:\n{"winner": "tie", "reason": "eh"}')["winner"] == "tie"
    # 完全是垃圾
    out = _extract_json("totally not json")
    assert out["winner"] == "tie"
    assert "parse error" in out["reason"]


def test_callable_runner_wraps_function() -> None:
    """CallableRunner 让你传一个函数不用写类。"""
    r = CallableRunner(lambda ctx, prompt: f"len(ctx)={len(ctx)} prompt={prompt[:10]}")
    out = r.run("hello world", "solve this for me")
    assert out.startswith("len(ctx)=11 ")


def test_run_eval_with_callable_runner() -> None:
    """把 CallableRunner 喂给 run_eval 跑一下。"""
    tasks = default_tasks()[:2]
    runner = CallableRunner(lambda ctx, prompt: f"[{ctx[:3]}] {prompt[:10]}")
    report = run_eval("ABC-context", "XYZ-context", tasks, runner)
    assert len(report.pairs) == 2
    assert report.pairs[0].answer_a.startswith("[ABC]")
    assert report.pairs[0].answer_b.startswith("[XYZ]")


def test_judge_pair_with_custom_judge() -> None:
    """judge_pair 接受任意 callable。"""
    task = default_tasks()[0]

    def always_a(t, a, b):
        return JudgeVerdict(task_id=t.id, winner="A", reason="I like A")

    v = judge_pair(task, "foo", "bar", always_a)
    assert v.winner == "A"


def test_sim_judge_returns_tie() -> None:
    task = default_tasks()[0]
    v = sim_judge(task, "anything", "anything else")
    assert v.winner == "tie"
