"""Soft budgets for compiled outputs + rule-zone budget early warning.

The rule zone always had a line budget; compiled runtime artifacts had no
size guard at all. These tests cover: budget parsing (zones.yaml global +
config frontmatter override), doctor/build warnings on over-budget compiled
output (warning, never failure), the token-estimate heuristic, and the
early-warning threshold (~87%) on the existing rule-zone budget.
"""

from __future__ import annotations

from pathlib import Path

from forge import gate
from forge.budget import estimate_tokens, output_budget_checks
from forge.compiler.config import Config
from forge.gate.doctor import run as doctor_run
from forge.zone import load_zones, rule_budget_warn_threshold, zone_init

import pytest


def _workspace(root: Path, zones_extra: str = "") -> Path:
    sections = root / "context build" / "sections"
    config = root / "context build" / "config"
    sections.mkdir(parents=True)
    config.mkdir(parents=True)
    (sections / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled context.\n", encoding="utf-8"
    )
    (sections / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n", encoding="utf-8"
    )
    (sections / "alpha.md").write_text(
        "---\nname: alpha\ntype: project\n---\n\nAlpha 项目状态:进行中。\n", encoding="utf-8"
    )
    (config / "agents-md.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - _preface\n  - preference\n  - alpha\n---\n",
        encoding="utf-8",
    )
    (root / "context build" / "zones.yaml").write_text(
        'rule_zone:\n  - "context build/sections/preference.md"\n' + zones_extra,
        encoding="utf-8",
    )
    return root


def _budget_warnings(report) -> list[str]:
    return [w for w in report.warnings if "soft budget" in w]


# ---------- parsing ----------

