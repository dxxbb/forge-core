"""Forge Run source-discovery completeness at the public CLI boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.claude_memory import format_monitor_lines
from forge.governance.web_clipping import pending_clippings


def _workspace_with_new_codex_memory(
    tmp_path: Path, monkeypatch,
) -> Path:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
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
    assert signal["summary"] == "agent-memory batch: 1 of 1; remaining after batch: 0"


def test_first_memory_baseline_does_not_create_an_empty_run_batch(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    memory_dir = home / ".codex" / "memories"
    memory_dir.mkdir(parents=True)
    (memory_dir / "memory_summary.md").write_text("baseline\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert "0 input(s)" in result.output
    assert "source://agent-memory" not in result.output


def test_forge_run_open_limits_agent_memory_source_batch(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    for index in range(1, 12):
        (rollout_dir / f"new-{index:02d}.md").write_text(
            f"durable learning {index}\n", encoding="utf-8"
        )

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert "agent-memory batch: 10 of 12" in result.output
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    assert signal["source_kind"] == "agent-memory"
    assert signal["handler"] == "bounded-memory-review"
    assert len(signal["batch_items"]) == 10
    assert signal["total_count"] == 12
    assert signal["remaining_count"] == 2


def test_reopening_run_keeps_the_original_memory_batch(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    for index in range(1, 11):
        (rollout_dir / f"new-{index:02d}.md").write_text(
            f"durable learning {index}\n", encoding="utf-8"
        )
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    first = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    first_signal = next(
        item for item in first["inputs"] if item["path"] == "source://agent-memory"
    )

    (rollout_dir / "new-00.md").write_text("arrived later\n", encoding="utf-8")
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0

    reopened = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    reopened_signal = next(
        item for item in reopened["inputs"] if item["path"] == "source://agent-memory"
    )
    assert reopened_signal == first_signal


def test_forge_run_next_returns_one_bounded_memory_contract(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    for index in range(1, 12):
        (rollout_dir / f"new-{index:02d}.md").write_text(
            f"durable learning {index}\n", encoding="utf-8"
        )
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0

    result = runner.invoke(
        cli_main, ["run", "next", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    contract = yaml.safe_load(result.output)
    assert contract["action"] == "classify-source"
    assert contract["input_ref"] == "source://agent-memory"
    assert contract["handler"] == "bounded-memory-review"
    assert contract["batch_size"] == 10
    assert contract["remaining_count"] == 2
    assert contract["constraints"] == [
        "inspect only the listed batch items",
        "do not invoke another workflow without explicit owner request",
        "record exactly one disposition for this batch",
    ]


def test_agent_memory_source_settlement_advances_to_the_next_batch(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    for index in range(1, 12):
        (rollout_dir / f"new-{index:02d}.md").write_text(
            f"durable learning {index}\n", encoding="utf-8"
        )
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
    subprocess.run(["git", "-C", str(workspace), "commit", "-qm", "base"], check=True)
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0
    assert runner.invoke(
        cli_main,
        [
            "run", "disposition", "capture/import/baseline/codex.md",
            "--as", "closed", "--note", "baseline marker only",
            "--root", str(workspace),
        ],
    ).exit_code == 0

    settled = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--as", "closed", "--note", "batch has no durable asset value",
            "--root", str(workspace),
        ],
    )
    assert settled.exit_code == 0, settled.output
    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])
    assert closed.exit_code == 0, closed.output
    assert "本批完成" in closed.output
    assert "剩余来源 2" in closed.output

    reopened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert reopened.exit_code == 0, reopened.output
    assert "agent-memory batch: 2 of 2" in reopened.output


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


def test_forge_run_open_builds_web_clipping_source_batch(tmp_path: Path) -> None:
    workspace = tmp_path / "personalOS"
    clipping_dir = workspace / "capture" / "web clipping"
    clipping_dir.mkdir(parents=True)
    for name in ("alpha", "beta"):
        (clipping_dir / f"{name}.md").write_text(
            f"---\nsource: https://example.com/{name}\ncreated: 2026-08-23\n---\n\n{name}\n",
            encoding="utf-8",
        )

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://web-clipping")
    assert signal["handler"] == "canonical-coverage-check"
    assert signal["summary"] == "web-clipping batch: 2 of 2; remaining after batch: 0"
    assert [item["path"] for item in signal["batch_items"]] == [
        "capture/web clipping/alpha.md",
        "capture/web clipping/beta.md",
    ]
    assert not any(
        item["type"] == "capture-evidence"
        and item["path"].startswith("capture/web clipping/")
        for item in record["inputs"]
    )


def test_web_clipping_source_settlement_records_existing_canonical_sink(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    clipping_dir = workspace / "capture" / "web clipping"
    clipping_dir.mkdir(parents=True)
    clipping_paths = []
    for name in ("alpha", "beta"):
        path = clipping_dir / f"{name}.md"
        path.write_text(
            f"---\nsource: https://example.com/{name}\ncreated: 2026-08-23\n---\n\n{name}\n",
            encoding="utf-8",
        )
        clipping_paths.append(path)
    sink = workspace / "user space" / "writing" / "strategy.md"
    sink.parent.mkdir(parents=True)
    sink.write_text("# Existing synthesis\n", encoding="utf-8")
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
    subprocess.run(["git", "-C", str(workspace), "commit", "-qm", "base"], check=True)
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0
    settled = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://web-clipping",
            "--as", "covered", "--sink", "user space/writing/strategy.md",
            "--root", str(workspace),
        ],
    )
    assert settled.exit_code == 0, settled.output
    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])
    assert closed.exit_code == 0, closed.output
    assert "结算完毕" in closed.output
    for path in clipping_paths:
        clipping = path.read_text(encoding="utf-8")
        assert "synthesized_at:" in clipping
        assert "- user space/writing/strategy.md" in clipping
    assert not pending_clippings(workspace)
    status = subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert status == ""


def test_web_clipping_source_settlement_rejects_sink_outside_workspace(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    clipping_dir = workspace / "capture" / "web clipping"
    clipping_dir.mkdir(parents=True)
    (workspace / "user space").mkdir()
    (clipping_dir / "alpha.md").write_text(
        "---\nsource: https://example.com/alpha\ncreated: 2026-08-23\n---\n\nalpha\n",
        encoding="utf-8",
    )
    (tmp_path / "outside.md").write_text("outside\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0

    settled = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://web-clipping",
            "--as", "covered", "--sink", "user space/../../outside.md",
            "--root", str(workspace),
        ],
    )

    assert settled.exit_code != 0
    assert "existing canonical asset" in str(settled.exception)


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


def test_forge_run_close_reports_machine_checked_dirty_worktree(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
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
    (workspace / "README.md").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(workspace), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(workspace), "commit", "-qm", "base"], check=True)
    (workspace / "unfinished-review.md").write_text("still here\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0

    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])

    assert closed.exit_code == 0, closed.output
    assert "最终状态 complete" in closed.output
    assert "Run 已关闭" in closed.output
    assert "工作树 dirty" in closed.output
    assert "剩余来源 0" in closed.output
