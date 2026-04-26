"""Roll sp/ + output/ back to a historical approved state.

v0.2: rollback is `git checkout <hash> -- sp/ output/` — works for any commit
in the workspace's git history, not just the most recent one. This was the
fundamental v0.1 limitation that motivated the git rewrite.
"""

from __future__ import annotations

from pathlib import Path

from forge.gate import _git
from forge.gate.state import GateState


def rollback(root: Path, target_hash_prefix: str | None = None) -> dict:
    """Roll sp/ + output/ back to a historical approved state.

    Args:
        root: workspace root
        target_hash_prefix: short or full git hash. If None, list available hashes.

    Returns:
        {
          "current_hash": str,
          "available": [{"hash": str, "short": str, "subject": str, "at": str}, ...],
          "applied_to": str | None,    # hash that was checked out, or None if listing
        }

    Behavior:
        - target_hash_prefix=None  → list all approved commits, do nothing
        - target_hash_prefix=<x>   → look up commit, git checkout <hash> -- sp/ output/,
                                     then `forge approve` later to make it official HEAD
                                     (rollback writes working tree but doesn't auto-commit
                                      — user reviews via `forge review` first)
    """
    state = GateState(root)
    if not state.initialized():
        raise RuntimeError(f"forge not initialized at {root}")

    head = _git.head_hash(root) or ""
    log = _git.log_for_paths(root, ["sp"])

    available = [
        {"hash": e["hash"], "short": e["short"], "subject": e["subject"], "at": e["at"]}
        for e in log
    ]

    result: dict = {
        "current_hash": head,
        "available": available,
        "applied_to": None,
    }

    if target_hash_prefix is None:
        return result

    # find matching commit
    match = next((e for e in log if e["hash"].startswith(target_hash_prefix)), None)
    if match is None:
        raise ValueError(
            f"no commit hash starts with `{target_hash_prefix}` in sp/ history. "
            f"Run `forge rollback` (no arg) to list available hashes."
        )

    # check working tree clean for sp/ + output/ — refuse to rollback over uncommitted changes
    if _git.has_pending_changes(root, ["sp", "output"]):
        raise RuntimeError(
            "working tree has uncommitted changes to sp/ or output/. "
            "Run `forge approve` or `forge reject` first, then retry rollback."
        )

    _git.checkout_paths_at_ref(root, match["hash"], ["sp", "output"])
    result["applied_to"] = match["hash"]
    result["next_step"] = (
        "Working tree now reflects this old commit. Run `forge review` to "
        "see what changed and `forge approve -m 'rollback to <short>'` to "
        "make it the new HEAD."
    )
    return result
