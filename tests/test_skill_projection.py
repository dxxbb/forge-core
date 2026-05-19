"""Governed skill source -> compiled skill projection checks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.gate.doctor import run as doctor_run
from forge.governance.skill_projection import find_skill_projection_gaps


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)


def _write_workspace(root: Path, *, project_skill: bool) -> None:
    skill_dir = root / "assist config" / "skill"
    section_dir = root / "context build" / "sections"
    config_dir = root / "context build" / "config"
    skill_dir.mkdir(parents=True)
    section_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    (skill_dir / "index.md").write_text(
        """\
# Skill Index

- [Lark CLI](lark-cli.md) — Feishu/Lark API client
- [OriginPush VPS](originpush-vps.md) — VPS operator
""",
        encoding="utf-8",
    )
    (skill_dir / "lark-cli.md").write_text("# Lark CLI\n", encoding="utf-8")
    (skill_dir / "originpush-vps.md").write_text("# OriginPush VPS\n", encoding="utf-8")

    origin_upstream = "  - assist config/skill/originpush-vps.md\n" if project_skill else ""
    origin_body = (
        "- `assist config/skill/originpush-vps.md` — VPS operator\n"
        if project_skill
        else ""
    )
    (section_dir / "skill.md").write_text(
        "---\n"
        "name: skill\n"
        "type: skill\n"
        "upstream:\n"
        "  - assist config/skill/index.md\n"
        "  - assist config/skill/lark-cli.md\n"
        f"{origin_upstream}"
        "---\n\n"
        "# Skill Index\n\n"
        "- `assist config/skill/lark-cli.md` — Feishu/Lark API client\n"
        f"{origin_body}",
        encoding="utf-8",
    )
    (config_dir / "agents-md.md").write_text(
        "---\n"
        "name: agents-md\n"
        "target: agents-md\n"
        "sections:\n"
        "  - skill\n"
        "---\n",
        encoding="utf-8",
    )


def test_skill_projection_gap_detects_index_declared_skill_missing_from_section(
    tmp_path: Path,
) -> None:
    _write_workspace(tmp_path, project_skill=False)

    gaps = find_skill_projection_gaps(tmp_path)

    assert len(gaps) == 1
    assert gaps[0].skill_path == "assist config/skill/originpush-vps.md"
    assert gaps[0].missing_upstream is True
    assert gaps[0].missing_pointer is True


def test_skill_projection_gap_clean_when_declared_skill_is_projected(
    tmp_path: Path,
) -> None:
    _write_workspace(tmp_path, project_skill=True)

    assert find_skill_projection_gaps(tmp_path) == []


def test_doctor_warns_on_skill_projection_gap(tmp_path: Path) -> None:
    _write_workspace(tmp_path, project_skill=False)

    report = doctor_run(tmp_path)

    assert report.ok
    assert any("skill projection gap" in w for w in report.warnings)


def test_monitor_reports_skill_projection_gap_on_committed_tree(tmp_path: Path) -> None:
    _write_workspace(tmp_path, project_skill=False)
    _init_git_repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)

    result = CliRunner().invoke(cli_main, ["monitor", "--root", str(tmp_path)])

    assert result.exit_code == 0
    assert "status: attention" in result.output
    assert "skill projection gaps: 1" in result.output
    assert "assist config/skill/originpush-vps.md" in result.output
