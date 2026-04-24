"""回滚到某个历史 approved 状态。

v0.1 只支持 "回到当前 approved 的前一次"——通过 git 操作。完整的回滚到
任意历史哈希（跨多个 approve 点、带 bench snapshot 还原）在 v0.2。
"""

from __future__ import annotations

import shutil
from pathlib import Path

from forge.gate.state import GateState


def rollback(root: Path, target_hash_prefix: str | None = None) -> dict:
    """尝试把 sp/ 恢复到前一次 approved 状态。

    参数:
        root               — workspace 根
        target_hash_prefix — 目标 approved_hash 的前缀（12 位或更长）。
                             如果为 None，不做真实回滚；只返回可用的目标列表。

    v0.1 实际做的事:
        1. 读 .forge/changelog.md 里的 "approve (hash=X) — msg" 行
        2. 如果 target_hash_prefix 对应某一条 approve 记录，把 .forge/approved/
           里对应的快照还原到 sp/
        3. 如果 target_hash_prefix 是当前 approved，就把当前 sp/ 恢复到 approved
           （等同于 `forge reject`）

    返回:
        {
          "current_hash": str,
          "available": [{"hash": str, "line": str}, ...],
          "applied_to": str | None,
        }

    v0.1 局限:
        - `.forge/approved/` 只保留 **最近一次** approved 快照。真正的多点
          回滚需要一个 snapshot ring buffer 或 git-based 历史存储，是 v0.2。
        - 所以 target_hash_prefix != current_hash 时会返回 applied_to=None
          以及一条诊断信息，告诉你还没实现跨点回滚。
    """
    state = GateState(root)
    if not state.initialized():
        raise RuntimeError(f"forge not initialized at {root}")
    manifest = state.read_manifest()
    current = manifest.get("approved_hash", "")

    log = state.changelog_path
    available: list[dict] = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            if "approve (hash=" not in line:
                continue
            start = line.find("hash=") + len("hash=")
            end = line.find(")", start)
            if end < 0:
                continue
            available.append({"hash": line[start:end], "line": line.strip()})

    result: dict = {
        "current_hash": current,
        "available": available,
        "applied_to": None,
    }

    if target_hash_prefix is None:
        return result

    # 当前 = target: 把 sp/ 从 approved/ 恢复（和 gate.reject 语义相同）
    if current.startswith(target_hash_prefix):
        shutil.rmtree(state.current_sp, ignore_errors=True)
        shutil.copytree(state.approved_sp, state.current_sp)
        result["applied_to"] = current
        return result

    # target 是历史上的某次 approve，但 v0.1 只存当前 approved
    match = next(
        (e for e in available if e["hash"].startswith(target_hash_prefix)), None
    )
    if match is None:
        raise ValueError(
            f"no approved hash matching prefix `{target_hash_prefix}` in changelog"
        )
    result["applied_to"] = None
    result["diagnostic"] = (
        f"target hash `{match['hash']}` is in changelog but is not the current "
        f"approved. v0.1 only keeps the latest approved snapshot in .forge/approved/. "
        f"Multi-point rollback needs a snapshot ring buffer (v0.2)."
    )
    return result
