"""Eval tasks: realistic questions whose quality-of-answer depends on CLAUDE.md.

Each task names the sections it should exercise, so the report can highlight
which parts of the compiled context materially affected agent behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvalTask:
    id: str
    prompt: str
    exercises: list[str] = field(default_factory=list)
    description: str = ""


def default_tasks() -> list[EvalTask]:
    """The default 6-task battery — identity / workspace / preference / skill / boundaries."""
    return [
        EvalTask(
            id="identity-summary",
            prompt=(
                "请用 3 句中文总结你对用户的理解——"
                "包括他是谁、在做什么、当前的核心挑战。"
                "只输出 3 句话，不要前缀、不要编号、不要额外解释。"
            ),
            exercises=["about user"],
            description="Does the agent capture the user's identity summary?",
        ),
        EvalTask(
            id="workspace-awareness",
            prompt=(
                "列出用户当前在做的 3 个主要 project 或 topic。"
                "每个只写 1 行：`<name> — <一句话说明在做什么>`。"
                "只列 3 个，按重要性排序。"
            ),
            exercises=["workspace"],
            description="Does the agent know the user's active projects/topics?",
        ),
        EvalTask(
            id="language-preference",
            prompt=(
                "我问你一个关于 Python 的技术问题，你应该用中文还是英文回答？"
                "只用一句话回答，给出判断 + 依据。"
            ),
            exercises=["preference"],
            description="Does the agent follow the user's language-choice preference?",
        ),
        EvalTask(
            id="grounding-rule",
            prompt=(
                "用户问：'Claude Opus 4.7 是什么时候发布的？'"
                "在你回答这个问题之前，你应该做什么？"
                "只用 2 句话回答——第一句：你会不会直接凭记忆答；第二句：为什么。"
            ),
            exercises=["preference"],
            description="Does the agent apply the 'ground external facts in live sources' rule?",
        ),
        EvalTask(
            id="skill-routing",
            prompt=(
                "用户说：'monitor inbox'。"
                "作为一个遵守 operator skill 规则的 agent，你第一步应该做什么？"
                "只用 2 句话。"
            ),
            exercises=["skill"],
            description="Does the agent know to load the os-operator skill on this trigger?",
        ),
        EvalTask(
            id="ikigai-direction",
            prompt=(
                "用户说：'我最近还是没想清楚创业方向'。"
                "基于你对他的了解，给出 1 条最有针对性的下一步建议。"
                "不超过 3 句话。避免泛泛空话。"
            ),
            exercises=["about user", "workspace"],
            description="Does the agent tie advice to the user's actual 2026 goals and constraints?",
        ),
    ]
