"""v0.5.0: working-tree-aware monitor tests.

Cover the v0.5 design points:

  1. dirty_hash compute (sha256 of porcelain output)
  2. monitor reports working tree drift (HEAD unchanged, M count changed)
  3. monitor reports working tree drift (HEAD unchanged, ?? count changed)
  4. priority: HEAD diff > dirty drift (commit moved → suppress dirty)
  5. staleness reminder (mock now - last_synced.at > default 7 days)
  6. staleness reminder per-project override (`staleness_days: 30`)
  7. approve writes dirty_hash + dirty_count
  8. capture path leaves last_synced untouched (only approve writes it)
  9. legacy onepage (no dirty_hash field) → treated as "needs sync" when
     working tree is non-empty
 10. dirty_hash matches but git HEAD ahead → still report commit drift only

Plus an end-to-end fixture exercise that walks: clean → add untracked →
monitor reports drift → restore → monitor clean → mock 8 days later →
monitor reports staleness.
"""

from __future__ import annotations

import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.workspace_project import (
    DEFAULT_STALENESS_DAYS,
    ProjectStatus,
    compute_dirty_hash,
    discover_project_onepages,
    head_hash,
    load_project_onepage,
    porcelain_status,
    probe_project,
    update_last_synced,
    working_tree_snapshot,
)


# ---------- helpers ----------


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _make_personalos_root(tmp_path: Path) -> Path:
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    return root


def _make_upstream_repo(tmp_path: Path, name: str = "watermark") -> Path:
    repo = tmp_path / "external" / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "t@t")
    (repo / "REPORT.md").write_text("# Report\n\nphase 1\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def _write_onepage(
    workspace: Path,
    name: str,
    *,
    local_dir: Path,
    last_synced_commit: str = "",
    last_synced_at: str = "",
    last_synced_dirty_hash: str | None = None,
    last_synced_dirty_count: int | None = None,
    staleness_days: int | None = None,
    body: str = "Project description.\n",
) -> Path:
    op_dir = workspace / "workspace" / "project" / name
    op_dir.mkdir(parents=True, exist_ok=True)
    op = op_dir / "onepage.md"
    fm_lines = ["---", "kind: project", f"name: {name}", "upstream:"]
    fm_lines.append(f"  local_dir: {local_dir}")
    if staleness_days is not None:
        fm_lines.append(f"  staleness_days: {staleness_days}")
    if last_synced_commit or last_synced_at or last_synced_dirty_hash is not None:
        fm_lines.append("last_synced:")
        if last_synced_commit:
            fm_lines.append(f"  commit: {last_synced_commit}")
        if last_synced_at:
            fm_lines.append(f"  at: '{last_synced_at}'")
        if last_synced_dirty_hash is not None:
            fm_lines.append(f"  dirty_hash: {last_synced_dirty_hash}")
            count = last_synced_dirty_count if last_synced_dirty_count is not None else 0
            fm_lines.append(f"  dirty_count: {count}")
    fm_lines.append("---")
    op.write_text("\n".join(fm_lines) + "\n\n" + body, encoding="utf-8")
    return op


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    fake = tmp_path / "fakehome"
    fake.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake))
    return fake


# ---------- 1. dirty_hash compute ----------


def test_compute_dirty_hash_empty_input_returns_empty() -> None:
    assert compute_dirty_hash("") == ""


def test_compute_dirty_hash_deterministic() -> None:
    text = " M README.md\n?? new.py\n"
    h1 = compute_dirty_hash(text)
    h2 = compute_dirty_hash(text)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex


def test_compute_dirty_hash_changes_with_content() -> None:
    a = compute_dirty_hash(" M README.md\n")
    b = compute_dirty_hash(" M README.md\n?? new.py\n")
    assert a != b


