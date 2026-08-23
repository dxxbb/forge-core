"""Forge Run source-discovery completeness at the public CLI boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.claude_memory import format_monitor_lines


def _workspace_with_new_codex_memory(
    tmp_path: Path, monkeypatch,
) -> Path:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    (workspace / "capture" / "import" / "baseline").mkdir(parents=True)
    (workspace / "system" / "inbox").mkdir(parents=True)
    (home / ".codex" / "memories" / "rollout_summaries").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    summary = home / ".codex" / "memories" / "memory_summary.md"
    summary.write_text("baseline\n", encoding="utf-8")
    format_monitor_lines(workspace)
    # A historical corpus capture exists, so only the later delta is actionable.
    (workspace / "capture" / "import" / "baseline" / "codex.md").write_text(
        '---\nsource: "codex-memory-history:all"\n---\n\nCaptured baseline.\n',
        encoding="utf-8",
    )
    (home / ".codex" / "memories" / "rollout_summaries" / "new.md").write_text(
        "new durable learning\n", encoding="utf-8"
    )
    return workspace


def test_forge_run_open_collects_agent_memory_source_signal(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert "source://agent-memory" in result.output
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    frontmatter = run_path.read_text(encoding="utf-8").split("---", 2)[1]
    record = yaml.safe_load(frontmatter)
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    assert signal["type"] == "source-signal"
    assert signal["summary"] == "agent-memory updates: 1 (unseen 1)"


def test_forge_run_status_reports_source_attention(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert '"source_attention": true' in result.output
    assert '"agent-memory": 1' in result.output


def test_forge_run_open_collects_every_monitor_source_category(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (workspace / "system" / "inbox").mkdir(parents=True)
    (workspace / "system" / "inbox" / "pending.md").write_text(
        "---\ntype: import\n---\n\nPending.\n", encoding="utf-8"
    )
    clipping_dir = workspace / "capture" / "web clipping"
    clipping_dir.mkdir(parents=True)
    (clipping_dir / "alpha.md").write_text(
        "---\nsource: https://example.com\ncreated: 2026-08-23\n---\n\nEvidence.\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert "source://pending-inbox" in result.output
    assert "source://web-clipping" in result.output


def test_forge_run_cannot_close_with_unclassified_source_signal(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    runner = CliRunner()
    opened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert opened.exit_code == 0, opened.output
    classified_capture = runner.invoke(
        cli_main,
        [
            "run", "disposition", "capture/import/baseline/codex.md",
            "--as", "closed", "--note", "baseline marker only",
            "--root", str(workspace),
        ],
    )
    assert classified_capture.exit_code == 0, classified_capture.output

    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])

    assert closed.exit_code != 0
    assert "unclassified input(s): source://agent-memory" in str(closed.exception)
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    assert "status: open" in run_path.read_text(encoding="utf-8")


def test_forge_run_reports_deferred_source_signal_as_incomplete(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    # Run close owns a scoped Git commit when the run contains an audit record.
    (workspace / "context build" / "sections").mkdir(parents=True)
    (workspace / "context build" / "config").mkdir(parents=True)
    subprocess.run(["git", "-C", str(workspace), "init", "-q"], check=True)
    subprocess.run(
        ["git", "-C", str(workspace), "config", "user.email", "t@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(workspace), "config", "user.name", "t"], check=True
    )
    subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(workspace), "commit", "-qm", "base"], check=True
    )
    runner = CliRunner()
    assert runner.invoke(cli_main, ["run", "open", "--root", str(workspace)]).exit_code == 0
    assert runner.invoke(
        cli_main,
        [
            "run", "disposition", "capture/import/baseline/codex.md",
            "--as", "closed", "--note", "baseline marker only",
            "--root", str(workspace),
        ],
    ).exit_code == 0

    deferred = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--as", "defer", "--note", "historical corpus needs bounded triage",
            "--root", str(workspace),
        ],
    )

    assert deferred.exit_code == 0, deferred.output
    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])
    assert closed.exit_code == 0, closed.output
    assert "本轮未完成" in closed.output
    assert "顺延来源 1" in closed.output

    reopened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert reopened.exit_code == 0, reopened.output
    assert "source://agent-memory" in reopened.output
