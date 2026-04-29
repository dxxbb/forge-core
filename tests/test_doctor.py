from pathlib import Path

from forge.gate.doctor import run as doctor


def test_doctor_clean_workspace(workspace: Path) -> None:
    r = doctor(workspace)
    assert r.ok
    # 2 sections, 1 config — both sections are referenced, no orphans
    assert r.warnings == []
    assert any("sections: 2" in i for i in r.info)
    assert any("configs: 1" in i for i in r.info)


def test_doctor_flags_unknown_section_ref(workspace: Path) -> None:
    (workspace / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections: [alpha, ghost]\n---\n",
        encoding="utf-8",
    )
    r = doctor(workspace)
    assert not r.ok
    assert any("unknown section `ghost`" in e for e in r.errors)


def test_doctor_required_sections_missing(workspace: Path) -> None:
    (workspace / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections: [alpha]\n"
        "required_sections: [alpha, beta]\n---\n",
        encoding="utf-8",
    )
    r = doctor(workspace)
    assert not r.ok
    assert any("required_sections" in e and "beta" in e for e in r.errors)


def test_doctor_required_sections_covered(workspace: Path) -> None:
    (workspace / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: claude-code\nsections: [alpha, beta]\n"
        "required_sections: [alpha, beta]\n---\n",
        encoding="utf-8",
    )
    r = doctor(workspace)
    assert r.ok


def test_doctor_warns_orphan_section(workspace: Path) -> None:
    (workspace / "sp" / "section" / "lonely.md").write_text(
        "---\nname: lonely\n---\norphan body\n", encoding="utf-8"
    )
    r = doctor(workspace)
    assert r.ok  # still ok — it's only a warning
    assert any("lonely" in w and "orphan" in w for w in r.warnings)


def test_doctor_warns_derived_without_upstream(workspace: Path) -> None:
    (workspace / "sp" / "section" / "alpha.md").write_text(
        "---\nname: alpha\nkind: derived\n---\nbody\n", encoding="utf-8"
    )
    r = doctor(workspace)
    assert any("derived" in w and "upstream" in w for w in r.warnings)


def test_doctor_flags_unknown_adapter(workspace: Path) -> None:
    (workspace / "sp" / "config" / "main.md").write_text(
        "---\nname: main\ntarget: fictional-adapter\nsections: [alpha, beta]\n---\n",
        encoding="utf-8",
    )
    r = doctor(workspace)
    assert any("fictional-adapter" in w for w in r.warnings)


# ---------- v0428 personalOS asset coverage ----------


def _make_v0428_workspace(root: Path) -> None:
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)
    (root / "assist config" / "collaboration preference").mkdir(parents=True)
    (root / "context build" / "config" / "claude-code.md").write_text(
        "---\nname: c\ntarget: claude-code\nsections: [preference]\n---\n",
        encoding="utf-8",
    )


def test_coverage_reports_bridged_when_section_lists_upstream(tmp_path: Path) -> None:
    _make_v0428_workspace(tmp_path)
    (tmp_path / "assist config" / "collaboration preference" / "working-style.md").write_text(
        "x\n", encoding="utf-8"
    )
    (tmp_path / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\nkind: derived\nupstream:\n  - assist config/collaboration preference/working-style.md\n---\n\nbody\n",
        encoding="utf-8",
    )
    r = doctor(tmp_path)
    coverage_lines = [i for i in r.info if "asset coverage" in i]
    assert any("`assist config/`" in line and "1/1" in line for line in coverage_lines)


def test_coverage_reports_unbridged_files(tmp_path: Path) -> None:
    _make_v0428_workspace(tmp_path)
    (tmp_path / "assist config" / "collaboration preference" / "feedback-log.md").write_text(
        "y\n", encoding="utf-8"
    )
    (tmp_path / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\nkind: derived\nupstream: []\n---\n\nbody\n",
        encoding="utf-8",
    )
    r = doctor(tmp_path)
    assert any("0/1" in i for i in r.info if "asset coverage" in i)
    assert any("not bridged: assist config/collaboration preference/feedback-log.md" in i for i in r.info)


def test_coverage_does_not_run_on_legacy_layout(workspace: Path) -> None:
    """workspace fixture is the legacy sp/section layout."""
    r = doctor(workspace)
    assert not any("asset coverage" in i for i in r.info)


def test_coverage_accepts_basename_or_relative_in_upstream(tmp_path: Path) -> None:
    """Sections may write upstream as a basename, a relative path, or an
    absolute path — doctor recognizes all three as the same bridge."""
    _make_v0428_workspace(tmp_path)
    (tmp_path / "assist config" / "collaboration preference" / "a.md").write_text("a\n", encoding="utf-8")
    (tmp_path / "assist config" / "collaboration preference" / "b.md").write_text("b\n", encoding="utf-8")
    (tmp_path / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\nkind: derived\nupstream:\n  - a.md\n  - assist config/collaboration preference/b.md\n---\n\nbody\n",
        encoding="utf-8",
    )
    r = doctor(tmp_path)
    assert any("2/2" in i for i in r.info if "asset coverage" in i)


def test_coverage_truncates_long_unbridged_list(tmp_path: Path) -> None:
    _make_v0428_workspace(tmp_path)
    for i in range(8):
        (tmp_path / "assist config" / "collaboration preference" / f"f{i}.md").write_text("x", encoding="utf-8")
    (tmp_path / "context build" / "sections" / "preference.md").write_text(
        "---\nname: preference\nkind: derived\nupstream: []\n---\n\nbody\n",
        encoding="utf-8",
    )
    r = doctor(tmp_path)
    truncations = [i for i in r.info if "more" in i]
    assert truncations and "+3 more" in truncations[0]