def test_porcelain_status_counts_modified_and_untracked(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    # modify tracked + add untracked
    (repo / "REPORT.md").write_text("# Report\nedited\n", encoding="utf-8")
    (repo / "new.py").write_text("x\n", encoding="utf-8")
    (repo / "another.py").write_text("y\n", encoding="utf-8")
    raw, modified, untracked = porcelain_status(repo)
    assert modified == 1
    assert untracked == 2
    assert "REPORT.md" in raw
    assert "new.py" in raw


def test_working_tree_snapshot_clean_returns_empty(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    h, count = working_tree_snapshot(repo)
    assert h == ""
    assert count == 0


def test_working_tree_snapshot_dirty_returns_hash_and_count(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    (repo / "new.py").write_text("x\n", encoding="utf-8")
    h, count = working_tree_snapshot(repo)
    assert h != ""
    assert len(h) == 64
    assert count == 1


# ---------- 2. monitor reports working tree drift (modified) ----------


def test_probe_reports_dirty_drift_when_modified_count_changes(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    # baseline snapshot at clean tree (empty hash); record in onepage as ""
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    # Now modify a tracked file
    (repo / "REPORT.md").write_text("# Report\nedited\n", encoding="utf-8")

    op = load_project_onepage(op_path)
    assert op is not None
    status = probe_project(op)
    assert status.commit_drift == ""
    assert "working tree drift" in status.dirty_drift
    assert "1 modified" in status.dirty_drift


# ---------- 3. monitor reports working tree drift (untracked) ----------


def test_probe_reports_dirty_drift_when_untracked_count_changes(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    # Add untracked file
    (repo / "new.py").write_text("y\n", encoding="utf-8")

    op = load_project_onepage(op_path)
    assert op is not None
    status = probe_project(op)
    assert status.commit_drift == ""
    assert "working tree drift" in status.dirty_drift
    assert "1 untracked" in status.dirty_drift


# ---------- 4. priority: HEAD ahead of last_synced.commit ----------


def test_probe_commit_drift_takes_priority_over_dirty(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    initial = head_hash(repo)
    assert initial is not None
    # Advance HEAD with a new commit
    (repo / "B.md").write_text("b\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "second")
    # Add unrelated dirty work (uncommitted)
    (repo / "draft.txt").write_text("draft\n", encoding="utf-8")

    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=initial,
        last_synced_at="2099-01-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    op = load_project_onepage(op_path)
    assert op is not None
    status = probe_project(op)
    # both populated, but format_monitor_lines picks commit_drift only
    assert "commit(s) ahead" in status.commit_drift
    from forge.governance.workspace_project import format_monitor_lines
    lines = format_monitor_lines(status)
    assert len(lines) == 1
    assert "commit(s) ahead" in lines[0]
    assert "working tree drift" not in lines[0]


# ---------- 5. staleness reminder default 7 days ----------


def test_probe_staleness_default_after_eight_days(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None

    last_at = "2026-01-01T00:00:00+00:00"
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at=last_at,
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    op = load_project_onepage(op_path)
    assert op is not None

    # Mock now = 8 days after last_at (default threshold = 7)
    fake_now = datetime(2026, 1, 9, 0, 0, 0, tzinfo=timezone.utc)
    status = probe_project(op, now=fake_now)
    assert status.commit_drift == ""
    assert status.dirty_drift == ""
    assert "stale" in status.staleness
    assert "8 days ago" in status.staleness
    assert op.staleness_days == DEFAULT_STALENESS_DAYS


def test_probe_no_staleness_within_threshold(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None

    last_at = "2026-01-01T00:00:00+00:00"
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at=last_at,
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    op = load_project_onepage(op_path)
    assert op is not None

    # 6 days < 7-day default → no staleness
    fake_now = datetime(2026, 1, 7, 0, 0, 0, tzinfo=timezone.utc)
    status = probe_project(op, now=fake_now)
    assert status.staleness == ""


# ---------- 6. staleness reminder per-project override ----------


def test_probe_staleness_respects_per_project_override(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    last_at = "2026-01-01T00:00:00+00:00"
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at=last_at,
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
        staleness_days=30,
    )
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.staleness_days == 30

    # 15 days < 30 → no staleness despite > default 7
    fake_now = datetime(2026, 1, 16, 0, 0, 0, tzinfo=timezone.utc)
    status = probe_project(op, now=fake_now)
    assert status.staleness == ""

    # 35 days > 30 → staleness
    fake_now2 = datetime(2026, 2, 5, 0, 0, 0, tzinfo=timezone.utc)
    status2 = probe_project(op, now=fake_now2)
    assert "stale" in status2.staleness
    assert "35 days ago" in status2.staleness


# ---------- 7. approve writes dirty_hash + dirty_count ----------


def test_approve_writes_dirty_hash_and_count(tmp_path: Path) -> None:
    """Full pr-done approve cycle: project repo has uncommitted dev work,
    approve should snapshot it into the onepage."""
    repo = _make_upstream_repo(tmp_path)
    initial = head_hash(repo)
    assert initial is not None
    # Add uncommitted dev work (mimics watermark ver1 reality)
    (repo / "ver1").mkdir()
    (repo / "ver1" / "main.py").write_text("# code\n", encoding="utf-8")
    (repo / "REPORT.md").write_text("# Report\n\nphase 2 in progress\n", encoding="utf-8")

    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@t")
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init os")

    # User edits the onepage as part of "the PR" change
    op_path.write_text(
        op_path.read_text(encoding="utf-8") + "\n## Update\nphase 2 underway.\n",
        encoding="utf-8",
    )

    pr_id = "20260507-100000-watermark-update"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(
        "---\nkind: pr\ntype: workspace-project-update\nstatus: pending\n---\n\nbody\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main, ["pr", "done", pr_id, "--root", str(root), "-m", "merged"]
    )
    assert result.exit_code == 0, result.output

    # Verify onepage has dirty_hash + dirty_count after approve
    text = op_path.read_text(encoding="utf-8")
    assert "dirty_hash:" in text
    assert "dirty_count:" in text
    # Reload and confirm matches working tree snapshot
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.has_dirty_hash_field is True
    assert op.last_synced_dirty_count >= 2  # ver1/main.py untracked + REPORT.md modified
    assert len(op.last_synced_dirty_hash) == 64

    # And probe_project should now report clean (HEAD same, dirty_hash matches)
    status = probe_project(op, now=datetime.now(timezone.utc))
    assert status.commit_drift == ""
    assert status.dirty_drift == ""


# ---------- 8. update_last_synced legacy compat (no dirty_hash provided) ----------


def test_update_last_synced_without_dirty_hash_stays_v04_compatible(tmp_path: Path) -> None:
    """Calling update_last_synced without dirty_hash keeps v0.4 frontmatter
    layout (commit + at only)."""
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(root, "x", local_dir=tmp_path / "x")
    ok = update_last_synced(op_path, commit="abc", at="2026-05-07T00:00:00+00:00")
    assert ok is True
    text = op_path.read_text(encoding="utf-8")
    assert "commit: abc" in text
    assert "dirty_hash" not in text


def test_update_last_synced_with_dirty_hash_writes_all_four(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(root, "x", local_dir=tmp_path / "x")
    ok = update_last_synced(
        op_path,
        commit="abc",
        at="2026-05-07T00:00:00+00:00",
        dirty_hash="deadbeef" * 8,
        dirty_count=24,
    )
    assert ok is True
    text = op_path.read_text(encoding="utf-8")
    assert "commit: abc" in text
    assert "dirty_hash: " in text
    assert "dirty_count: 24" in text


# ---------- 9. legacy onepage compat ----------


def test_legacy_onepage_no_dirty_hash_with_clean_tree_silent(tmp_path: Path) -> None:
    """v0.4 onepage (no dirty_hash field) + clean external tree → no dirty drift.
    The legitimate "had a clean tree at last sync" case stays clean."""
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    # NB: dirty_hash explicitly None → omitted from frontmatter
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",
    )
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.has_dirty_hash_field is False
    status = probe_project(op)
    assert status.dirty_drift == ""


def test_legacy_onepage_no_dirty_hash_with_dirty_tree_reports_drift(tmp_path: Path) -> None:
    """v0.4 onepage + currently-dirty tree → report drift with a hint that
    we have no baseline (capture will establish one)."""
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    (repo / "uncommitted.py").write_text("x\n", encoding="utf-8")

    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",
        # no dirty_hash
    )
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.has_dirty_hash_field is False
    status = probe_project(op)
    assert "working tree drift" in status.dirty_drift
    assert "legacy onepage" in status.dirty_drift


# ---------- 10. dirty_hash matches but git HEAD ahead → still report commit drift ----------


def test_dirty_hash_match_but_head_ahead_still_reports_commit_drift(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    initial = head_hash(repo)
    assert initial is not None
    # Establish a baseline: snapshot is clean at initial
    base_hash = ""
    base_count = 0
    # Move HEAD forward (commit) but keep working tree clean
    (repo / "C.md").write_text("c\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "third")

    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "wm",
        local_dir=repo,
        last_synced_commit=initial,
        last_synced_at="2099-01-01T00:00:00+00:00",
        last_synced_dirty_hash=base_hash,
        last_synced_dirty_count=base_count,
    )
    op = load_project_onepage(op_path)
    assert op is not None
    status = probe_project(op)
    assert "commit(s) ahead" in status.commit_drift
    # Working tree is clean now (committed) so dirty_drift stays empty —
    # current dirty_hash == baseline empty hash
    assert status.dirty_drift == ""


# ---------- 11. monitor CLI surfaces dirty drift ----------


def test_monitor_cli_reports_working_tree_drift(
    tmp_path: Path, isolated_home: Path
) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None

    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )

    # Working tree clean → status: clean
    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: clean" in result.output, result.output

    # Add untracked file → working tree drift
    (repo / "another.py").write_text("y\n", encoding="utf-8")
    result2 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: attention" in result2.output, result2.output
    assert "workspace-project changed: watermark" in result2.output
    assert "working tree drift" in result2.output


# ---------- 12. e2e fixture: drift → restore → clean → 8 days → stale ----------


def test_e2e_fixture_drift_restore_clean_cycle(
    tmp_path: Path, isolated_home: Path
) -> None:
    """Walk the real working-tree lifecycle on a fixture personalOS:

      1. project at HEAD with dirty_hash baseline (clean) → monitor clean
      2. add untracked → monitor reports "working tree drift: ... untracked"
      3. remove untracked → monitor clean again

    (The staleness branch is covered separately by
    test_probe_staleness_default_after_eight_days; mocking `datetime.now`
    inside a CLI subprocess is fragile, so we test it at the probe layer.)
    """
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None

    # last_synced.at far in the future so staleness never fires during the
    # real-clock run.
    last_at = "2099-04-30T00:00:00+00:00"
    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at=last_at,
        last_synced_dirty_hash="",  # clean baseline
        last_synced_dirty_count=0,
    )

    runner = CliRunner()

    # Step 1: clean
    r1 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: clean" in r1.output, r1.output

    # Step 2: untracked file → working tree drift
    untracked = repo / "another.py"
    untracked.write_text("x\n", encoding="utf-8")
    r2 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: attention" in r2.output
    assert "working tree drift" in r2.output
    assert "1 untracked" in r2.output

    # Step 3: restore → clean
    untracked.unlink()
    r3 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: clean" in r3.output, r3.output
