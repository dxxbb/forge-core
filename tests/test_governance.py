"""Governance pillar 单测：events + inbox + watcher（用 fake git repo）+ rollback。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from forge.governance.events import EventType, default_classify
from forge.governance.inbox import Inbox
from forge.governance.watcher import scan_git
from forge.governance.rollback import rollback
from forge.gate import actions as gate


# ---------- events ----------

def test_default_classify_skill() -> None:
    assert default_classify("01 assist/learn and improve/skill/foo.md") == EventType.skill_change


def test_default_classify_project() -> None:
    assert default_classify("03 workspace/project/forge/onepage.md") == EventType.project_update


def test_default_classify_unknown() -> None:
    assert default_classify("random/path.md") == EventType.unclassified


# ---------- inbox ----------

def test_inbox_enqueue_list_skip(tmp_path: Path) -> None:
    inbox = Inbox(tmp_path)
    t1 = inbox.enqueue("project_update", "abc123", "03 workspace/project/x.md", note="note1")
    t2 = inbox.enqueue("skill_change", "def456", "01 assist/.../skill.md", note="note2")
    assert t1.id == 1 and t2.id == 2

    items = inbox.list()
    assert len(items) == 2
    assert items[0].event_type == "project_update"
    assert items[0].note == "note1"

    inbox.skip(1, reason="not relevant")
    items = inbox.list()
    assert len(items) == 1
    assert items[0].id == 2

    # changelog should record the skip
    log = tmp_path / ".forge" / "governance" / "changelog.md"
    assert log.exists()
    assert "skip inbox/0001" in log.read_text("utf-8")
    assert "not relevant" in log.read_text("utf-8")


def test_inbox_skip_missing_raises(tmp_path: Path) -> None:
    inbox = Inbox(tmp_path)
    with pytest.raises(KeyError):
        inbox.skip(99, reason="gone")


# ---------- watcher (requires real git) ----------

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


def test_watcher_scans_new_commits_and_queues(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "03 workspace/project/alpha/onepage.md", "# alpha\nbody\n", "initial")
    _commit(
        tmp_path,
        "01 assist/learn and improve/skill/new.md",
        "# new skill\n",
        "add skill",
    )

    changes = scan_git(tmp_path)
    assert len(changes) == 2
    event_types = {c.event_type for c in changes}
    assert EventType.project_update in event_types
    assert EventType.skill_change in event_types

    inbox = Inbox(tmp_path)
    assert len(inbox.list()) == 2


def test_watcher_skips_derived_kind(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    # 带 kind: derived 的 frontmatter，应被 watcher 跳过
    _commit(
        tmp_path,
        "03 workspace/project/x/onepage.md",
        "---\nkind: derived\n---\n\ncontent\n",
        "add derived",
    )
    changes = scan_git(tmp_path)
    assert len(changes) == 0


def test_watcher_skips_commit_with_approved_trailer(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    full = tmp_path / "03 workspace/project/x/onepage.md"
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "commit", "-q", "-m", "msg\n\nApproved-by: dxy"],
        check=True,
    )
    changes = scan_git(tmp_path)
    assert len(changes) == 0


def test_watcher_state_tracks_last_seen(tmp_path: Path) -> None:
    _init_git_repo(tmp_path)
    _commit(tmp_path, "03 workspace/project/a/onepage.md", "a", "a")
    scan_git(tmp_path)
    # 第二次扫，没有新 commit → 空结果
    changes = scan_git(tmp_path)
    assert len(changes) == 0
    # 加一个新 commit
    _commit(tmp_path, "03 workspace/project/b/onepage.md", "b", "b")
    changes = scan_git(tmp_path)
    assert len(changes) == 1


# ---------- rollback (v0.2: git-based, supports any hash in history) ----------

def test_rollback_lists_available(workspace: Path) -> None:
    """rollback without target_hash returns commit list."""
    result = rollback(workspace, target_hash_prefix=None)
    assert "current_hash" in result
    assert isinstance(result["available"], list)
    assert len(result["available"]) >= 1  # at least the fixture initial commit


def test_rollback_to_old_hash_restores_working_tree(workspace: Path) -> None:
    """v0.2: rollback to ANY commit in history (not just the latest)."""
    # First approve: v1
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text("---\nname: alpha\ntype: test\n---\nv1\n", encoding="utf-8")
    r1 = gate.approve(workspace, note="to v1")
    v1_hash = r1.approved_hash

    # Second approve: v2
    p.write_text("---\nname: alpha\ntype: test\n---\nv2\n", encoding="utf-8")
    gate.approve(workspace, note="to v2")

    # Roll back to v1
    result = rollback(workspace, target_hash_prefix=v1_hash[:12])
    assert result["applied_to"] == v1_hash

    # Working tree shows v1 content
    assert "v1" in p.read_text("utf-8")
    assert "v2" not in p.read_text("utf-8")


def test_rollback_refuses_with_uncommitted_changes(workspace: Path) -> None:
    p = workspace / "sp" / "section" / "alpha.md"
    p.write_text("---\nname: alpha\n---\nuncommitted\n", encoding="utf-8")

    head = gate.status(workspace)["approved_hash"]
    with pytest.raises(RuntimeError, match="uncommitted"):
        rollback(workspace, target_hash_prefix=head[:12])


def test_rollback_unknown_hash_raises(workspace: Path) -> None:
    with pytest.raises(ValueError):
        rollback(workspace, target_hash_prefix="ffffffffffff")
