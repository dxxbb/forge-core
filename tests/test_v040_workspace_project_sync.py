"""v0.4.0: workspace-project sync tests.

Cover the four pieces of work specified for v0.4.0:

  1. Schema parsing + doctor INFO lint for `kind: project` onepages.
  2. `forge monitor` reports git HEAD drift + status_sources mtime drift.
  3. `forge capture --workspace-project <name>` writes correct capture/inbox.
  4. `forge approve` (`forge pr done`) injects `last_synced` into modified
     project onepages atomically.

End-to-end: a single fixture project, monitor → capture → approve → verify
last_synced was written.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.workspace_project import (
    ProjectOnepage,
    build_capture_markdown,
    discover_project_onepages,
    find_modified_project_onepages,
    head_hash,
    is_git_repo,
    load_project_onepage,
    probe_project,
    split_frontmatter,
    update_last_synced,
)


# ---------- helpers ----------


def _git(cwd: Path, *args: str) -> str:
    """Run git in cwd; return stdout. Asserts success."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _make_personalos_root(tmp_path: Path) -> Path:
    """Build a minimal personalOS layout (capture/, system/, workspace/project/)."""
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    return root


def _make_upstream_repo(tmp_path: Path, name: str = "watermark") -> Path:
    """Create a tiny external git repo with one commit."""
    repo = tmp_path / "external" / name
    repo.mkdir(parents=True)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "t@t")
    (repo / "REPORT.md").write_text("# Report\n\nphase 1\n", encoding="utf-8")
    (repo / "README.md").write_text("# external\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "initial")
    return repo


def _write_onepage(
    workspace: Path,
    name: str,
    *,
    local_dir: Path | None,
    status_sources: list[str] | None = None,
    last_synced_commit: str = "",
    last_synced_at: str = "",
    git_remote: str = "",
    body: str = "Project description.\n",
    kind: str = "project",
) -> Path:
    """Write a project onepage with optional fields."""
    op_dir = workspace / "workspace" / "project" / name
    op_dir.mkdir(parents=True, exist_ok=True)
    op = op_dir / "onepage.md"
    fm_lines = ["---", f"kind: {kind}", f"name: {name}"]
    if local_dir is not None or git_remote or status_sources:
        fm_lines.append("upstream:")
        if local_dir is not None:
            fm_lines.append(f"  local_dir: {local_dir}")
        if git_remote:
            fm_lines.append(f"  git_remote: {git_remote}")
        if status_sources:
            fm_lines.append("  status_sources:")
            for s in status_sources:
                fm_lines.append(f"    - {s}")
    if last_synced_commit or last_synced_at:
        fm_lines.append("last_synced:")
        if last_synced_commit:
            fm_lines.append(f"  commit: {last_synced_commit}")
        if last_synced_at:
            fm_lines.append(f"  at: {last_synced_at}")
    fm_lines.append("---")
    op.write_text("\n".join(fm_lines) + "\n\n" + body, encoding="utf-8")
    return op


# ---------- 1. schema parsing ----------


def test_load_project_onepage_with_full_upstream(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(
        root,
        "watermark",
        local_dir=upstream,
        git_remote="https://github.com/me/wm.git",
        status_sources=["REPORT.md", "docs/plan.md"],
        last_synced_commit="abc123",
        last_synced_at="2026-05-01T00:00:00+00:00",
    )

    loaded = load_project_onepage(op)
    assert loaded is not None
    assert loaded.name == "watermark"
    assert loaded.local_dir == upstream
    assert loaded.git_remote == "https://github.com/me/wm.git"
    assert loaded.status_sources == ["REPORT.md", "docs/plan.md"]
    assert loaded.last_synced_commit == "abc123"
    assert loaded.last_synced_at == "2026-05-01T00:00:00+00:00"
    assert loaded.has_upstream is True


def test_load_project_onepage_skips_non_project_kind(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(
        root, "old", local_dir=None, kind="preference"
    )
    assert load_project_onepage(op) is None


def test_load_project_onepage_handles_kind_project_without_upstream(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(root, "draft", local_dir=None)
    loaded = load_project_onepage(op)
    assert loaded is not None
    assert loaded.name == "draft"
    assert loaded.has_upstream is False
    assert loaded.local_dir is None


def test_load_project_onepage_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    root = _make_personalos_root(tmp_path)
    op_dir = root / "workspace" / "project" / "tilde"
    op_dir.mkdir(parents=True)
    (op_dir / "onepage.md").write_text(
        "---\n"
        "kind: project\n"
        "name: tilde\n"
        "upstream:\n"
        "  local_dir: ~/projects/x\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    loaded = load_project_onepage(op_dir / "onepage.md")
    assert loaded is not None
    assert loaded.local_dir == fake_home / "projects" / "x"


def test_discover_project_onepages_only_returns_kind_project(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    root = _make_personalos_root(tmp_path)
    _write_onepage(root, "alpha", local_dir=upstream)
    _write_onepage(root, "legacy", local_dir=None, kind="preference")
    # missing onepage.md entirely
    (root / "workspace" / "project" / "stub").mkdir()

    onepages = discover_project_onepages(root)
    names = [op.name for op in onepages]
    assert names == ["alpha"]


def test_split_frontmatter_handles_yaml_nested(tmp_path: Path) -> None:
    text = (
        "---\n"
        "kind: project\n"
        "name: x\n"
        "upstream:\n"
        "  local_dir: /a\n"
        "---\n\nbody\n"
    )
    fm, body = split_frontmatter(text)
    assert fm is not None
    assert fm["upstream"] == {"local_dir": "/a"}
    assert body == "\nbody\n"


# ---------- 2. doctor lint ----------


def test_doctor_info_for_project_onepage_missing_local_dir(tmp_path: Path) -> None:
    """A `kind: project` onepage without upstream.local_dir surfaces as INFO,
    not a warning or error."""
    root = _make_personalos_root(tmp_path)
    # need legacy v0.428 layout to call doctor.run
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)
    _write_onepage(root, "draft", local_dir=None)

    from forge.gate.doctor import run as doctor_run

    report = doctor_run(root)
    info_text = "\n".join(report.info)
    assert "workspace-project onepages: 1" in info_text
    assert "project `draft`: missing upstream.local_dir" in info_text
    # No errors / warnings caused by this lint
    assert all("draft" not in e for e in report.errors)
    assert all("draft" not in w for w in report.warnings)


def test_doctor_no_workspace_project_lines_when_no_onepages(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    (root / "context build" / "sections").mkdir(parents=True)
    (root / "context build" / "config").mkdir(parents=True)
    from forge.gate.doctor import run as doctor_run

    report = doctor_run(root)
    info_text = "\n".join(report.info)
    assert "workspace-project onepages" not in info_text


# ---------- 3. monitor (probe + cli output) ----------


def test_probe_detects_commit_drift(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial_hash = head_hash(upstream)
    assert initial_hash is not None
    # one more commit
    (upstream / "B.md").write_text("b\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "second")

    root = _make_personalos_root(tmp_path)
    op = _write_onepage(
        root,
        "wm",
        local_dir=upstream,
        last_synced_commit=initial_hash,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )
    loaded = load_project_onepage(op)
    assert loaded is not None
    status = probe_project(loaded)
    assert status.issue == ""
    assert "1 commit(s) ahead" in status.commit_drift


def test_probe_never_synced_reports_drift(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(root, "wm", local_dir=upstream)
    loaded = load_project_onepage(op)
    assert loaded is not None
    status = probe_project(loaded)
    assert "never synced" in status.commit_drift


def test_probe_status_source_mtime_drift(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial = head_hash(upstream)
    assert initial is not None
    # advance file mtime well past last_synced.at
    report = upstream / "REPORT.md"
    new_mtime = time.time()
    os.utime(report, (new_mtime, new_mtime))

    root = _make_personalos_root(tmp_path)
    op = _write_onepage(
        root,
        "wm",
        local_dir=upstream,
        status_sources=["REPORT.md"],
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )
    loaded = load_project_onepage(op)
    assert loaded is not None
    status = probe_project(loaded)
    assert status.commit_drift == ""  # HEAD unchanged
    assert status.status_drift == ["REPORT.md"]


def test_probe_warn_when_local_dir_missing(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    fake = tmp_path / "no-such-dir"
    op = _write_onepage(root, "wm", local_dir=fake)
    loaded = load_project_onepage(op)
    assert loaded is not None
    status = probe_project(loaded)
    assert "does not exist" in status.issue


def test_probe_warn_when_local_dir_not_git(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(root, "wm", local_dir=plain)
    loaded = load_project_onepage(op)
    assert loaded is not None
    status = probe_project(loaded)
    assert "not a git repo" in status.issue


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate HOME so monitor's _import_updates doesn't see the real
    ~/.claude/CLAUDE.md when the dev box happens to have one."""
    fake = tmp_path / "fakehome"
    fake.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake))
    return fake


def test_monitor_cli_reports_workspace_project_change(
    tmp_path: Path, isolated_home: Path
) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial = head_hash(upstream)
    assert initial is not None
    (upstream / "C.md").write_text("c\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "third")

    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "watermark",
        local_dir=upstream,
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "workspace-project changed: watermark" in result.output, result.output


def test_monitor_cli_clean_when_no_drift(
    tmp_path: Path, isolated_home: Path
) -> None:
    upstream = _make_upstream_repo(tmp_path)
    h = head_hash(upstream)
    assert h is not None
    # status_source mtime well in the past relative to last_synced.at
    report = upstream / "REPORT.md"
    past = time.time() - 86400 * 365  # 1 yr ago
    os.utime(report, (past, past))

    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "wm",
        local_dir=upstream,
        status_sources=["REPORT.md"],
        last_synced_commit=h,
        last_synced_at="2099-01-01T00:00:00+00:00",  # future, so no mtime > at
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "status: clean" in result.output, result.output
    assert "workspace-project changed" not in result.output


def test_monitor_cli_warn_when_local_dir_missing(
    tmp_path: Path, isolated_home: Path
) -> None:
    root = _make_personalos_root(tmp_path)
    _write_onepage(root, "ghost", local_dir=tmp_path / "no-such-dir")

    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    # Bad upstream is WARN-level, not attention-level
    assert "warn:" in result.output
    assert "ghost" in result.output


# ---------- 4. capture --workspace-project ----------


def test_capture_workspace_project_writes_capture_and_inbox(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial = head_hash(upstream)
    assert initial is not None
    (upstream / "B.md").write_text("b\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "new")

    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "watermark",
        local_dir=upstream,
        status_sources=["REPORT.md"],
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["capture", "--root", str(root), "--workspace-project", "watermark"],
    )
    assert result.exit_code == 0, result.output
    assert "captured workspace-project" in result.output

    # capture file
    capture_files = list((root / "capture" / "import").glob("*/workspace-project-watermark.md"))
    assert len(capture_files) == 1
    capture = capture_files[0].read_text(encoding="utf-8")
    assert "kind: raw import" in capture
    assert "type: workspace-project-update" in capture
    assert "Commits since last_synced" in capture
    assert "new" in capture  # commit subject
    assert "REPORT.md" in capture  # status sources section
    assert "## Working tree status" in capture

    # inbox item
    inbox_items = list((root / "system" / "inbox").glob("*-workspace-project-watermark.md"))
    assert len(inbox_items) == 1
    inbox = inbox_items[0].read_text(encoding="utf-8")
    assert "type: workspace-project-update" in inbox
    assert "workspace_project: watermark" in inbox


def test_capture_workspace_project_unknown_name_errors(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_main, ["capture", "--root", str(root), "--workspace-project", "ghost"]
    )
    assert result.exit_code != 0
    assert "no project onepage found" in result.output


def test_capture_workspace_project_missing_upstream_errors(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_onepage(root, "draft", local_dir=None)
    runner = CliRunner()
    result = runner.invoke(
        cli_main, ["capture", "--root", str(root), "--workspace-project", "draft"]
    )
    assert result.exit_code != 0
    assert "no upstream.local_dir" in result.output


def test_capture_input_modes_mutual_exclusion(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    runner = CliRunner()
    # --from-stdin AND --workspace-project both set → error
    src = tmp_path / "src.md"
    src.write_text("hi\n", encoding="utf-8")
    result = runner.invoke(
        cli_main,
        [
            "capture",
            "--root",
            str(root),
            "--from",
            str(src),
            "--workspace-project",
            "x",
        ],
    )
    assert result.exit_code != 0
    assert "exactly one input mode" in result.output


def test_build_capture_markdown_handles_never_synced(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    op = ProjectOnepage(
        path=tmp_path / "onepage.md",
        name="x",
        local_dir=upstream,
        status_sources=["REPORT.md"],
    )
    text = build_capture_markdown(op, "2026-05-06T00:00:00+00:00")
    assert "no last_synced.commit" in text
    assert "showing last 20 commits" in text
    # status sources section still rendered
    assert "### REPORT.md" in text


# ---------- 5. last_synced write-back ----------


def test_update_last_synced_injects_fields(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(root, "x", local_dir=tmp_path / "x")

    ok = update_last_synced(op, commit="deadbeef", at="2026-05-06T01:02:03+00:00")
    assert ok is True

    text = op.read_text(encoding="utf-8")
    assert "last_synced:" in text
    assert "commit: deadbeef" in text
    assert "at: '2026-05-06T01:02:03+00:00'" in text or "at: 2026-05-06T01:02:03+00:00" in text
    # body preserved
    assert "Project description." in text


def test_update_last_synced_skips_non_project_kind(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(root, "x", local_dir=None, kind="preference")
    ok = update_last_synced(op, commit="x", at="y")
    assert ok is False


def test_update_last_synced_overwrites_old_values(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    op = _write_onepage(
        root,
        "x",
        local_dir=tmp_path / "x",
        last_synced_commit="oldhash",
        last_synced_at="2020-01-01T00:00:00+00:00",
    )
    ok = update_last_synced(op, commit="newhash", at="2026-05-06T00:00:00+00:00")
    assert ok is True
    text = op.read_text(encoding="utf-8")
    assert "newhash" in text
    assert "oldhash" not in text


def test_find_modified_project_onepages(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    # init root as git
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "user.email", "t@t")
    op_a = _write_onepage(root, "a", local_dir=upstream)
    op_b = _write_onepage(root, "b", local_dir=upstream)
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")

    # Modify only `a`'s onepage
    op_a.write_text(op_a.read_text(encoding="utf-8") + "\nmore.\n", encoding="utf-8")

    modified = find_modified_project_onepages(root)
    rels = sorted([p.relative_to(root).as_posix() for p in modified])
    assert rels == ["workspace/project/a/onepage.md"]


def test_find_modified_project_onepages_includes_untracked(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@t")
    (root / ".keep").write_text("x", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")

    op = _write_onepage(root, "fresh", local_dir=upstream)
    modified = find_modified_project_onepages(root)
    rels = [p.relative_to(root).as_posix() for p in modified]
    assert "workspace/project/fresh/onepage.md" in rels


def test_pr_done_writes_back_last_synced_on_approve(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial = head_hash(upstream)
    assert initial is not None
    # advance upstream by one commit
    (upstream / "B.md").write_text("b\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "advance")
    new_hash = head_hash(upstream)
    assert new_hash is not None
    assert new_hash != initial

    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@t")
    op = _write_onepage(
        root,
        "watermark",
        local_dir=upstream,
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init os")

    # Simulate user editing the onepage body (the "PR" change)
    op.write_text(
        op.read_text(encoding="utf-8") + "\n## Update\nphase 2 done.\n",
        encoding="utf-8",
    )

    # Create a stub PR dir
    pr_id = "20260506-120000-watermark-update"
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
    assert "updated last_synced" in result.output
    assert "watermark" in result.output

    # Onepage should now have last_synced.commit = new_hash
    text = op.read_text(encoding="utf-8")
    assert new_hash in text
    assert initial not in text  # overwritten

    # PR dir removed
    assert not pr_dir.exists()


def test_pr_done_reject_does_not_update_last_synced(tmp_path: Path) -> None:
    upstream = _make_upstream_repo(tmp_path)
    initial = head_hash(upstream)
    assert initial is not None
    (upstream / "B.md").write_text("b\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "advance")

    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@t")
    op = _write_onepage(
        root,
        "wm",
        local_dir=upstream,
        last_synced_commit=initial,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")

    op.write_text(
        op.read_text(encoding="utf-8") + "\nedits.\n", encoding="utf-8"
    )

    pr_id = "20260506-120100-x"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(
        "---\nkind: pr\ntype: workspace-project-update\nstatus: pending\n---\n\nb\n",
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["pr", "done", pr_id, "--root", str(root), "--reject", "-m", "no"],
    )
    assert result.exit_code == 0, result.output
    assert "updated last_synced" not in result.output

    # Onepage last_synced unchanged
    text = op.read_text(encoding="utf-8")
    assert initial in text


# ---------- end-to-end ----------


def test_e2e_monitor_capture_approve_writes_last_synced(
    tmp_path: Path, isolated_home: Path
) -> None:
    """Full loop: drift detected → capture writes inbox → simulated approve
    injects last_synced.

    This is the headline acceptance criterion: a real upstream repo, a real
    fixture project onepage, the actual CLI commands, and a verifiable
    last_synced field after approve.
    """
    upstream = _make_upstream_repo(tmp_path)
    base_hash = head_hash(upstream)
    assert base_hash is not None

    # Advance upstream
    (upstream / "phase2.md").write_text("phase 2 plan\n", encoding="utf-8")
    _git(upstream, "add", "-A")
    _git(upstream, "commit", "-m", "phase 2")
    new_hash = head_hash(upstream)
    assert new_hash is not None and new_hash != base_hash

    # Build personalOS root as git repo
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "workspace" / "project").mkdir(parents=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "user.email", "t@t")
    op = _write_onepage(
        root,
        "watermark",
        local_dir=upstream,
        status_sources=["REPORT.md"],
        last_synced_commit=base_hash,
        last_synced_at="2026-01-01T00:00:00+00:00",
    )
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init os")

    runner = CliRunner()

    # 1. monitor reports drift
    monitor_result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "workspace-project changed: watermark" in monitor_result.output, monitor_result.output

    # 2. capture creates an inbox + capture file
    cap_result = runner.invoke(
        cli_main,
        ["capture", "--root", str(root), "--workspace-project", "watermark"],
    )
    assert cap_result.exit_code == 0, cap_result.output
    inbox_items = list((root / "system" / "inbox").glob("*-workspace-project-watermark.md"))
    assert len(inbox_items) == 1

    # 3. agent / user modifies onepage body to reflect upstream changes
    op.write_text(
        op.read_text(encoding="utf-8") + "\n## Phase 2\nIn flight.\n",
        encoding="utf-8",
    )

    # 4. create a fake PR dir to simulate the approval handoff
    pr_id = "20260506-130000-watermark-sync"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir()
    (pr_dir / "proposal.md").write_text(
        "---\nkind: pr\ntype: workspace-project-update\nstatus: pending\n---\n\nbody\n",
        encoding="utf-8",
    )

    # 5. forge pr done (= approve) — should inject last_synced
    done_result = runner.invoke(
        cli_main,
        ["pr", "done", pr_id, "--root", str(root), "-m", "phase 2 synced"],
    )
    assert done_result.exit_code == 0, done_result.output
    assert "updated last_synced" in done_result.output

    text = op.read_text(encoding="utf-8")
    assert new_hash in text  # current upstream HEAD recorded
    # body update preserved
    assert "Phase 2" in text
