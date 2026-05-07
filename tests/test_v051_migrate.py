"""v0.5.1: legacy onepage schema auto-migration tests.

Cover the v0.5.1 design:

  1. legacy onepage (last_synced w/o dirty_hash) → migrate inline upgrade,
     dirty_hash + dirty_count written, no PR review involved
  2. already v0.5 schema onepage → status="current", skip
  3. multiple onepages mixed legacy + current handled independently
  4. --dry-run probes but writes nothing
  5. onepage without last_synced.commit (never synced) → status="no-baseline",
     skip (capture/sync establishes baseline; not legacy)
  6. monitor surfaces a tail-note when legacy onepages exist; suppresses note
     when none

Plus an end-to-end fixture: write legacy onepage → run migrate-onepage →
verify inline frontmatter contains dirty_hash + dirty_count and that
probe_project now returns clean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.workspace_project import (
    count_legacy_onepages,
    discover_project_onepages,
    head_hash,
    load_project_onepage,
    migrate_legacy_onepage_schema,
    probe_project,
    working_tree_snapshot,
)


# ---------- helpers (mirror test_v050) ----------


def _git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"
    return proc.stdout


def _make_personalos_root(tmp_path: Path, name: str = "os") -> Path:
    root = tmp_path / name
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
    body: str = "Project description.\n",
) -> Path:
    op_dir = workspace / "workspace" / "project" / name
    op_dir.mkdir(parents=True, exist_ok=True)
    op = op_dir / "onepage.md"
    fm_lines = ["---", "kind: project", f"name: {name}", "upstream:"]
    fm_lines.append(f"  local_dir: {local_dir}")
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


# ---------- 1. legacy onepage → upgraded inline ----------


def test_legacy_onepage_gets_dirty_hash_inline(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    # Add uncommitted dev work so dirty_count > 0 and we can verify the right
    # hash gets written.
    (repo / "ver1").mkdir()
    (repo / "ver1" / "main.py").write_text("# code\n", encoding="utf-8")

    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-04-30T00:00:00+00:00",
        # NB: no dirty_hash → legacy v0.4.x schema
    )

    # Sanity: before migrate, onepage has no dirty_hash field
    op_before = load_project_onepage(op_path)
    assert op_before is not None
    assert op_before.has_dirty_hash_field is False

    report = migrate_legacy_onepage_schema(root)
    assert len(report.upgraded) == 1
    assert report.upgraded[0].name == "watermark"
    assert report.upgraded[0].dirty_count >= 1
    assert len(report.upgraded[0].dirty_hash) == 64

    # File should now have dirty_hash + dirty_count inline
    text = op_path.read_text(encoding="utf-8")
    assert "dirty_hash:" in text
    assert "dirty_count:" in text
    # commit must be preserved
    assert head in text

    # Reload — has_dirty_hash_field flips True, hash matches working tree
    op_after = load_project_onepage(op_path)
    assert op_after is not None
    assert op_after.has_dirty_hash_field is True
    expected_hash, expected_count = working_tree_snapshot(repo)
    assert op_after.last_synced_dirty_hash == expected_hash
    assert op_after.last_synced_dirty_count == expected_count

    # No PR was created (this is the whole point — bypass review)
    assert list((root / "system" / "pr").glob("*/proposal.md")) == []
    assert list((root / "system" / "inbox").glob("*.md")) == []


# ---------- 2. v0.5 onepage → skipped as "current" ----------


def test_already_v05_onepage_is_current(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-05-01T00:00:00+00:00",
        last_synced_dirty_hash="",  # explicit dirty_hash field present (clean baseline)
        last_synced_dirty_count=0,
    )
    text_before = op_path.read_text(encoding="utf-8")

    report = migrate_legacy_onepage_schema(root)
    assert len(report.upgraded) == 0
    assert len(report.current) == 1
    assert report.current[0].name == "watermark"

    # File untouched (current → not rewritten)
    text_after = op_path.read_text(encoding="utf-8")
    assert text_before == text_after


# ---------- 3. multiple onepages, mixed states ----------


def test_multiple_onepages_handled_independently(tmp_path: Path) -> None:
    repo_a = _make_upstream_repo(tmp_path / "a", "watermark")
    repo_b = _make_upstream_repo(tmp_path / "b", "forge")
    head_a = head_hash(repo_a)
    head_b = head_hash(repo_b)
    assert head_a is not None and head_b is not None

    root = _make_personalos_root(tmp_path)
    # legacy
    _write_onepage(
        root,
        "watermark",
        local_dir=repo_a,
        last_synced_commit=head_a,
        last_synced_at="2026-04-30T00:00:00+00:00",
    )
    # already v0.5
    _write_onepage(
        root,
        "forge",
        local_dir=repo_b,
        last_synced_commit=head_b,
        last_synced_at="2026-05-01T00:00:00+00:00",
        last_synced_dirty_hash="",
        last_synced_dirty_count=0,
    )
    # never synced
    _write_onepage(
        root,
        "newproject",
        local_dir=tmp_path / "c",   # path doesn't exist; that's fine — no last_synced.commit, skipped early
    )

    report = migrate_legacy_onepage_schema(root)
    assert len(report.upgraded) == 1
    assert report.upgraded[0].name == "watermark"
    assert len(report.current) == 1
    assert report.current[0].name == "forge"
    assert len(report.no_baseline) == 1
    assert report.no_baseline[0].name == "newproject"
    assert len(report.warns) == 0


# ---------- 4. --dry-run writes nothing ----------


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-04-30T00:00:00+00:00",
    )
    text_before = op_path.read_text(encoding="utf-8")

    report = migrate_legacy_onepage_schema(root, dry_run=True)
    assert len(report.upgraded) == 1
    assert "dirty_hash" not in text_before  # sanity

    # File untouched after dry-run
    text_after = op_path.read_text(encoding="utf-8")
    assert text_before == text_after

    # Reload onepage — still legacy (no dirty_hash field)
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.has_dirty_hash_field is False


# ---------- 5. never-synced onepage → no-baseline (not legacy) ----------


def test_never_synced_onepage_classified_no_baseline(tmp_path: Path) -> None:
    """A onepage with upstream but no last_synced.commit isn't legacy — capture
    will establish a v0.5 baseline naturally. We must not fabricate one here."""
    repo = _make_upstream_repo(tmp_path)
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        # no last_synced
    )
    text_before = op_path.read_text(encoding="utf-8")

    report = migrate_legacy_onepage_schema(root)
    assert len(report.upgraded) == 0
    assert len(report.no_baseline) == 1
    assert report.no_baseline[0].name == "watermark"

    text_after = op_path.read_text(encoding="utf-8")
    assert text_before == text_after  # untouched

    # count_legacy_onepages should NOT include never-synced
    assert count_legacy_onepages(root) == 0


# ---------- 6. monitor surfaces tail-note when legacy onepages exist ----------


def test_monitor_notes_legacy_onepages(tmp_path: Path, isolated_home: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    # legacy onepage
    _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2099-01-01T00:00:00+00:00",  # far future → no staleness/drift
    )

    runner = CliRunner()
    r = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert r.exit_code == 0, r.output
    # Working tree clean + last_synced.at far future + legacy schema → status:
    # clean (legacy is not "drift"), but monitor must surface the migrate hint
    assert "status: clean" in r.output, r.output
    assert "1 project onepage" in r.output
    assert "legacy schema" in r.output
    assert "forge migrate-onepage" in r.output


def test_monitor_omits_note_when_no_legacy(tmp_path: Path, isolated_home: Path) -> None:
    """No legacy onepages → no migrate hint. Belt and suspenders for #6."""
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
        last_synced_dirty_hash="",  # v0.5 baseline
        last_synced_dirty_count=0,
    )

    runner = CliRunner()
    r = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert r.exit_code == 0, r.output
    assert "status: clean" in r.output
    assert "legacy schema" not in r.output
    assert "forge migrate-onepage" not in r.output


