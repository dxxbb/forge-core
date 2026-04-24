"""Git log 扫描：把新 commit 里的变动排到 inbox。

v0.1 是一次性扫描（同步调用），不是 daemon。由人或 cron 触发。
完整 daemon 模式（文件系统事件、分钟级 poll）在 v0.2。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from forge.governance.events import (
    ClassifyFn,
    EventType,
    ProposedChange,
    default_classify,
)
from forge.governance.inbox import Inbox


SKIP_TRAILERS = ("Approved-by:", "Rebuilt-by:", "System-owned-by:")
FALLBACK_WINDOW = 50


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), "-c", "core.quotepath=false", *args],
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, result.args, result.stdout, result.stderr
        )
    return result.stdout


def _state_path(root: Path) -> Path:
    return root / ".forge" / "governance" / "state.json"


def _load_state(root: Path) -> dict:
    p = _state_path(root)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(root: Path, state: dict) -> None:
    p = _state_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _commit_has_skip_trailer(msg: str) -> bool:
    return any(
        line.startswith(trailer)
        for line in msg.splitlines()
        for trailer in SKIP_TRAILERS
    )


def _commits_between(root: Path, since: str | None) -> list[str]:
    if since:
        try:
            out = _git(root, "rev-list", "--reverse", f"{since}..HEAD")
        except subprocess.CalledProcessError:
            return []
    else:
        out = _git(
            root, "rev-list", "--reverse", f"--max-count={FALLBACK_WINDOW}", "HEAD"
        )
    return [c for c in out.strip().splitlines() if c]


def _files_in_commit(root: Path, rev: str) -> list[str]:
    out = _git(root, "show", "--pretty=", "--name-status", rev)
    files: list[str] = []
    for line in out.splitlines():
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        status, path = parts
        if status.startswith("D"):
            continue  # deletion — 不入 inbox，由 rollback 处理
        files.append(path.strip())
    return [f for f in files if f.endswith(".md")]


def _frontmatter_at(root: Path, rev: str, path: str) -> dict | None:
    try:
        blob = _git(root, "show", f"{rev}:{path}")
    except subprocess.CalledProcessError:
        return None
    if not blob.startswith("---"):
        return None
    end = blob.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(blob[3:end].strip()) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def scan_git(
    root: Path,
    classify: ClassifyFn | None = None,
    enqueue: bool = True,
) -> list[ProposedChange]:
    """扫描自上次 scan 以来的 commit，返回 ProposedChange 列表。

    参数:
        root     — workspace 根（必须是 git 仓库）
        classify — 路径 → EventType 的分派函数，默认用 `default_classify`
        enqueue  — 是否把结果写进 `.forge/governance/inbox/`

    v0.1 的局限:
        - 只识别 `.md` 文件
        - 跳过 `kind: derived` 和 `kind: wrapper` 的 frontmatter
        - 跳过带 `Approved-by` / `Rebuilt-by` / `System-owned-by` trailer 的 commit
        - 不处理 rename / delete
    """
    classify = classify or default_classify
    state = _load_state(root)
    last_seen = state.get("last_seen_commit")
    new_commits = _commits_between(root, last_seen)

    results: list[ProposedChange] = []
    inbox = Inbox(root) if enqueue else None

    for sha in new_commits:
        msg = _git(root, "show", "--no-patch", "--format=%B", sha)
        if _commit_has_skip_trailer(msg):
            continue
        for path in _files_in_commit(root, sha):
            fm = _frontmatter_at(root, sha, path)
            if fm and fm.get("kind") in ("derived", "wrapper", "system"):
                continue
            ev = classify(path)
            change = ProposedChange(
                commit_sha=sha,
                path=path,
                event_type=ev,
                frontmatter=fm or {},
            )
            results.append(change)
            if inbox:
                inbox.enqueue(
                    event_type=ev.value,
                    commit_sha=sha,
                    path=path,
                    note=f"auto-queued by `forge watch` from commit {sha[:8]}",
                )

    if new_commits:
        state["last_seen_commit"] = new_commits[-1]
        _save_state(root, state)

    return results
