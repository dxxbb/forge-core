"""Inbox：候选改动的排队 + 管理。

存储位置：`.forge/governance/inbox/NNNN-<event-type>.md`

每条 TODO 是一个 markdown 文件，YAML frontmatter 保存元数据，body 保留
自由文本给 agent 写 triage note。

API 刻意小——只有 enqueue / list / skip / remove。完整的 "triage workflow"
（request-changes 回合、分派到特定 agent 等）是 v0.2 的事。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass
class Todo:
    id: int
    event_type: str
    commit_sha: str
    path: str
    created_at: str
    note: str = ""
    file: Path | None = None


class Inbox:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / ".forge" / "governance" / "inbox"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _next_id(self) -> int:
        max_id = 0
        for p in self.dir.glob("*.md"):
            m = re.match(r"^(\d+)-", p.stem)
            if m:
                max_id = max(max_id, int(m.group(1)))
        return max_id + 1

    def enqueue(
        self,
        event_type: str,
        commit_sha: str,
        path: str,
        note: str = "",
    ) -> Todo:
        tid = self._next_id()
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        fname = f"{tid:04d}-{event_type}.md"
        fpath = self.dir / fname
        fm = {
            "id": tid,
            "event_type": event_type,
            "commit_sha": commit_sha,
            "path": path,
            "created_at": now,
        }
        body = note.strip() + "\n" if note else ""
        fpath.write_text(
            f"---\n{yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip()}\n---\n\n{body}",
            encoding="utf-8",
        )
        return Todo(
            id=tid,
            event_type=event_type,
            commit_sha=commit_sha,
            path=path,
            created_at=now,
            note=note,
            file=fpath,
        )

    def list(self) -> list[Todo]:
        out: list[Todo] = []
        for p in sorted(self.dir.glob("*.md")):
            todo = self._parse(p)
            if todo:
                out.append(todo)
        return out

    def get(self, todo_id: int) -> Todo | None:
        for p in self.dir.glob(f"{todo_id:04d}-*.md"):
            return self._parse(p)
        return None

    def skip(self, todo_id: int, reason: str) -> None:
        """把一个 TODO 标记为 skip——从 inbox 移除，追加到 changelog。"""
        todo = self.get(todo_id)
        if todo is None:
            raise KeyError(f"todo {todo_id} not found in inbox")
        # 追加到 governance changelog
        log = self.root / ".forge" / "governance" / "changelog.md"
        log.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        line = f"- {now} skip inbox/{todo_id:04d} ({todo.event_type}, {todo.path}) — {reason}\n"
        with log.open("a", encoding="utf-8") as f:
            f.write(line)
        if todo.file:
            todo.file.unlink()

    def remove(self, todo_id: int) -> None:
        """从 inbox 删除 TODO，不记 log（审核通过后 gate 会自己记 log）。"""
        todo = self.get(todo_id)
        if todo is None:
            return
        if todo.file:
            todo.file.unlink()

    def _parse(self, path: Path) -> Todo | None:
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            return None
        end = text.find("\n---", 3)
        if end < 0:
            return None
        fm = yaml.safe_load(text[3:end].strip()) or {}
        if not isinstance(fm, dict) or "id" not in fm:
            return None
        body = text[end + 4 :].strip()
        return Todo(
            id=int(fm["id"]),
            event_type=str(fm.get("event_type", "unclassified")),
            commit_sha=str(fm.get("commit_sha", "")),
            path=str(fm.get("path", "")),
            created_at=str(fm.get("created_at", "")),
            note=body,
            file=path,
        )