# ---------- 7. CLI dry-run prints summary, no write ----------


def test_cli_dry_run_prints_summary(tmp_path: Path, isolated_home: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-04-30T00:00:00+00:00",
    )
    text_before = op_path.read_text(encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(
        cli_main,
        ["migrate-onepage", "--root", str(root), "--dry-run"],
    )
    assert r.exit_code == 0, r.output
    assert "[dry-run]" in r.output
    assert "would be:" in r.output
    assert "upgraded=1" in r.output

    # File still legacy
    assert text_before == op_path.read_text(encoding="utf-8")


# ---------- 8. CLI verbose prints per-onepage line ----------


def test_cli_verbose_prints_each_onepage(tmp_path: Path, isolated_home: Path) -> None:
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    root = _make_personalos_root(tmp_path)
    _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-04-30T00:00:00+00:00",
    )
    _write_onepage(
        root,
        "forge",
        local_dir=tmp_path / "nope",  # never synced, no last_synced
    )

    runner = CliRunner()
    r = runner.invoke(
        cli_main,
        ["migrate-onepage", "--root", str(root), "--verbose"],
    )
    assert r.exit_code == 0, r.output
    assert "upgraded:" in r.output
    assert "watermark" in r.output
    assert "no-baseline:" in r.output
    assert "forge" in r.output
    assert "done:" in r.output


