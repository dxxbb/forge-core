"""Forge Run source-discovery completeness at the public CLI boundary."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import yaml
import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.claude_memory import build_run_source_signal, format_monitor_lines
from forge.governance.claude_memory import (
    MemoryState,
    discover_review_units,
    load_state,
    save_state,
)
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


def test_agent_memory_batch_uses_bounded_task_group_review_units(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    memories = home / ".codex" / "memories"
    memories.mkdir(parents=True)
    groups = "".join(
        f"# Task Group: Topic {index:02d}\n\nscope: bounded {index}\n\n"
        for index in range(12)
    )
    (memories / "MEMORY.md").write_text(groups, encoding="utf-8")
    (memories / "raw_memories.md").write_text("raw aggregate\n", encoding="utf-8")
    archived = home / ".codex" / "archived_sessions"
    archived.mkdir(parents=True)
    (archived / "huge.jsonl").write_text("raw session\n", encoding="utf-8")

    status_result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )
    status = yaml.safe_load(status_result.output)
    assert status["source_diagnostics"][0]["eligible_review_units"] == 12
    assert status["source_diagnostics"][0]["excluded_source_counts"] == {
        "aggregate-memory-files": 1,
        "archived-sessions": 1,
    }

    result = CliRunner().invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    assert signal["total_count"] == 12
    assert signal["batch_size"] == 10
    assert signal["remaining_count"] == 2
    assert all(item["unit_kind"] == "codex-task-group" for item in signal["batch_items"])
    assert signal["excluded_source_counts"] == {
        "aggregate-memory-files": 1,
        "archived-sessions": 1,
    }


def test_codex_review_units_split_task_group_by_task_and_keep_tagged_context(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    memories = home / ".codex" / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        """# Task Group: Mixed project work

scope: shared scope
applies_to: shared project

## Task 1: Fix release receipt

### rollout_summary_files

- rollout-a.md (thread_id=thread-a)

### keywords

- release, receipt

## Task 2: Explain a medical answer

### rollout_summary_files

- rollout-b.md (thread_id=thread-b)

### keywords

- medical, explanation

## User preferences

- Release status must distinguish local and deployed. [Task 1]
- Medical answers should cite sources for this request. [Task 2]

## Reusable knowledge

- Verify the actual effect. [Task 1][Task 2]
""",
        encoding="utf-8",
    )

    signal = build_run_source_signal(workspace)

    assert signal is not None
    assert signal["total_count"] == 2
    first, second = signal["batch_items"]
    assert first["unit_kind"] == second["unit_kind"] == "codex-task"
    assert first["title"].endswith("Task 1: Fix release receipt")
    assert second["title"].endswith("Task 2: Explain a medical answer")
    assert "rollout-a.md" in first["content"]
    assert "Release status must distinguish" in first["content"]
    assert "Medical answers should cite" not in first["content"]
    assert "rollout-b.md" in second["content"]
    assert "Medical answers should cite" in second["content"]
    assert "Release status must distinguish" not in second["content"]
    assert "Verify the actual effect" in first["content"]
    assert "Verify the actual effect" in second["content"]


def test_codex_unassigned_group_content_becomes_a_summary_review_unit(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    memories = home / ".codex" / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        """# Task Group: Mixed project work

scope: shared scope

## Task 1: Fix release receipt

### keywords

- release, receipt

## User preferences

- Release status must distinguish local and deployed. [Task 1]
- This group-level preference was not assigned to a Task.

## Reusable knowledge

This section-level note is also not assigned.

- Verify the actual effect. [Task 1]
""",
        encoding="utf-8",
    )

    signal = build_run_source_signal(workspace)

    assert signal is not None
    assert signal["total_count"] == 2
    task, summary = signal["batch_items"]
    assert task["unit_kind"] == "codex-task"
    assert summary["unit_kind"] == "codex-task-group-summary"
    assert summary["title"].endswith("Group summary")
    assert "This group-level preference was not assigned" in summary["content"]
    assert "This section-level note is also not assigned" in summary["content"]
    assert "Release status must distinguish" not in summary["content"]
    assert "Verify the actual effect" not in summary["content"]


def test_single_task_group_inherits_its_exact_legacy_group_checkpoint(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    memories = home / ".codex" / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        """# Task Group: One task only

scope: bounded

## Task 1: The only task

