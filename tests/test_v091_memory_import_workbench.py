from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from forge.cli import main
from forge.proposal.workbench import extract_workbench_items


def _make_root(tmp_path: Path) -> Path:
    (tmp_path / "capture" / "import" / "20260522-000000").mkdir(parents=True)
    (tmp_path / "system" / "inbox").mkdir(parents=True)
    return tmp_path


def test_extract_workbench_items_from_task_groups() -> None:
    text = """# Task Group: personalOS documentation consolidation

body

# Task Group: project workspace current status

body
"""
    items = extract_workbench_items(text, source_label="capture/import/x.md")
    assert [i.id for i in items] == ["01", "02"]
    assert items[0].title == "personalOS documentation consolidation"
    assert items[0].initial_domain == "workflow / writing"
    assert items[1].initial_domain == "project"


def test_extract_workbench_items_falls_back_to_single_capture_item() -> None:
    items = extract_workbench_items("plain capture", source_label="capture/import/x.md")
    assert len(items) == 1
    assert items[0].id == "01"
    assert items[0].title == "capture/import/x.md"


def test_proposal_workbench_scaffolds_resumable_item_list(tmp_path: Path) -> None:
    root = _make_root(tmp_path)
    capture = root / "capture" / "import" / "20260522-000000" / "codex-memory-history.md"
    capture.write_text(
        "---\n"
        "kind: raw import\n"
        "source: codex-memory-history:all\n"
        "source_files: 2\n"
        "---\n\n"
        "# Task Group: personalOS documentation consolidation\n\n"
        "# Task Group: registration naming\n",
        encoding="utf-8",
    )
    inbox = root / "system" / "inbox" / "20260522-codex-memory-history.md"
    inbox.write_text(
        "---\n"
        "kind: inbox\n"
        "type: import-context\n"
        "status: pending\n"
        "source:\n"
        "  - capture/import/20260522-000000/\n"
        "---\n\n"
        "# Import context\n\n"
        "## Source summary\n\n"
        "- Codex memory/history (all, 2 files, 100 chars)\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        main,
        [
            "proposal",
            "workbench",
            "--root",
            str(root),
            "--inbox",
            inbox.name,
            "--title",
            "codex-memory-history-import",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "created staged workbench:" in result.output
    workbenches = list((root / "system" / "pr").glob("*/workbench.md"))
    assert len(workbenches) == 1
    text = workbenches[0].read_text(encoding="utf-8")
    assert "kind: memory-import-workbench" in text
    assert "final_pr_ready: false" in text
    assert "| 01 | personalOS documentation consolidation | workflow / writing | A | untriaged |" in text
    assert "| 02 | registration naming | policy / private planning | A | untriaged |" in text
    assert "`canonical_sink_status`" in text
    assert "`live_verify_required`" in text
    assert "Cross-review" in text
    # The diffable-proposal contract: APPLY items must carry a concrete patch,
    # not only prose, so the review portal can render before -> after.
    assert "`proposed_patch_target`" in text
    assert "- proposed_patch_target:" in text
    assert "- proposed_patch_anchor:" in text
    assert "- proposed_patch_text:" in text