def test_zones_output_budget_parsing(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 300\n  tokens: 8000\n")
    zones = load_zones(ws)
    assert zones.output_budget_lines == 300
    assert zones.output_budget_tokens == 8000


def test_zones_output_budget_defaults_to_unconfigured(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    zones = load_zones(ws)
    assert zones.output_budget_lines is None
    assert zones.output_budget_tokens is None


def test_zones_output_budget_must_be_mapping(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget: 300\n")
    with pytest.raises(ValueError, match="output_budget"):
        load_zones(ws)


def test_config_output_budget_parsing(tmp_path: Path) -> None:
    p = tmp_path / "c.md"
    p.write_text(
        "---\nname: c\ntarget: agents-md\nsections: [alpha]\n"
        "output_budget:\n  lines: 250\n  tokens: null\n---\n",
        encoding="utf-8",
    )
    cfg = Config.from_file(p)
    assert cfg.output_budget == {"lines": 250, "tokens": None}


def test_config_output_budget_rejects_unknown_key(tmp_path: Path) -> None:
    p = tmp_path / "c.md"
    p.write_text(
        "---\nname: c\ntarget: agents-md\nsections: [alpha]\n"
        "output_budget:\n  bytes: 9000\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="output_budget"):
        Config.from_file(p)


def test_config_output_budget_rejects_non_int(tmp_path: Path) -> None:
    p = tmp_path / "c.md"
    p.write_text(
        "---\nname: c\ntarget: agents-md\nsections: [alpha]\n"
        "output_budget:\n  lines: many\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="output_budget.lines"):
        Config.from_file(p)


# ---------- token estimate heuristic ----------

def test_estimate_tokens_heuristic() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("a" * 100) == 25  # ASCII ≈ 4 chars/token
    assert estimate_tokens("中" * 100) == 75  # CJK ≈ 0.75 token/char
    assert estimate_tokens("中" * 4 + "ab") == round(4 * 0.75 + 2 * 0.25)


# ---------- doctor / build warnings on compiled outputs ----------

def test_doctor_warns_on_over_budget_compiled_output(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 2\n")
    gate.build(ws)

    report = doctor_run(ws)

    warns = _budget_warnings(report)
    assert len(warns) == 1
    assert "context build/runtime/agents-md/AGENTS.md" in warns[0]
    assert "lines > 2" in warns[0]
    # Soft budget: a warning, never a failure.
    assert report.ok


def test_doctor_warns_on_over_token_budget(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  tokens: 1\n")
    gate.build(ws)

    report = doctor_run(ws)

    warns = _budget_warnings(report)
    assert len(warns) == 1
    assert "est. tokens > 1" in warns[0]


def test_doctor_quiet_and_informative_within_budget(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 1000\n  tokens: 100000\n")
    gate.build(ws)

    report = doctor_run(ws)

    assert _budget_warnings(report) == []
    assert any(
        "compiled output" in i and "soft budget" in i for i in report.info
    )


def test_no_budget_configured_means_no_check(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    gate.build(ws)

    assert output_budget_checks(ws) == []
    report = doctor_run(ws)
    assert _budget_warnings(report) == []
    assert not any("compiled output" in i for i in report.info)


def test_unbuilt_output_is_skipped(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 1\n")
    # No gate.build: runtime/ does not exist yet.
    assert output_budget_checks(ws) == []


def test_config_override_beats_global(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 2\n")
    cfg = ws / "context build" / "config" / "agents-md.md"
    cfg.write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - _preface\n  - preference\n  - alpha\n"
        "output_budget:\n  lines: 1000\n---\n",
        encoding="utf-8",
    )
    gate.build(ws)

    assert _budget_warnings(doctor_run(ws)) == []


def test_config_zero_disables_inherited_dimension(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "output_budget:\n  lines: 2\n")
    cfg = ws / "context build" / "config" / "agents-md.md"
    cfg.write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - _preface\n  - preference\n  - alpha\n"
        "output_budget:\n  lines: 0\n---\n",
        encoding="utf-8",
    )
    gate.build(ws)

    assert output_budget_checks(ws) == []


def test_config_budget_works_without_zones_yaml(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    (ws / "context build" / "zones.yaml").unlink()
    cfg = ws / "context build" / "config" / "agents-md.md"
    cfg.write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n"
        "  - _preface\n  - preference\n  - alpha\n"
        "output_budget:\n  lines: 2\n---\n",
        encoding="utf-8",
    )
    gate.build(ws)

    warns = _budget_warnings(doctor_run(ws))
    assert len(warns) == 1
    assert "lines > 2" in warns[0]


def test_build_cli_prints_soft_budget_warning(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from forge.cli import main

    ws = _workspace(tmp_path, "output_budget:\n  lines: 2\n")
    result = CliRunner().invoke(main, ["build", "--root", str(ws)])

    assert result.exit_code == 0  # warn, not fail
    assert "wrote" in result.output
    assert "soft budget" in result.output


# ---------- rule-zone budget early warning ----------

def test_rule_budget_warn_threshold_default() -> None:
    # The agreed example: 130/150 should already warn.
    assert rule_budget_warn_threshold(150) == 130


def _set_rule_lines(ws: Path, n: int) -> None:
    body = "\n".join(f"- 规则 {i}。" for i in range(n))
    (ws / "context build" / "sections" / "preference.md").write_text(
        f"---\nname: preference\ntype: rule\n---\n\n{body}\n", encoding="utf-8"
    )


def test_rule_budget_early_warning_near_cap(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "budget_lines: 10\n")
    _set_rule_lines(ws, 9)  # 9/10 ≥ warn threshold int(10*0.87)=8, not over
    zone_init(ws)

    report = doctor_run(ws)

    assert any("nearly full" in w and "9/10" in w for w in report.warnings)
    assert not any("budget exceeded" in w for w in report.warnings)
    assert report.ok


def test_rule_budget_no_early_warning_below_threshold(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "budget_lines: 10\n")
    _set_rule_lines(ws, 7)  # 7 < 8 = warn threshold
    zone_init(ws)

    report = doctor_run(ws)

    assert not any("nearly full" in w for w in report.warnings)


def test_rule_budget_exceeded_replaces_early_warning(tmp_path: Path) -> None:
    ws = _workspace(tmp_path, "budget_lines: 10\n")
    _set_rule_lines(ws, 11)
    zone_init(ws)

    report = doctor_run(ws)

    assert any("budget exceeded" in w for w in report.warnings)
    assert not any("nearly full" in w for w in report.warnings)