### keywords

- one

## Reusable knowledge

- Only this task. [Task 1]
""",
        encoding="utf-8",
    )
    [unit], _ = discover_review_units(workspace)
    assert unit.legacy_parent_id
    assert unit.legacy_parent_sha256
    save_state(
        workspace,
        MemoryState(
            settled_units={
                unit.legacy_parent_id: {
                    "hash": unit.legacy_parent_sha256,
                    "size": 1,
                    "seen_at": "2026-08-23T00:00:00+00:00",
                }
            }
        ),
    )

    assert build_run_source_signal(workspace) is None
    migrated = load_state(workspace)
    assert migrated is not None
    assert migrated.settled_units[unit.id]["hash"] == unit.sha256


def test_agent_memory_source_batch_is_bounded_by_bytes_not_only_unit_count(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    workspace = tmp_path / "personalOS"
    workspace.mkdir()
    monkeypatch.setenv("HOME", str(home))
    memories = home / ".codex" / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text(
        "# Task Group: Alpha\n\n" + ("a" * 50) + "\n\n"
        "# Task Group: Beta\n\n" + ("b" * 50) + "\n",
        encoding="utf-8",
    )

    signal = build_run_source_signal(workspace, limit=10, byte_limit=100)

    assert signal is not None
    assert signal["batch_size"] == 1
    assert signal["remaining_count"] == 1
    assert signal["batch_bytes"] <= signal["byte_limit"] == 100


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


def test_forge_run_next_returns_background_review_slice_with_owner_facing_projection(
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
    assert contract["action"] == "classify-source-items"
    assert contract["input_ref"] == "source://agent-memory"
    assert contract["handler"] == "bounded-memory-review"
    assert contract["source_batch_size"] == 10
    assert contract["remaining_in_batch"] == 10
    assert len(contract["review_units"]) == 3
    assert all(unit["content"] for unit in contract["review_units"])
    assert "review_unit" not in contract
    assert contract["remaining_count"] == 2
    assert contract["owner_visibility"] == "silent"
    assert contract["owner_facing_projection"] == {
        "default": "silent",
        "heartbeat_if_required": "Forge 仍在后台处理；当前不需要你决定。",
        "heartbeat_must_be_verbatim": True,
    }
    assert contract["constraints"] == [
        "inspect only the listed Review Units and their evidence pointers",
        "derive event ids from the underlying thread/session/source event, not from file paths; multiple pointers to the same event share one id",
        "source context must describe what actually happened; a hypothetical harm is not evidence of a problem",
        "a request made for this one task is not an owner-directed long-term requirement",
        "high-risk is a priority signal, not a promotion ground; deterministically fix an actual control defect as one-off, observe only an actual unresolved signal, and close hypothetical risk",
        "observation is not the default for unpromoted material; require an owner correction, observed failure, unresolved conflict, or owner-deferred candidate plus source context, a concrete repeat test, and a route gap",
        "successful one-off research, reusable task knowledge, and project-specific decisions go to covered, volatile-state, a proper project sink, or closed unless the owner explicitly requested long-term promotion",
        "do not read or search user space/private, secret config, credentials, or other protected paths while looking for a sink",
        "covered requires a tracked authoritative canonical asset inside the current workspace; runtime projections, scratch, capture, system files, private paths, and external repositories do not qualify",
        "volatile-state requires a real current Run state write or run ledger receipt; an unchanged existing state file is covered, not volatile-state",
        "before creating a candidate, compare related assets and explain why an owner-governed durable asset is the right sink instead of code, tests, volatile state, a reusable skill, platform baseline, or observation",
        "do not invoke another workflow without explicit owner request",
        "record exactly one disposition for each of these 3 Review Units using --item",
    ]


@pytest.mark.parametrize(
    "sink_kind",
    ["outside", "private", "runtime-projection", "scratch", "capture"],
)
def test_covered_disposition_requires_an_authoritative_canonical_receipt(
    tmp_path: Path, monkeypatch, sink_kind: str,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    sink_by_kind = {
        "outside": tmp_path / "external-repo" / "notes.md",
        "private": workspace / "user space" / "private" / "health.md",
        "runtime-projection": (
            workspace / "context build" / "runtime" / "agents-md" / "AGENTS.md"
        ),
        "scratch": workspace / "workbench" / "project" / "demo" / "scratch" / "note.md",
        "capture": workspace / "capture" / "manual-note.md",
    }
    sink = sink_by_kind[sink_kind]
    sink.parent.mkdir(parents=True, exist_ok=True)
    sink.write_text("not an authoritative canonical sink\n", encoding="utf-8")
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
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    item_ref = signal["batch_items"][0]["unit_id"]

    result = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "covered",
            "--sink", str(sink),
            "--coverage-claim", "fixture claim",
            "--coverage-locator", "authoritative canonical sink",
            "--coverage-excerpt", "authoritative canonical sink",
            "--root", str(workspace),
        ],
    )

    assert result.exit_code != 0
    assert "authoritative canonical asset" in str(result.exception)


def test_covered_receipt_proves_claim_with_real_excerpt_in_dynamic_canonical_root(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    sink = workspace / "medical knowledge base" / "topic" / "sampling.md"
    sink.parent.mkdir(parents=True)
    sink.write_text(
        "# 取样\n\n自然咳痰困难时，诱导痰应由医疗机构完成。\n",
        encoding="utf-8",
    )
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
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    item_ref = signal["batch_items"][0]["unit_id"]

    missing = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "covered",
            "--sink", "medical knowledge base/topic/sampling.md",
            "--root", str(workspace),
        ],
    )
    assert missing.exit_code != 0
    assert "coverage claim" in str(missing.exception)

    absent_excerpt = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "covered",
            "--sink", "medical knowledge base/topic/sampling.md",
            "--coverage-claim", "诱导痰不是默认居家动作",
            "--coverage-locator", "# 取样",
            "--coverage-excerpt", "这段并不存在",
            "--root", str(workspace),
        ],
    )
    assert absent_excerpt.exit_code != 0
    assert "coverage excerpt" in str(absent_excerpt.exception)

    accepted = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "covered",
            "--sink", "medical knowledge base/topic/sampling.md",
            "--coverage-claim", "诱导痰不是默认居家动作",
            "--coverage-locator", "# 取样",
            "--coverage-excerpt", "诱导痰应由医疗机构完成",
            "--root", str(workspace),
        ],
    )

    assert accepted.exit_code == 0, accepted.output
    receipt = yaml.safe_load(accepted.output)
    assert receipt["sink"] == "medical knowledge base/topic/sampling.md"
    assert receipt["coverage_claim"] == "诱导痰不是默认居家动作"
    assert receipt["coverage_locator"] == "# 取样"
    assert receipt["coverage_excerpt"] == "诱导痰应由医疗机构完成"


def test_volatile_state_disposition_requires_a_current_run_write_receipt(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    sink = workspace / "workbench" / "project" / "demo" / "onepage.md"
    sink.parent.mkdir(parents=True)
    sink.write_text("# Demo\n\nStatus: unchanged\n", encoding="utf-8")
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
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    item_ref = signal["batch_items"][0]["unit_id"]

    result = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "volatile-state",
            "--sink", "workbench/project/demo/onepage.md",
            "--root", str(workspace),
        ],
    )

    assert result.exit_code != 0
    assert "current Run write receipt" in str(result.exception)

    sink.write_text("# Demo\n\nStatus: updated during this Run\n", encoding="utf-8")
    accepted = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", item_ref,
            "--as", "volatile-state",
            "--sink", "workbench/project/demo/onepage.md",
            "--root", str(workspace),
        ],
    )

    assert accepted.exit_code == 0, accepted.output
    receipt = yaml.safe_load(accepted.output)
    assert receipt["sink"] == "workbench/project/demo/onepage.md"
    assert receipt["run_owned_write"] is True
    assert len(receipt["sink_digest"]) == 64

    sink.write_text("# Demo\n\nStatus: changed after receipt\n", encoding="utf-8")
    stale = runner.invoke(
        cli_main, ["run", "close", "--root", str(workspace)]
    )
    assert stale.exit_code != 0
    assert "volatile-state sink drifted" in str(stale.exception)

    sink.write_text("# Demo\n\nStatus: updated during this Run\n", encoding="utf-8")
    closed = runner.invoke(
        cli_main, ["run", "close", "--root", str(workspace)]
    )
    assert closed.exit_code == 0, closed.output
    assert subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""
    changed_files = subprocess.run(
        ["git", "-C", str(workspace), "show", "--pretty=", "--name-only", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "workbench/project/demo/onepage.md" in changed_files


def test_volatile_state_rejects_a_sink_that_was_dirty_before_run_opened(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    sink = workspace / "workbench" / "project" / "demo" / "onepage.md"
    sink.parent.mkdir(parents=True)
    sink.write_text("# Demo\n\nStatus: base\n", encoding="utf-8")
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
    sink.write_text("# Demo\n\nStatus: user WIP before Run\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")

    result = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", signal["batch_items"][0]["unit_id"],
            "--as", "volatile-state",
            "--sink", "workbench/project/demo/onepage.md",
            "--root", str(workspace),
        ],
    )

    assert result.exit_code != 0
    assert "dirty before this Run opened" in str(result.exception)


def test_run_owned_sink_uses_the_latest_receipt_across_review_units(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    (rollout_dir / "second.md").write_text(
        "second durable learning\n", encoding="utf-8"
    )
    sink = workspace / "workbench" / "project" / "demo" / "onepage.md"
    sink.parent.mkdir(parents=True)
    sink.write_text("# Demo\n\nStatus: base\n", encoding="utf-8")
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
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    first, second = signal["batch_items"]

    sink.write_text("# Demo\n\nStatus: first unit\n", encoding="utf-8")
    first_result = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", first["unit_id"],
            "--as", "volatile-state",
            "--sink", "workbench/project/demo/onepage.md",
            "--note", "first semantic update",
            "--root", str(workspace),
        ],
    )
    assert first_result.exit_code == 0, first_result.output

    sink.write_text("# Demo\n\nStatus: first and second units\n", encoding="utf-8")
    second_result = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", second["unit_id"],
            "--as", "volatile-state",
            "--sink", "workbench/project/demo/onepage.md",
            "--note", "second semantic update",
            "--root", str(workspace),
        ],
    )
    assert second_result.exit_code == 0, second_result.output

    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])

    assert closed.exit_code == 0, closed.output
    persisted = yaml.safe_load(
        run_path.read_text(encoding="utf-8").split("---", 2)[1]
    )
    receipts = [
        disposition
        for disposition in persisted["dispositions"]
        if disposition.get("sink") == "workbench/project/demo/onepage.md"
    ]
    assert [receipt["note"] for receipt in receipts] == [
        "first semantic update",
        "second semantic update",
    ]
    assert receipts[0]["sink_digest"] != receipts[1]["sink_digest"]


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
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    record = yaml.safe_load(run_path.read_text(encoding="utf-8").split("---", 2)[1])
    signal = next(i for i in record["inputs"] if i["path"] == "source://agent-memory")
    for item in signal["batch_items"]:
        settled = runner.invoke(
            cli_main,
            [
                "run", "disposition", "source://agent-memory",
                "--item", item["unit_id"],
                "--as", "closed", "--note", "no durable asset value",
                "--root", str(workspace),
            ],
        )
        assert settled.exit_code == 0, settled.output
    closed = runner.invoke(cli_main, ["run", "close", "--root", str(workspace)])
    assert closed.exit_code == 0, closed.output
    assert "本批完成" in closed.output
    assert "剩余可筛选单元 2" in closed.output
    assert "候选结论 未知（2 个可筛选单元尚未处理）" in closed.output
    persisted = yaml.safe_load(
        run_path.read_text(encoding="utf-8").split("---", 2)[1]
    )
    assert persisted["report"]["remaining_sources"] == 2
    assert persisted["report"]["candidate_conclusion"] == "unknown"
    assert subprocess.run(
        ["git", "-C", str(workspace), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""

    reopened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert reopened.exit_code == 0, reopened.output
    assert "agent-memory batch: 2 of 2" in reopened.output


def test_source_batch_requires_one_disposition_per_review_unit(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    (rollout_dir / "second.md").write_text(
        "second durable learning\n", encoding="utf-8"
    )
    runner = CliRunner()
    opened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert opened.exit_code == 0, opened.output

    parent = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--as", "closed", "--note", "too coarse",
            "--root", str(workspace),
        ],
    )
    assert parent.exit_code != 0
    assert "requires --item" in str(parent.exception)

    first_contract = runner.invoke(
        cli_main, ["run", "next", "--root", str(workspace)]
    )
    assert first_contract.exit_code == 0, first_contract.output
    first = yaml.safe_load(first_contract.output)
    assert first["action"] == "classify-source-items"
    assert first["remaining_in_batch"] == 2
    first_item = first["review_units"][0]["unit_id"]

    settled = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", first_item,
            "--as", "closed", "--note", "no generalizable value",
            "--root", str(workspace),
        ],
    )
    assert settled.exit_code == 0, settled.output

    second_contract = runner.invoke(
        cli_main, ["run", "next", "--root", str(workspace)]
    )
    second = yaml.safe_load(second_contract.output)
    assert second["action"] == "classify-source-item"
    assert second["remaining_in_batch"] == 1
    assert second["review_unit"]["unit_id"] != first_item


def test_identical_source_contents_still_require_distinct_review_unit_outcomes(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    rollout_dir = tmp_path / "home" / ".codex" / "memories" / "rollout_summaries"
    (rollout_dir / "same.md").write_text(
        "new durable learning\n", encoding="utf-8"
    )
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0
    first_contract = yaml.safe_load(
        runner.invoke(cli_main, ["run", "next", "--root", str(workspace)]).output
    )
    first_path = first_contract["review_units"][0]["path"]

    settled = runner.invoke(
        cli_main,
        [
            "run", "disposition", "source://agent-memory",
            "--item", first_path,
            "--as", "closed", "--note", "duplicate raw evidence",
            "--root", str(workspace),
        ],
    )
    assert settled.exit_code == 0, settled.output

    second = yaml.safe_load(
        runner.invoke(cli_main, ["run", "next", "--root", str(workspace)]).output
    )
    assert second["action"] == "classify-source-item"
    assert second["remaining_in_batch"] == 1
    assert second["review_unit"]["path"] != first_path


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


def test_candidate_conclusion_is_unknown_while_review_units_remain(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)

    result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert '"selection_coverage": "incomplete"' in result.output
    assert '"candidate_conclusion": "unknown"' in result.output
    assert '"unprocessed_review_units": 1' in result.output


def test_candidate_conclusion_is_none_only_after_selection_is_complete(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    workspace.mkdir()

    result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    assert '"selection_coverage": "complete"' in result.output
    assert '"candidate_conclusion": "none"' in result.output
    assert '"unprocessed_review_units": 0' in result.output


def test_candidate_conclusion_is_unknown_while_capture_evidence_remains(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    capture = workspace / "capture" / "notes"
    capture.mkdir(parents=True)
    (capture / "unreviewed.md").write_text("new evidence\n", encoding="utf-8")

    result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    status = yaml.safe_load(result.output)
    assert status["selection_coverage"] == "incomplete"
    assert status["candidate_conclusion"] == "unknown"
    assert status["unprocessed_review_units"] == 1
    assert status["unprocessed_source_units"] == 0
    assert status["unprocessed_capture_evidence"] == 1


def test_identical_capture_contents_remain_distinct_review_units(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    capture = workspace / "capture" / "notes"
    capture.mkdir(parents=True)
    for name in ("alpha.md", "beta.md"):
        (capture / name).write_text("same evidence\n", encoding="utf-8")
    runner = CliRunner()
    assert runner.invoke(
        cli_main, ["run", "open", "--root", str(workspace)]
    ).exit_code == 0

    first = yaml.safe_load(
        runner.invoke(
            cli_main, ["run", "next", "--root", str(workspace)]
        ).output
    )
    assert first["input_ref"] == "capture/notes/alpha.md"
    disposition = runner.invoke(
        cli_main,
        [
            "run", "disposition", first["input_ref"],
            "--as", "closed", "--note", "first copy classified",
            "--root", str(workspace),
        ],
    )
    assert disposition.exit_code == 0, disposition.output

    second = yaml.safe_load(
        runner.invoke(
            cli_main, ["run", "next", "--root", str(workspace)]
        ).output
    )
    assert second["action"] == "classify-evidence"
    assert second["input_ref"] == "capture/notes/beta.md"


def test_closed_legacy_run_grandfathers_its_capture_fingerprints(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    capture = workspace / "capture" / "notes"
    capture.mkdir(parents=True)
    evidence = capture / "historical.md"
    evidence.write_text("already settled by old Run\n", encoding="utf-8")
    digest = hashlib.sha1(evidence.read_bytes()).hexdigest()[:16]
    run_dir = workspace / "system" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "run-20260101-000000.md").write_text(
        "---\n"
        "kind: forge-run\n"
        "id: run-20260101-000000\n"
        "status: closed\n"
        "opened_at: '2026-01-01T00:00:00+08:00'\n"
        "closed_at: '2026-01-01T00:01:00+08:00'\n"
        "inputs:\n"
        "- path: capture/notes/historical.md\n"
        f"  digest: {digest}\n"
        "---\n\n# Legacy Run\n",
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli_main, ["run", "status", "--root", str(workspace)]
    )

    assert result.exit_code == 0, result.output
    status = yaml.safe_load(result.output)
    assert status["selection_coverage"] == "complete"
    assert status["candidate_conclusion"] == "none"
    assert status["unprocessed_capture_evidence"] == 0


def test_close_owner_facing_projection_uses_global_inventory_when_capture_arrives(
    tmp_path: Path, monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    workspace = tmp_path / "personalOS"
    capture = workspace / "capture" / "notes"
    capture.mkdir(parents=True)
    first = capture / "first.md"
    first.write_text("first evidence\n", encoding="utf-8")
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
    disposition = runner.invoke(
        cli_main,
        [
            "run", "disposition", "capture/notes/first.md",
            "--as", "closed", "--note", "no durable value",
            "--root", str(workspace),
        ],
    )
    assert disposition.exit_code == 0, disposition.output
    (capture / "second.md").write_text("arrived after open\n", encoding="utf-8")

    closed = runner.invoke(
        cli_main, ["run", "close", "--root", str(workspace)]
    )

    assert closed.exit_code == 0, closed.output
    assert "本批完成" in closed.output
    assert "候选结论 未知（1 个可筛选单元尚未处理）" in closed.output
    assert "最终状态 batch-complete" in closed.output
    owner_summary = next(
        line.removeprefix("OWNER-FACING SUMMARY: ")
        for line in closed.output.splitlines()
        if line.startswith("OWNER-FACING SUMMARY: ")
    )
    assert "Forge 本批已处理并关闭" in owner_summary
    assert "final_state=batch-complete" in owner_summary
    assert "Run=closed" in owner_summary
    assert "Selection Coverage=incomplete" in owner_summary
    assert "Candidate Conclusion=unknown" in owner_summary
    assert "剩余可筛选单元=1" in owner_summary
    assert "Forge 完成" not in owner_summary
    [run_path] = (workspace / "system" / "run").glob("run-*.md")
    report = yaml.safe_load(
        run_path.read_text(encoding="utf-8").split("---", 2)[1]
    )["report"]
    assert report["candidate_conclusion"] == "unknown"
    assert report["unprocessed_review_units"] == 1
    assert report["unprocessed_capture_evidence"] == 1


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
    for path in clipping_paths:
        settled = runner.invoke(
            cli_main,
            [
                "run", "disposition", "source://web-clipping",
                "--item", path.relative_to(workspace).as_posix(),
                "--as", "covered", "--sink", "user space/writing/strategy.md",
                "--coverage-claim", "clipping material is already synthesized",
                "--coverage-locator", "# Existing synthesis",
                "--coverage-excerpt", "Existing synthesis",
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
            "--item", "capture/web clipping/alpha.md",
            "--as", "covered", "--sink", "user space/../../outside.md",
            "--coverage-claim", "fixture claim",
            "--coverage-locator", "outside",
            "--coverage-excerpt", "outside",
            "--root", str(workspace),
        ],
    )

    assert settled.exit_code != 0
    assert "authoritative canonical asset" in str(settled.exception)


def test_forge_run_cannot_close_with_unclassified_source_signal(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = _workspace_with_new_codex_memory(tmp_path, monkeypatch)
    runner = CliRunner()
    opened = runner.invoke(cli_main, ["run", "open", "--root", str(workspace)])
    assert opened.exit_code == 0, opened.output
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
    owner_summary = next(
        line.removeprefix("OWNER-FACING SUMMARY: ")
        for line in closed.output.splitlines()
        if line.startswith("OWNER-FACING SUMMARY: ")
    )
    assert "Forge 本轮未完成并已关闭" in owner_summary
    assert "final_state=incomplete" in owner_summary
    assert "Forge 完成" not in owner_summary

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
    assert "剩余可筛选单元 0" in closed.output
