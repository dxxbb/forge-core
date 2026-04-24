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
