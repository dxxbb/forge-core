"""Tests for `forge proposal new` (scaffold + CLI)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from click.testing import CliRunner

from forge.cli import main
from forge.proposal.scaffold import (
    derive_pr_id,
    resolve_inbox_arg,
    scaffold_proposal,
)
from forge.proposal.schema import Disposition, has_schema, load_proposal_file


def _seed_personal_os(tmp_path: Path, n_inbox: int = 1) -> Path:
    """Create a minimal personalOS workspace with N inbox files + matching captures."""
    (tmp_path / "system" / "inbox").mkdir(parents=True)
    (tmp_path / "system" / "pr").mkdir(parents=True)
    (tmp_path / "capture" / "import").mkdir(parents=True)
    for i in range(n_inbox):
        ts = f"20260505-18305{i}"
        batch = tmp_path / "capture" / "import" / ts
        batch.mkdir(parents=True)
        (batch / "src.md").write_text(
            "---\n"
            "kind: raw import\n"
            f"source: \"/some/file{i}.md\"\n"
            "captured_at: 2026-05-05T18:30:51+08:00\n"
            "source_size: 1234\n"
            "source_digest: deadbeef00112233\n"
            "status: unreviewed\n"
            "---\n\n"
            f"file{i} body\n",
            encoding="utf-8",
        )
        (tmp_path / "system" / "inbox" / f"{ts}-source-{i}.md").write_text(
            "---\n"
            "kind: inbox\n"
            "type: import-context\n"
            "status: pending\n"
            "source:\n"
            f"  - capture/import/{ts}/\n"
            "---\n\n"
            "# Import context\n\n"
            "## Source summary\n\n"
            f"- /some/file{i}.md (1234 chars)\n\n",
            encoding="utf-8",
        )
    return tmp_path


def test_resolve_inbox_arg_lists_all_when_none(tmp_path):
    root = _seed_personal_os(tmp_path, n_inbox=2)
    files = resolve_inbox_arg(root, None)
    assert len(files) == 2


def test_resolve_inbox_arg_by_id_prefix(tmp_path):
    root = _seed_personal_os(tmp_path, n_inbox=2)
    files = resolve_inbox_arg(root, "20260505-183050")
    assert len(files) == 1
    assert "20260505-183050" in files[0].name


def test_scaffold_creates_pr_dir_and_proposal(tmp_path):
    root = _seed_personal_os(tmp_path, n_inbox=2)
    inbox_files = sorted((root / "system" / "inbox").glob("*.md"))
    out = scaffold_proposal(root, inbox_files, title="my-import",
                             now=datetime(2026, 5, 5, 20, 0, 0).astimezone())
    assert out.exists()
    assert out.name == "proposal.md"
    assert "my-import" in out.parent.name

    p = load_proposal_file(out)
    assert has_schema(p) is True
    assert len(p.items) == 2
    assert p.items[0].disposition is None  # left blank for agent
    assert p.items[0].monitor_info  # populated from inbox source summary
    assert "capture/import/" in p.items[0].extracted
    assert len(p.inbox_sources) == 2


def test_proposal_new_cli_creates_stub(tmp_path):
    root = _seed_personal_os(tmp_path, n_inbox=1)
    runner = CliRunner()
    result = runner.invoke(main, ["proposal", "new", "--root", str(root)])
    assert result.exit_code == 0, result.output
    pr_dirs = list((root / "system" / "pr").iterdir())
    assert len(pr_dirs) == 1
    assert (pr_dirs[0] / "proposal.md").is_file()


def test_proposal_new_cli_errors_on_empty_inbox(tmp_path):
    (tmp_path / "system" / "inbox").mkdir(parents=True)
    (tmp_path / "system" / "pr").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(main, ["proposal", "new", "--root", str(tmp_path)])
    assert result.exit_code != 0
    assert "no pending inbox" in result.output


def test_proposal_new_cli_errors_outside_personal_os(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["proposal", "new", "--root", str(tmp_path)])
    assert result.exit_code != 0
    assert "personalOS" in result.output


def test_derive_pr_id_format():
    pid = derive_pr_id(datetime(2026, 5, 5, 18, 33, 0), "context import")
    assert pid.startswith("20260505-183300-")
    assert "context-import" in pid