# ---------- 9. e2e: legacy → migrate → probe clean ----------


def test_e2e_migrate_legacy_then_probe_clean(tmp_path: Path, isolated_home: Path) -> None:
    """End-to-end fixture exercise:

    1. Create personalOS workspace + external git project + legacy onepage
       (last_synced.commit set, no dirty_hash field).
    2. Run `forge migrate-onepage` (no PR review).
    3. Reload onepage — has_dirty_hash_field flips True, hash matches the
       upstream working tree snapshot.
    4. probe_project on the migrated onepage returns no dirty_drift (the
       baseline now matches reality).
    5. No PR / inbox artifacts exist (no review needed).
    """
    repo = _make_upstream_repo(tmp_path)
    head = head_hash(repo)
    assert head is not None
    # Mimic real watermark situation: has uncommitted dev work
    (repo / "draft.md").write_text("# draft\n", encoding="utf-8")

    root = _make_personalos_root(tmp_path)
    op_path = _write_onepage(
        root,
        "watermark",
        local_dir=repo,
        last_synced_commit=head,
        last_synced_at="2026-04-30T00:00:00+00:00",
    )

    # Step 1 sanity: monitor reports legacy + dirty drift (no baseline)
    runner = CliRunner()
    r0 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    # workspace-project drift is surfaced as `status: attention` in the body
    # (exit_code stays 0; only doctor failures hard-fail). Assert on output.
    assert "status: attention" in r0.output
    assert "working tree drift" in r0.output
    assert "legacy onepage" in r0.output
    # And surfaces the migrate hint
    assert "forge migrate-onepage" in r0.output

    # Step 2: migrate
    r1 = runner.invoke(cli_main, ["migrate-onepage", "--root", str(root)])
    assert r1.exit_code == 0, r1.output
    assert "upgraded watermark" in r1.output
    assert "done:" in r1.output

    # Step 3: file mutated inline
    text = op_path.read_text(encoding="utf-8")
    assert "dirty_hash:" in text
    assert "dirty_count:" in text
    op = load_project_onepage(op_path)
    assert op is not None
    assert op.has_dirty_hash_field is True
    expected_hash, expected_count = working_tree_snapshot(repo)
    assert op.last_synced_dirty_hash == expected_hash
    assert op.last_synced_dirty_count == expected_count
    assert op.last_synced_commit == head  # commit preserved

    # Step 4: probe → clean
    status = probe_project(op)
    assert status.commit_drift == ""
    assert status.dirty_drift == ""
    assert status.issue == ""

    # Step 5: monitor now clean, no migrate hint
    r2 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert r2.exit_code == 0, r2.output
    assert "status: clean" in r2.output
    assert "forge migrate-onepage" not in r2.output

    # No PR / inbox artifacts created (this is the whole point)
    assert list((root / "system" / "pr").glob("*/proposal.md")) == []
    assert list((root / "system" / "inbox").glob("*.md")) == []
