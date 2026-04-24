"""Anthropic SDK 判官：两个答案盲评 → 给出 winner + reason。

用法：

    from forge.eval import default_tasks, AnthropicJudge, judge_pair

    judge = AnthropicJudge(model="claude-opus-4-7")
    verdict = judge_pair(task, ans_a, ans_b, judge.judge)

或者传进 run_eval 的后处理：

    for pair in report.pairs:
        report.judge_verdicts.append(judge.judge(pair.task, pair.answer_a, pair.answer_b))
"""

from __future__ import annotations

import json
import os
import re
import secrets
from dataclasses import dataclass

from forge.eval.tasks import EvalTask
from forge.eval.judge import JudgeVerdict


JUDGE_INSTRUCTIONS = """\
你在评估两份候选回答，被问的是同一个题目。

**这是盲评**：标注为 Response 1 和 Response 2，但你不知道哪个来自哪个来源。
位置是随机分配的，位置偏见会影响结果，别只按位置选。

评分标准（按优先级从高到低）：
1. 是否准确、具体地回答了题目
2. 是否用了给出的 context 里的具体信息（相比只靠通用知识）
3. 是否遵守了题目里的格式要求

只输出一行严格 JSON，没有其他文字：

    {"winner": "1" | "2" | "tie", "reason": "一句话原因"}
"""


@dataclass
class AnthropicJudge:
    """用 Anthropic SDK 做盲评判官。

    参数：
        model            — 判官用的模型，默认 claude-opus-4-7
        max_tokens       — 回答上限，通常很小（几百够了）
        api_key          — 覆盖 env var
        counter_balance  — 如果 True，每次评两遍（交换 A/B 位置），返回投票结果
                           用来抵消位置偏见。代价是 2× tokens。
    """

    model: str = "claude-opus-4-7"
    max_tokens: int = 400
    api_key: str | None = None
    counter_balance: bool = False

    def __post_init__(self) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "AnthropicJudge 需要 anthropic 包：pip install anthropic"
            ) from e

    def _client(self):  # pragma: no cover
        import anthropic

        if self.api_key:
            return anthropic.Anthropic(api_key=self.api_key)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY 未设置")
        return anthropic.Anthropic()

    def _one_pass(self, task: EvalTask, answer_1: str, answer_2: str) -> JudgeVerdict:
        client = self._client()
        prompt = (
            f"题目：\n{task.prompt}\n\n"
            f"--- Response 1 ---\n{answer_1}\n\n"
            f"--- Response 2 ---\n{answer_2}\n"
        )
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=JUDGE_INSTRUCTIONS,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        data = _extract_json(text)
        winner = str(data.get("winner", "tie"))
        if winner not in ("1", "2", "tie"):
            winner = "tie"
        return JudgeVerdict(
            task_id=task.id,
            winner=winner,
            reason=str(data.get("reason", "(no reason)")),
        )

    def judge(self, task: EvalTask, answer_a: str, answer_b: str) -> JudgeVerdict:
        """评一对答案。A/B 是"语义来源"（比如 master vs forge），
        Response 1/2 是盲评里的位置——每次随机分配。
        """
        # 随机化位置
        flip = secrets.randbelow(2) == 1

        if not self.counter_balance:
            if flip:
                v = self._one_pass(task, answer_b, answer_a)
                winner = {"1": "B", "2": "A", "tie": "tie"}[v.winner]
            else:
                v = self._one_pass(task, answer_a, answer_b)
                winner = {"1": "A", "2": "B", "tie": "tie"}[v.winner]
            return JudgeVerdict(task_id=task.id, winner=winner, reason=v.reason)

        # counter_balance：两次，位置对调，投票
        v1 = self._one_pass(task, answer_a, answer_b)
        w1 = {"1": "A", "2": "B", "tie": "tie"}[v1.winner]
        v2 = self._one_pass(task, answer_b, answer_a)
        w2 = {"1": "B", "2": "A", "tie": "tie"}[v2.winner]

        if w1 == w2:
            final = w1
        elif "tie" in (w1, w2):
            final = w1 if w2 == "tie" else w2
        else:
            final = "tie"  # 两次结果冲突，记为位置偏见，按 tie

        return JudgeVerdict(
            task_id=task.id,
            winner=final,
            reason=f"counter-balanced: pass1={w1} ({v1.reason}); pass2={w2} ({v2.reason})",
        )


def _extract_json(text: str) -> dict:
    """从模型输出里抠出那行 JSON。容忍前后空白和偶尔的 markdown 代码块。"""
    text = text.strip()
    # 如果整段是 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 找第一个 { 到最后一个 }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return {"winner": "tie", "reason": f"(parse error; raw: {text[:80]!r})"}
