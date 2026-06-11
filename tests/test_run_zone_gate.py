"""Zones + compile gate: the structural enforcement point of the run design.

Acceptance mapping: AC-ZONE-* and AC-GATE-* in docs/run-acceptance-spec.md.
"""

from __future__ import annotations

from pathlib import Path

from forge import gate
from forge.zone import gate_drifts, load_zones, zone_init


def _workspace(root: Path) -> Path:
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
        'rule_zone:\n  - "context build/sections/preference.md"\n', encoding="utf-8"
    )
    return root


def test_zones_config_declares_rule_zone_and_everything_else_is_state(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    zones = load_zones(ws)

    assert zones.exists
    assert zones.zone_for("context build/sections/preference.md") == "rule"
    assert zones.zone_for("context build/sections/alpha.md") == "state"
    # The zones declaration itself is rule-zone: changing the fence is a
    # behavioral change (AC-ZONE-2).
    assert zones.zone_for("context build/zones.yaml") == "rule"


def test_zone_init_certifies_current_rule_zone_as_verified_baseline(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)

    baselined = zone_init(ws)

    assert "context build/sections/preference.md" in baselined
    assert "context build/zones.yaml" in baselined
    snapshot = ws / "system" / "verified" / "context build" / "sections" / "preference.md"
    assert snapshot.read_text(encoding="utf-8") == (
        ws / "context build" / "sections" / "preference.md"
    ).read_text(encoding="utf-8")
    # Freshly initialized baseline has no drift (AC-ZONE-4).
    assert gate_drifts(ws) == []


def test_rule_zone_drift_is_detected_against_verified_snapshot(tmp_path: Path) -> None:
    ws = _workspace(tmp_path)
    zone_init(ws)
    pref = ws / "context build" / "sections" / "preference.md"
    pref.write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 偷偷加的新规则。\n",
        encoding="utf-8",
    )

    drifts = gate_drifts(ws)

    assert len(drifts) == 1
    d = drifts[0]
    assert d.relpath == "context build/sections/preference.md"
    assert "偷偷加的新规则" in d.current_text
    assert "偷偷加的新规则" not in d.verified_text


def test_rule_zone_drift_compiles_from_verified_snapshot(tmp_path: Path) -> None:
    """AC-GATE-1: agents keep reading the owner-approved rules, structurally."""
    ws = _workspace(tmp_path)
    zone_init(ws)
    gate.build(ws)
    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "沟通直接高效" in runtime.read_text(encoding="utf-8")

    (ws / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 偷偷加的新规则。\n",
        encoding="utf-8",
    )
    gate.build(ws)

    compiled = runtime.read_text(encoding="utf-8")
    assert "沟通直接高效" in compiled
    assert "偷偷加的新规则" not in compiled


def test_state_zone_changes_compile_directly(tmp_path: Path) -> None:
    """AC-GATE-4: informational content flows without the gate."""
    ws = _workspace(tmp_path)
    zone_init(ws)
    (ws / "context build" / "sections" / "alpha.md").write_text(
        "---\nname: alpha\ntype: project\n---\n\nAlpha 项目状态:已上线。\n", encoding="utf-8"
    )

    gate.build(ws)

    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "已上线" in runtime.read_text(encoding="utf-8")


def test_gate_inactive_without_baseline_compiles_current_content(tmp_path: Path) -> None:
    """AC-ZONE-4: no baseline -> gate must not silently pretend protection."""
    ws = _workspace(tmp_path)
    (ws / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 未初始化前的内容直接编译。\n",
        encoding="utf-8",
    )

    gate.build(ws)

    runtime = ws / "context build" / "runtime" / "agents-md" / "AGENTS.md"
    assert "未初始化前的内容直接编译" in runtime.read_text(encoding="utf-8")


def test_doctor_reports_gate_state_and_rule_budget(tmp_path: Path) -> None:
    """AC-ZONE-3 / AC-ZONE-4: doctor surfaces gate health instead of silence."""
    from forge.gate.doctor import run as doctor_run

    ws = _workspace(tmp_path)
    # Uninitialized gate is a warning, not silent fake protection.
    report = doctor_run(ws)
    assert any("zone" in w and "init" in w for w in report.warnings)

    zone_init(ws)
    report = doctor_run(ws)
    assert not any("zone" in w and "init" in w for w in report.warnings)
    assert any("rule zone" in i for i in report.info)

    # Drift shows up as a warning with the file named.
    (ws / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 偷偷加的新规则。\n",
        encoding="utf-8",
    )
    report = doctor_run(ws)
    assert any("preference.md" in w and "drift" in w for w in report.warnings)

    # Budget overrun warns (AC-ZONE-3).
    (ws / "context build" / "zones.yaml").write_text(
        'rule_zone:\n  - "context build/sections/preference.md"\nbudget_lines: 1\n',
        encoding="utf-8",
    )
    report = doctor_run(ws)
    assert any("budget" in w for w in report.warnings)


def test_portal_payload_carries_zone_cert_and_ask_items(tmp_path: Path) -> None:
    """AC-PORTAL-1/2: portal shows zone, freshness, and read-only ask items."""
    import json
    import re as _re

    from forge.audit.portal import write_portal
    from forge.zone import certify

    ws = _workspace(tmp_path)
    zone_init(ws)
    # Make preference a declared upstream so it appears as a source node.
    (ws / "context build" / "sections" / "alpha.md").write_text(
        "---\nname: alpha\ntype: project\nupstream:\n"
        "  - context build/sections/preference.md\n---\n\nAlpha 项目状态:进行中。\n",
        encoding="utf-8",
    )
    certify(ws, "context build/sections/alpha.md")
    # Rule drift -> a rule-change ask item.
    (ws / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\ntype: rule\n---\n\n- 沟通直接高效。\n- 新规则候选。\n",
        encoding="utf-8",
    )

    html_path, json_path = write_portal(ws, tmp_path / "audit-out")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    pref = next(
        s for s in payload["sources"]
        if s["pointer"] == "context build/sections/preference.md"
    )
    assert pref["zone"] == "rule"
    assert any(i["type"] == "rule-change" for i in payload["ask_items"])

    html = html_path.read_text(encoding="utf-8")
    assert "规则区" in html
    assert "Run 待问项" in html
    assert "裁决在 forge run 中进行" in html


def test_cli_zone_init_prints_baseline(tmp_path: Path) -> None:
    from click.testing import CliRunner

    from forge.cli import main

    ws = _workspace(tmp_path)
    result = CliRunner().invoke(main, ["zone", "init", "--root", str(ws)])

    assert result.exit_code == 0
    assert "preference.md" in result.output
    assert (ws / "system" / "verified" / "context build" / "zones.yaml").exists()
