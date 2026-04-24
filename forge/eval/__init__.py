"""forge eval: behavioral A/B comparison of two compiled context versions.

Unlike `forge bench`, which compares bytes and structure, `forge eval` runs
real tasks against each version of a compiled `CLAUDE.md` / `AGENTS.md` and
compares the agent's answers.

v0.1 ships the harness API and task definitions. The actual model calls
happen via a pluggable runner:

- `SimulationRunner`: returns stub responses (for tests)
- `AnthropicRunner`: calls the Anthropic SDK (requires API key)
- `ExternalRunner`: user supplies their own callable

The point of v0.1 is to fix the API + report format so LLM eval can plug in
cleanly. v0.3 will ship a standard task library + baseline runners.
"""

from forge.eval.tasks import EvalTask, default_tasks
from forge.eval.harness import (
    Runner,
    SimulationRunner,
    CallableRunner,
    run_eval,
    AnswerPair,
    EvalReport,
)
from forge.eval.judge import JudgeVerdict, judge_pair, sim_judge

__all__ = [
    "EvalTask",
    "default_tasks",
    "Runner",
    "SimulationRunner",
    "CallableRunner",
    "run_eval",
    "AnswerPair",
    "EvalReport",
    "JudgeVerdict",
    "judge_pair",
    "sim_judge",
]


def __getattr__(name: str):
    """按需 import，避免没装 anthropic 的用户 import forge.eval 时炸。"""
    if name == "AnthropicRunner":
        from forge.eval.anthropic_runner import AnthropicRunner

        return AnthropicRunner
    if name == "AnthropicJudge":
        from forge.eval.anthropic_judge import AnthropicJudge

        return AnthropicJudge
    raise AttributeError(f"module 'forge.eval' has no attribute {name!r}")
