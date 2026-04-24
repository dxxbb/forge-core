"""Target adapters: render a list of sections into a specific runtime format."""

from __future__ import annotations

from forge.targets.base import TargetAdapter
from forge.targets.claude_code import ClaudeCodeAdapter
from forge.targets.agents_md import AgentsMdAdapter

_REGISTRY: dict[str, TargetAdapter] = {
    "claude-code": ClaudeCodeAdapter(),
    "agents-md": AgentsMdAdapter(),
}


def get_adapter(name: str) -> TargetAdapter:
    if name not in _REGISTRY:
        raise KeyError(
            f"unknown target adapter `{name}`. Available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[name]


def register_adapter(adapter: TargetAdapter) -> None:
    """Register a custom adapter at runtime (for extension)."""
    _REGISTRY[adapter.name] = adapter


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


__all__ = ["TargetAdapter", "get_adapter", "register_adapter", "available_adapters"]
