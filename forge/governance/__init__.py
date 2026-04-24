"""Governance pillar: upstream of the audit gate.

v0.1 实现的 `forge/gate/` 是 governance 里"决定某次改动是否进系统"的那一小段。
本模块补上前置和后置：

    watcher — 扫描新 commit，把"可能要进系统的改动"排队到 inbox
            → inbox — 排队、分派、跳过
              → gate（forge/gate/）— 审核 diff / approve / reject
                → changelog — append-only 审计
                  → rollback — 从历史某个通过点恢复

v0.1 里 watcher / inbox / rollback 都是 **stub 级别**：
- watcher 仅实现 git log 扫描 + 最小分派规则
- inbox 仅实现 enqueue / list / skip
- rollback 仅从 changelog 回溯到某个 approved hash

完整 daemon 模式、request-changes 回合、事件类型大全，是 v0.2。
"""

from forge.governance.events import EventType, ProposedChange, default_classify
from forge.governance.inbox import Inbox, Todo
from forge.governance.watcher import scan_git
from forge.governance.rollback import rollback

__all__ = [
    "EventType",
    "ProposedChange",
    "default_classify",
    "Inbox",
    "Todo",
    "scan_git",
    "rollback",
]
