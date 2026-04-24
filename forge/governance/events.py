"""Event types + 默认分派规则（按路径前缀分类）。

MVP 事件类型来自 dxyOS forge 实际跑通的经验。使用者可以用自己的 classify
函数替换默认规则——governance 的 events 层刻意不绑死 dxyOS 目录结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class EventType(str, Enum):
    # 6 个 MVP 活跃事件类型（dxyOS 实际覆盖过的）
    conversation = "conversation"       # 会话沉淀进 memory
    cc_memory = "cc_memory"             # Claude Code auto-memory 变更
    pr_revision = "pr_revision"         # 一次 PR 的 review 回合
    ingest = "ingest"                   # 外部素材入 KB
    project_update = "project_update"   # workspace project 变更
    skill_change = "skill_change"       # skill 目录变更

    # 无法分类
    unclassified = "unclassified"


@dataclass
class ProposedChange:
    """一次扫描发现的、候选进入系统的改动。"""

    commit_sha: str
    path: str
    event_type: EventType
    summary: str = ""
    frontmatter: dict = field(default_factory=dict)


# 默认的路径 → EventType 映射，沿用 dxyOS forge MVP 规则
# 使用者可以自己写一个 classify 函数覆盖。
_DEFAULT_RULES: list[tuple[str, EventType]] = [
    ("01 assist/memory collection/agents memory/", EventType.cc_memory),
    ("01 assist/memory collection/history/", EventType.conversation),
    ("01 assist/learn and improve/skill/", EventType.skill_change),
    ("03 workspace/project/", EventType.project_update),
    ("04 knowledge base/src/", EventType.ingest),
    # 明确需要 PR round-trip 的路径会独立标 pr_revision，这里默认规则里不放
]


def default_classify(path: str) -> EventType:
    for prefix, ev in _DEFAULT_RULES:
        if path.startswith(prefix):
            return ev
    return EventType.unclassified


ClassifyFn = Callable[[str], EventType]
