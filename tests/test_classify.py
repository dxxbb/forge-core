"""Tests for configurable path dispatch (classify.yaml) and internal content scanner."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge.governance.events import EventType
from forge.governance.classify import (
    ClassifyConfig,
    ClassifyRule,
    build_classify_fn,
    load_config,
    is_ignored,
    _builtin_config,
    _parse_config,
)
from forge.governance.content_scanner import scan_working_tree, format_monitor_lines


# ---------- classify config ----------


def test_builtin_config_has_rules() -> None:
    config = _builtin_config()
    assert len(config.rules) > 0
    assert len(config.ignore) > 0


def test_builtin_classify_user_space_daily() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("user space/daily/memo2026Q2.md") == EventType.content_change


def test_builtin_classify_writing() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("user space/writing/personalOS.md") == EventType.content_change


def test_builtin_classify_workspace_project() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("workspace/project/forge/onepage.md") == EventType.project_update


def test_builtin_classify_skill() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("assist config/skill/lark-cli.md") == EventType.skill_change


def test_builtin_classify_preference() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("assist config/collaboration preference/foo.md") == EventType.preference_change


def test_builtin_classify_kb() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("public knowledge base/topic/ai.md") == EventType.ingest


def test_builtin_classify_context_sections() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("context build/sections/about user.md") == EventType.context_source_change


def test_builtin_ignore_obsidian() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn(".obsidian/appearance.json") == EventType.ignored


def test_builtin_ignore_system() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("system/inbox/foo.md") == EventType.ignored


def test_builtin_unclassified() -> None:
    config = _builtin_config()
    fn = build_classify_fn(config)
    assert fn("random/unknown/path.md") == EventType.unclassified


def test_is_ignored() -> None:
    config = _builtin_config()
    assert is_ignored(".obsidian/foo", config) is True
    assert is_ignored("user space/daily/memo.md", config) is False


# ---------- yaml config loading ----------


def test_load_config_from_yaml(tmp_path: Path) -> None:
    yaml_dir = tmp_path / ".forge" / "governance"
    yaml_dir.mkdir(parents=True)
    (yaml_dir / "classify.yaml").write_text(
        """\
rules:
  - pattern: "my/custom/path/"
    event_type: content_change
  - pattern: "kb/"
    event_type: ingest
ignore:
  - ".git/"
  - "node_modules/"
""",
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert len(config.rules) == 2
    assert config.rules[0].pattern == "my/custom/path/"
    assert config.rules[0].event_type == EventType.content_change
    assert ".git/" in config.ignore


def test_load_config_fallback_no_file(tmp_path: Path) -> None:
    config = load_config(tmp_path)
    assert len(config.rules) == len(_builtin_config().rules)


def test_parse_config_unknown_event_type() -> None:
    data = {"rules": [{"pattern": "x/", "event_type": "nonexistent_type"}]}
    config = _parse_config(data)
    assert config.rules[0].event_type == EventType.unclassified


# ---------- content scanner ----------


def _init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "test"], check=True)


def _commit(path: Path, filename: str, content: str, message: str) -> None:
    full = path / filename
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", filename], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-q", "-m", message], check=True)


def test_scanner_detects_modified_memo(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "user space/daily/memo.md", "old content", "init")
    (tmp_path / "user space/daily/memo.md").write_text("new content")

    changes = scan_working_tree(tmp_path)
    assert len(changes) == 1
    assert changes[0].path == "user space/daily/memo.md"
    assert changes[0].event_type == EventType.content_change


def test_scanner_detects_new_writing(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    (tmp_path / "user space/writing").mkdir(parents=True)
    (tmp_path / "user space/writing/draft.md").write_text("draft")

    changes = scan_working_tree(tmp_path)
    assert any(c.path == "user space/writing/draft.md" for c in changes)


def test_scanner_ignores_obsidian(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    (tmp_path / ".obsidian").mkdir(parents=True)
    (tmp_path / ".obsidian/config.json").write_text("{}")

    changes = scan_working_tree(tmp_path)
    assert not any(c.path.startswith(".obsidian") for c in changes)


def test_scanner_ignores_unclassified(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    (tmp_path / "random").mkdir(parents=True)
    (tmp_path / "random/file.md").write_text("x")

    changes = scan_working_tree(tmp_path)
    assert not any(c.path.startswith("random/") for c in changes)


def test_scanner_empty_repo(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    changes = scan_working_tree(tmp_path)
    assert changes == []


def test_format_monitor_lines_with_changes(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "user space/daily/memo.md", "old", "init")
    (tmp_path / "user space/daily/memo.md").write_text("new")
    (tmp_path / "user space/writing").mkdir(parents=True)
    (tmp_path / "user space/writing/draft.md").write_text("draft")

    issues, actions = format_monitor_lines(tmp_path)
    assert len(issues) == 1
    assert "internal content changes" in issues[0]
    assert len(actions) >= 1


def test_format_monitor_lines_clean(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    issues, actions = format_monitor_lines(tmp_path)
    assert issues == []
    assert actions == []


def test_custom_config_scanner(tmp_path: Path) -> None:
    """Scanner respects custom classify config."""
    _init_git_repo(tmp_path)
    _commit(tmp_path, "README.md", "init", "init")
    (tmp_path / "my/notes").mkdir(parents=True)
    (tmp_path / "my/notes/idea.md").write_text("idea")

    config = ClassifyConfig(
        rules=[ClassifyRule("my/notes/", EventType.content_change)],
        ignore=[".git/"],
    )
    changes = scan_working_tree(tmp_path, config)
    assert len(changes) == 1
    assert changes[0].event_type == EventType.content_change
