"""Judge: compare two answers for the same task, decide which is better.

Judgement is itself done by an LLM. For v0.1 we define the interface and a
deterministic sim-judge. Production judges are plugged in by caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from forge.eval.tasks import EvalTask


@dataclass
class JudgeVerdict:
    task_id: str
    winner: str  # "A" | "B" | "tie"
    reason: str


def judge_pair(
    task: EvalTask,
    answer_a: str,
    answer_b: str,
    judge_fn: Callable[[EvalTask, str, str], JudgeVerdict],
) -> JudgeVerdict:
    """Run a judge over an answer pair. judge_fn is user-supplied."""
    return judge_fn(task, answer_a, answer_b)


def sim_judge(task: EvalTask, answer_a: str, answer_b: str) -> JudgeVerdict:
    """Deterministic sim judge for tests: always calls it a tie."""
    return JudgeVerdict(
        task_id=task.id,
        winner="tie",
        reason="sim-judge: always returns tie",
    )
