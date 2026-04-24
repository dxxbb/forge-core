"""Anthropic SDK runner: 把 CLAUDE.md 当 system prompt 传进去，真跑 agent 回答。

默认模型 claude-opus-4-7，走 adaptive thinking。使用者可以自己换模型和参数。

本模块有软依赖 `anthropic` 包。没装也能 import forge.eval，只是用到
AnthropicRunner 才会抛 ImportError。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from forge.eval.harness import Runner


@dataclass
class AnthropicRunner(Runner):
    """用 Anthropic SDK 真跑的 runner。

    参数：
        model         — 模型 ID，默认 claude-opus-4-7
        max_tokens    — 每次回答的上限
        api_key       — 覆盖环境变量（不传就读 ANTHROPIC_API_KEY）
        thinking      — 是否开 adaptive thinking；对行为评估默认关闭
                        （减少思考字数，看回答本身）
        effort        — 可选的 effort 等级（low/medium/high/max）

    用法：

        from forge.eval import AnthropicRunner, run_eval, default_tasks

        runner = AnthropicRunner(model="claude-opus-4-7", max_tokens=2000)
        report = run_eval(context_a, context_b, default_tasks(), runner,
                          version_a="master", version_b="forge")
    """

    model: str = "claude-opus-4-7"
    max_tokens: int = 2000
    api_key: str | None = None
    thinking: bool = False
    effort: str | None = None

    def __post_init__(self) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "AnthropicRunner 需要 anthropic 包：pip install anthropic"
            ) from e

    def _client(self):  # pragma: no cover - thin wrapper
        import anthropic

        if self.api_key:
            return anthropic.Anthropic(api_key=self.api_key)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "ANTHROPIC_API_KEY 未设置。设环境变量或在 AnthropicRunner(api_key=...) 里传。"
            )
        return anthropic.Anthropic()

    def run(self, context: str, prompt: str) -> str:
        """把 context 当 system prompt，prompt 当 user message，返回 text 回答。"""
        client = self._client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": context,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.thinking:
            kwargs["thinking"] = {"type": "adaptive"}
        if self.effort:
            kwargs["output_config"] = {"effort": self.effort}

        response = client.messages.create(**kwargs)
        parts: list[str] = []
        for block in response.content:
            if block.type == "text":
                parts.append(block.text)
        return "".join(parts).strip()
