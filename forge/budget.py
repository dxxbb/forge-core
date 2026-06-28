"""Soft size budgets for compiled runtime outputs.

The rule zone has a line budget over its section sources (forge/zone.py).
Compiled runtime artifacts (CLAUDE.md / AGENTS.md / ...) had no guard at
all — nothing noticed when an output slowly bloated past what an agent
should carry as permanent context. This module adds an optional *soft*
budget: `forge doctor` and `forge build` WARN when a compiled output
exceeds it; nothing ever fails on it.

Configuration — every key optional, resolved per-key (config overrides
zones.yaml; ``0`` / ``null`` in a config explicitly disables a dimension):

    # context build/zones.yaml — workspace-wide default
    output_budget:
      lines: 300
      tokens: 8000

    # context build/config/<name>.md frontmatter — per-output override
    output_budget:
      lines: 250

Token counts are a heuristic estimate (CJK chars × 0.75 + everything else
× 0.25) — good enough to notice bloat, not a tokenizer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Character ranges that tokenize at roughly 3/4 token per character.
# Everything else (mostly ASCII markdown) averages ~4 characters per token.
_CJK_RANGES = (
    (0x3000, 0x30FF),  # CJK punctuation, hiragana, katakana
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xAC00, 0xD7AF),  # hangul syllables
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFF00, 0xFFEF),  # fullwidth forms
)

CJK_TOKENS_PER_CHAR = 0.75
OTHER_TOKENS_PER_CHAR = 0.25


def estimate_tokens(text: str) -> int:
    """Heuristic token estimate: CJK chars × 0.75 + everything else × 0.25."""
    cjk = sum(1 for ch in text if any(lo <= ord(ch) <= hi for lo, hi in _CJK_RANGES))
    other = len(text) - cjk
    return round(cjk * CJK_TOKENS_PER_CHAR + other * OTHER_TOKENS_PER_CHAR)


@dataclass
class OutputBudgetCheck:
    """Measured size of one compiled output vs its effective soft budget."""

    config_name: str
    relpath: str  # compiled output, workspace-relative
    lines: int
    est_tokens: int
    budget_lines: int | None
    budget_tokens: int | None

    @property
    def over_lines(self) -> bool:
        return self.budget_lines is not None and self.lines > self.budget_lines

    @property
    def over_tokens(self) -> bool:
        return self.budget_tokens is not None and self.est_tokens > self.budget_tokens

    @property
    def over(self) -> bool:
        return self.over_lines or self.over_tokens

    def warning(self) -> str:
        parts = []
        if self.over_lines:
            parts.append(f"{self.lines} lines > {self.budget_lines}")
        if self.over_tokens:
            parts.append(f"~{self.est_tokens} est. tokens > {self.budget_tokens}")
        return (
            f"compiled output `{self.relpath}` over soft budget: {', '.join(parts)} "
            f"(config `{self.config_name}`) — agents carry this whole file every "
            f"session; consider compressing"
        )

    def summary(self) -> str:
        budget = []
        if self.budget_lines is not None:
            budget.append(f"{self.budget_lines} lines")
        if self.budget_tokens is not None:
            budget.append(f"~{self.budget_tokens} tokens")
        return (
            f"compiled output `{self.relpath}`: {self.lines} lines, "
            f"~{self.est_tokens} est. tokens (soft budget {' / '.join(budget)})"
        )


def output_budget_checks(root: Path) -> list[OutputBudgetCheck]:
    """Measure every compiled output that has an effective soft budget.

    Outputs not yet built are skipped — there is nothing to measure, and the
    budget is about what agents actually read, not about the recipe.
    """
    from forge.compiler.loader import load_all_configs
    from forge.layout import detect
    from forge.targets import get_adapter
    from forge.zone import load_zones

    root = Path(root).resolve()
    zones = load_zones(root)
    layout = detect(root)
    checks: list[OutputBudgetCheck] = []
    for cname, cfg in load_all_configs(root).items():
        budget_lines = _effective(cfg.output_budget, "lines", zones.output_budget_lines)
        budget_tokens = _effective(cfg.output_budget, "tokens", zones.output_budget_tokens)
        if budget_lines is None and budget_tokens is None:
            continue
        try:
            adapter = get_adapter(cfg.target)
        except KeyError:
            continue  # unregistered adapter is already a doctor warning
        filename = adapter.filename(cfg)
        if layout.runtime_nested_by_target:
            path = layout.runtime_dir / adapter.name / filename
        else:
            path = layout.runtime_dir / filename
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        lines = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
        checks.append(
            OutputBudgetCheck(
                config_name=cname,
                relpath=path.relative_to(root).as_posix(),
                lines=lines,
                est_tokens=estimate_tokens(text),
                budget_lines=budget_lines,
                budget_tokens=budget_tokens,
            )
        )
    return checks


def _effective(override: dict, key: str, default: int | None) -> int | None:
    """Per-key resolution: config value wins; 0/null there disables the check."""
    if key in override:
        value = override[key]
        return int(value) if value else None
    return default
