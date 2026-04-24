"""Eval harness: run task battery against two compiled-context versions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

from forge.eval.tasks import EvalTask


@dataclass
class AnswerPair:
    task: EvalTask
    answer_a: str
    answer_b: str


@dataclass
class EvalReport:
    version_a: str
    version_b: str
    pairs: list[AnswerPair] = field(default_factory=list)
    judge_verdicts: list["JudgeVerdict"] = field(default_factory=list)  # type: ignore[name-defined]

    def summary(self) -> dict:
        if not self.judge_verdicts:
            return {"tasks": len(self.pairs), "judged": 0}
        a_wins = sum(1 for v in self.judge_verdicts if v.winner == "A")
        b_wins = sum(1 for v in self.judge_verdicts if v.winner == "B")
        ties = sum(1 for v in self.judge_verdicts if v.winner == "tie")
        return {
            "tasks": len(self.pairs),
            "judged": len(self.judge_verdicts),
            "a_wins": a_wins,
            "b_wins": b_wins,
            "ties": ties,
        }


class Runner(ABC):
    @abstractmethod
    def run(self, context: str, prompt: str) -> str:
        """Given a CLAUDE.md context and a user prompt, return the agent's reply."""


class SimulationRunner(Runner):
    """Deterministic stub for tests. Returns a fake response including a hash of inputs."""

    def run(self, context: str, prompt: str) -> str:
        h = hex(abs(hash((context[:200], prompt))) % (10**8))
        return f"[sim answer for prompt head={prompt[:30]!r} ctx_hash={h}]"


class CallableRunner(Runner):
    """Wrap a user-provided callable (context, prompt) -> str."""

    def __init__(self, fn: Callable[[str, str], str]):
        self.fn = fn

    def run(self, context: str, prompt: str) -> str:
        return self.fn(context, prompt)


def run_eval(
    context_a: str,
    context_b: str,
    tasks: list[EvalTask],
    runner: Runner,
    version_a: str = "A",
    version_b: str = "B",
) -> EvalReport:
    """Run every task against both contexts and collect answer pairs."""
    report = EvalReport(version_a=version_a, version_b=version_b)
    for task in tasks:
        ans_a = runner.run(context_a, task.prompt)
        ans_b = runner.run(context_b, task.prompt)
        report.pairs.append(AnswerPair(task=task, answer_a=ans_a, answer_b=ans_b))
    return report
