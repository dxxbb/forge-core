"""Deterministic backbone of Evidence-to-Asset Promotion.

The owner opens a Run; the agent gives every new input one disposition and
drafts only admission-checked Candidate Assets. The CLI presents integrity
issues plus at most three candidates, executes decisions through the existing
ledger/compile gate, expires stale observations, and writes the closing report.
Between Runs the system demands nothing from the owner.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from forge import ledger as ledgerlib
from forge.gate import _git
from forge.gate.actions import build as rebuild_outputs
from forge import promotion
from forge.zone import (
    certified_info,
    gate_drifts,
    load_zones,
    uncertified_diff,
    update_verified_snapshot,
    verified_snapshot_path,
)

RUN_DIR = Path("system") / "run"
DEFAULT_BUDGET = 3
_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", re.DOTALL)
_CANONICAL_SINK_PREFIXES = (
    "assist config/",
    "context build/config/",
    "context build/sections/",
    "public knowledge base/",
    "user space/",
    "workbench/",
    "workspace/",
)
_NON_AUTHORITATIVE_SINK_PARTS = {"capture", "output", "scratch", "temp", "tmp"}


@dataclass
class AskItem:
    id: str
    type: str  # conflict | candidate | unqualified-change
    title: str
    detail: str
    deferred: bool = False


@dataclass
class RunRecord:
    id: str
    status: str
    opened_at: str
    closed_at: str
    inputs: list[dict[str, Any]] = field(default_factory=list)
    dispositions: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)
    expired_observations: list[str] = field(default_factory=list)
    path: Path | None = None


def run_dir(root: Path) -> Path:
    return Path(root) / RUN_DIR


# ---------- status ----------

def status(
    root: Path,
    *,
    source_signals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    root = Path(root).resolve()
    records = _records(root)
    closed = [r for r in records if r.status == "closed"]
    last_closed = max((r.closed_at for r in closed), default="")
    items = _ask_items(root)
    freshness = _state_freshness(root)
    candidates = promotion.list_candidates(root, include_decided=True)
    observations = promotion.list_observations(root, include_closed=True)
    signals = source_signals or []
    pending_candidates = sum(1 for c in candidates if c.state == "pending")
    selection = _selection_facts(
        root,
        signals,
        pending_candidates=pending_candidates,
        observing=sum(1 for o in observations if o.state == "open"),
    )
    source_signal_counts: dict[str, int] = {}
    for signal in signals:
        kind = signal.get("path", "").removeprefix("source://")
        if kind:
            source_signal_counts[kind] = source_signal_counts.get(kind, 0) + 1
    source_diagnostics = [
        {
            "source_kind": _source_kind(signal),
            "eligible_review_units": int(signal.get("total_count") or 1),
            "batch_size": int(signal.get("batch_size") or 0),
            "batch_bytes": int(signal.get("batch_bytes") or 0),
            "excluded_source_counts": dict(
                signal.get("excluded_source_counts") or {}
            ),
        }
        for signal in signals
    ]
    return {
        "last_run_closed_at": last_closed or None,
        "days_since_last_run": _days_since(last_closed),
        "open_run": next((r.id for r in records if r.status == "open"), None),
        "source_attention": bool(signals),
        "source_signal_counts": source_signal_counts,
        "source_diagnostics": source_diagnostics,
        **selection,
        "ask_counts": {
            t: sum(1 for i in items if i.type == t)
            for t in ("conflict", "candidate", "unqualified-change")
        },
        "candidate_counts": {
            state: sum(1 for c in candidates if c.state == state)
            for state in ("pending", "promoted", "rejected", "observing")
        },
        "observation_counts": {
            state: sum(1 for o in observations if o.state == state)
            for state in ("open", "promoted", "closed")
        },
        "promotion_metrics": promotion.promotion_metrics(root),
        "state_freshness": freshness,
    }


def _selection_facts(
    root: Path,
    source_signals: list[dict[str, Any]],
    *,
    pending_candidates: int,
    observing: int,
) -> dict[str, Any]:
    """Return the only valid global candidate conclusion.

    A zero-sized candidate pool is not evidence that selection found nothing:
    any outstanding Review Unit makes the global conclusion unknown.
    """
    unprocessed_sources = _remaining_source_count(source_signals)
    unprocessed_captures = len(_pending_capture_inputs(root))
    unprocessed = unprocessed_sources + unprocessed_captures
    coverage = "complete" if unprocessed == 0 else "incomplete"
    if pending_candidates:
        conclusion = "available"
    elif coverage == "complete":
        conclusion = "none"
    else:
        conclusion = "unknown"
    return {
        "selection_coverage": coverage,
        "candidate_conclusion": conclusion,
        "unprocessed_review_units": unprocessed,
        "unprocessed_source_units": unprocessed_sources,
        "unprocessed_capture_evidence": unprocessed_captures,
        "observing_units": observing,
    }


# ---------- open / close ----------

def open_run(
    root: Path,
    *,
    source_signals: list[dict[str, Any]] | None = None,
) -> RunRecord:
    """Create the run record, or resume the one still open (AC-RUN-2)."""
    root = Path(root).resolve()
    existing = next((r for r in _records(root) if r.status == "open"), None)
    if existing is not None:
        if source_signals:
            existing_paths = {item.get("path") for item in existing.inputs}
            for signal in source_signals:
                path = signal.get("path")
                if path not in existing_paths:
                    existing.inputs.append(signal)
                    existing_paths.add(path)
            _write_record(root, existing)
        return existing
    inputs = _pending_capture_inputs(root)
    inputs.extend(source_signals or [])
    base_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id, n = base_id, 0
    while (run_dir(root) / f"{run_id}.md").exists():
        n += 1
        run_id = f"{base_id}-{n}"
    expired = promotion.expire_observations(root)
    record = RunRecord(
        id=run_id,
        status="open",
        opened_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        closed_at="",
        inputs=inputs,
        expired_observations=expired,
    )
    _write_record(root, record)
    return record


def close_run(
    root: Path,
    *,
    current_source_signals: list[dict[str, Any]] | None = None,
    refresh_source_signals: Callable[[], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Rebuild, report, mark closed, and commit the run's bookkeeping (AC-RUN-6)."""
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")
    unclassified = [
        item for item in record.inputs if not _input_is_classified(record, item)
    ]
    if unclassified:
        paths = ", ".join(i.get("path", "") for i in unclassified[:3])
        raise RuntimeError(f"unclassified input(s): {paths}")
    current_signals_by_path = {
        signal.get("path", ""): signal for signal in (current_source_signals or [])
    }
    unresolved_sources: list[str] = []
    for item in record.inputs:
        if item.get("type") != "source-signal":
            continue
        current_signal = current_signals_by_path.get(item.get("path", ""))
        if current_signal is None:
            continue
        dispositions = _dispositions_for_input(record, item)
        if any(disposition.get("kind") == "defer" for disposition in dispositions):
            unresolved_sources.append(item.get("path", ""))
            continue
        batch_items = list(item.get("batch_items") or [])
        if batch_items:
            if not dispositions or not all(
                disposition.get("source_settled") is True
                for disposition in dispositions
            ):
                raise RuntimeError(
                    f"source batch has unsettled Review Unit(s): {item.get('path')}"
                )
            if current_signal is not None:
                original_refs = {
                    _batch_item_ref(batch_item) for batch_item in batch_items
                }
                current_refs = {
                    _batch_item_ref(batch_item)
                    for batch_item in (current_signal.get("batch_items") or [])
                }
                if original_refs & current_refs:
                    raise RuntimeError(
                        f"source signal still contains settled Review Unit(s): "
                        f"{item.get('path')}"
                    )
            continue
        disposition = dispositions[0] if dispositions else {}
        batch_advanced = (
            disposition.get("source_settled") is True
            and current_signal.get("digest") != item.get("digest")
        )
        if not batch_advanced:
            raise RuntimeError(
                f"source signal still actionable: {item.get('path')} "
                "(resolve it or record --as defer with a reason)"
            )
    settled = [
        e for e in ledgerlib.list_entries(root) if e.origin == f"run:{record.id}"
    ]
    remaining_before_close = _ask_items(root)
    if (
        not record.inputs
        and not record.dispositions
        and not record.decisions
        and not record.expired_observations
        and not remaining_before_close
        and not settled
    ):
        if record.path is not None and record.path.exists():
            record.path.unlink()
        final_signals = (
            refresh_source_signals()
            if refresh_source_signals is not None
            else (current_source_signals or [])
        )
        return _with_final_facts(root, {
            "empty": True,
            "settled": 0,
            "decisions": 0,
            "deferred": 0,
            "pending_candidates": 0,
            "integrity_issues": 0,
            "rule_changes_decided": 0,
            "dispositions": {},
            "expired_observations": 0,
            "unresolved_sources": 0,
            "remaining_sources": 0,
        }, final_signals)
    runtime_paths = rebuild_outputs(root)
    remaining = _ask_items(root)
    final_signals = (
        refresh_source_signals()
        if refresh_source_signals is not None
        else (current_source_signals or [])
    )
    pending_candidates = sum(1 for item in remaining if item.type == "candidate")
    observing = sum(
        1 for observation in promotion.list_observations(root, include_closed=True)
        if observation.state == "open"
    )
    record.status = "closed"
    record.closed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "empty": False,
        "settled": len(settled),
        "decisions": len(record.decisions),
        "deferred": len(remaining),
        "pending_candidates": pending_candidates,
        "integrity_issues": sum(
            1 for item in remaining if item.type in {"conflict", "unqualified-change"}
        ),
        "rule_changes_decided": sum(
            1 for d in record.decisions if d.get("type") == "unqualified-change"
        ),
        "dispositions": _count_by(record.dispositions, "kind"),
        "expired_observations": len(record.expired_observations),
        "unresolved_sources": len(unresolved_sources),
        "remaining_sources": _remaining_source_count(final_signals),
        **_selection_facts(
            root,
            final_signals,
            pending_candidates=pending_candidates,
            observing=observing,
        ),
    }
    _write_record(root, record, report=report)
    scoped = [str((run_dir(root) / f"{record.id}.md").relative_to(root))]
    scoped.extend(str(path.resolve().relative_to(root)) for path in runtime_paths)
    scoped += [
        str(e.path.relative_to(root))
        for e in ledgerlib.list_entries(root)
        if e.path is not None and e.state in ("held-conflict", "rejected")
    ]
    for disposition in record.dispositions:
        sink = disposition.get("sink", "")
        if sink.startswith("obs-"):
            scoped.append(f"system/observations/{sink}.md")
        elif sink.startswith("cand-"):
            scoped.append(f"system/candidates/{sink}.md")
        scoped.extend(str(path) for path in disposition.get("settled_paths", []))
    for decision in record.decisions:
        if decision.get("type") != "candidate":
            continue
        candidate = promotion.get_candidate(root, decision.get("ask_id", ""))
        if candidate is None:
            continue
        scoped.append(f"system/candidates/{candidate.id}.md")
        if candidate.observation_id:
            scoped.append(f"system/observations/{candidate.observation_id}.md")
    scoped.extend(
        f"system/observations/{obs_id}.md" for obs_id in record.expired_observations
    )
    scoped = list(dict.fromkeys(path for path in scoped if (root / path).exists()))
    try:
        _git.add(root, scoped)
        _git.commit(
            root, f"run: close {record.id}", trailers={"Run-Id": record.id}
        )
    except Exception as exc:  # noqa: BLE001 — restore resumable run state, then fail loud
        try:
            _git.git(root, ["reset", "--", *scoped], allow_empty_output=True)
        except Exception:
            pass
        record.status = "open"
        record.closed_at = ""
        _write_record(root, record)
        raise RuntimeError(f"failed to commit run close {record.id}: {exc}") from exc
    post_commit_signals = (
        refresh_source_signals()
        if refresh_source_signals is not None
        else final_signals
    )
    closure_report = _with_final_facts(root, report, post_commit_signals)
    # Source providers whose truth depends on the close commit can change their
    # remaining inventory between the preliminary report and the committed
    # state. Persist that post-commit Closure Snapshot, then amend the same Run
    # commit so the report and returned CLI facts cannot diverge.
    _write_record(root, record, report=closure_report)
    run_relpath = str((run_dir(root) / f"{record.id}.md").relative_to(root))
    try:
        _git.add(root, [run_relpath])
        _git.git(root, ["commit", "--amend", "--no-edit"])
    except Exception as exc:  # noqa: BLE001 — a stale persisted report is not success
        raise RuntimeError(
            f"failed to persist closure snapshot for {record.id}: {exc}"
        ) from exc
    final_commit = _git.head_hash(root)
    assert final_commit is not None
    closure_report["commit"] = final_commit
    return closure_report


def record_disposition(
    root: Path,
    input_ref: str,
    kind: str,
    *,
    sink: str = "",
    note: str = "",
    item_ref: str = "",
) -> dict[str, Any]:
    """Give one newly collected input exactly one terminal or promotion route."""
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")
    allowed = {
        "covered", "one-off", "volatile-state", "observe", "candidate", "closed", "defer"
    }
    if kind not in allowed:
        raise ValueError("disposition must be " + "|".join(sorted(allowed)))
    item = next((i for i in record.inputs if i.get("path") == input_ref), None)
    if item is None:
        digest_matches = [
            candidate for candidate in record.inputs
            if candidate.get("digest") == input_ref
        ]
        if len(digest_matches) > 1:
            raise ValueError(
                f"input digest is ambiguous; use the exact input path: {input_ref}"
            )
        item = digest_matches[0] if digest_matches else None
    if item is None:
        raise ValueError(f"input not found in open run: {input_ref}")
    batch_items = list(item.get("batch_items") or [])
    batch_item: dict[str, Any] | None = None
    if batch_items and kind != "defer":
        if not item_ref.strip():
            raise ValueError(
                f"source batch {item.get('path')} requires --item for each Review Unit"
            )
        batch_item = next(
            (
                candidate for candidate in batch_items
                if item_ref in {
                    str(candidate.get("unit_id") or ""),
                    str(candidate.get("path") or ""),
                }
            ),
            None,
        )
        if batch_item is None:
            raise ValueError(f"Review Unit not found in source batch: {item_ref}")
    elif item_ref.strip():
        raise ValueError("--item is only valid for a non-defer Source Batch disposition")
    if kind == "defer" and item.get("type") != "source-signal":
        raise ValueError("defer is only valid for a source signal")
    if kind == "defer" and batch_items and _dispositions_for_input(record, item):
        raise ValueError("cannot defer a Source Batch after Review Unit settlement started")
    if kind in {"covered", "one-off", "volatile-state"} and not sink.strip():
        raise ValueError(f"{kind} disposition requires a concrete sink")
    if kind == "covered":
        sink = _authoritative_canonical_sink(root, sink, disposition="covered")
    if kind == "volatile-state":
        sink = _volatile_state_receipt(root, record, sink)
    if kind == "observe":
        if not any(
            o.id == sink for o in promotion.list_observations(root, include_closed=True)
        ):
            raise ValueError(f"observation sink not found: {sink}")
    if kind == "candidate":
        if promotion.get_candidate(root, sink) is None:
            raise ValueError(f"candidate sink not found: {sink}")
    if kind in {"closed", "defer"} and not note.strip():
        raise ValueError(f"{kind} disposition requires a reason")
    disposition = {
        "input_path": item["path"],
        "input_digest": item["digest"],
        "kind": kind,
        "sink": sink.strip(),
        "note": note.strip(),
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if batch_item is not None:
        disposition.update(
            {
                "batch_item_ref": str(
                    batch_item.get("unit_id") or batch_item.get("path") or ""
                ),
                "batch_item_path": str(batch_item.get("path") or ""),
                "batch_item_digest": str(batch_item.get("digest") or ""),
            }
        )
    if item.get("type") == "source-signal" and kind != "defer":
        settlement = _settle_source_batch(
            root,
            item,
            disposition_kind=kind,
            sink=sink.strip(),
            batch_items=[batch_item] if batch_item is not None else None,
        )
        if settlement["items"]:
            disposition["source_settled"] = True
            disposition["settled_items"] = settlement["items"]
            disposition["settled_paths"] = settlement["paths"]
    record.dispositions = [
        d for d in record.dispositions
        if not (
            d.get("input_path") == item["path"]
            and d.get("input_digest") == item["digest"]
            and d.get("batch_item_ref", "")
            == disposition.get("batch_item_ref", "")
        )
    ]
    record.dispositions.append(disposition)
    _write_record(root, record)
    return disposition


def _authoritative_canonical_sink(
    root: Path, sink: str, *, disposition: str,
) -> str:
    """Resolve a durable, non-private Canonical Source receipt inside ``root``."""
    candidate = Path(sink).expanduser()
    path = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    try:
        relpath = path.relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise ValueError(
            f"{disposition} sink is not an authoritative canonical asset: {sink}"
        ) from exc
    parts = {part.casefold() for part in Path(relpath).parts}
    if (
        not path.is_file()
        or not relpath.startswith(_CANONICAL_SINK_PREFIXES)
        or relpath.startswith("user space/private/")
        or "secret" in parts
        or bool(parts & _NON_AUTHORITATIVE_SINK_PARTS)
    ):
        raise ValueError(
            f"{disposition} sink is not an authoritative canonical asset: {sink}"
        )
    if _git.is_git_repo(root):
        tracked = _git.git(
            root, ["ls-files", "--error-unmatch", "--", relpath],
            check=False, allow_empty_output=True,
        ).strip()
        if not tracked:
            raise ValueError(
                f"{disposition} sink is not an authoritative canonical asset: {sink}"
            )
    return relpath


def _volatile_state_receipt(root: Path, record: RunRecord, sink: str) -> str:
    relpath = _authoritative_canonical_sink(
        root, sink, disposition="volatile-state"
    )
    dirty = False
    if _git.is_git_repo(root):
        dirty = bool(
            _git.git(
                root, ["status", "--porcelain", "--", relpath],
                allow_empty_output=True,
            ).strip()
        )
    ledgered = any(
        entry.origin == f"run:{record.id}"
        and entry.target == relpath
        and entry.state not in {"failed", "stale"}
        for entry in ledgerlib.list_entries(root)
    )
    if not dirty and not ledgered:
        raise ValueError(
            "volatile-state disposition requires a current Run write receipt: "
            f"{relpath} is unchanged and has no run ledger entry"
        )
    return relpath


def _settle_source_batch(
    root: Path,
    item: dict[str, Any],
    *,
    disposition_kind: str,
    sink: str,
    batch_items: list[dict[str, Any] | None] | None = None,
) -> dict[str, list[str]]:
    source_kind = _source_kind(item)
    selected_items = [
        batch_item for batch_item in (batch_items or item.get("batch_items") or [])
        if batch_item is not None
    ]
    if source_kind == "agent-memory" and selected_items:
        from forge.governance.claude_memory import settle_run_source_batch

        items = settle_run_source_batch(root, selected_items)
        state_relpath = ".forge/agent_memory_state.json"
        tracked = (
            _git.git(
                root,
                ["ls-files", "--", state_relpath],
                allow_empty_output=True,
            ).strip()
            if _git.is_git_repo(root) else ""
        )
        return {
            "items": items,
            "paths": [state_relpath] if tracked else [],
        }
    if source_kind == "web-clipping" and selected_items:
        from forge.governance.web_clipping import settle_run_source_batch

        paths = settle_run_source_batch(
            root,
            selected_items,
            disposition_kind=disposition_kind,
            sink=sink,
            at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        return {"items": paths, "paths": paths}
    return {"items": [], "paths": []}


def _dispositions_for_input(
    record: RunRecord,
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        disposition for disposition in record.dispositions
        if disposition.get("input_path") == item.get("path")
        and disposition.get("input_digest") == item.get("digest")
    ]


def _pending_batch_items(
    record: RunRecord,
    item: dict[str, Any],
) -> list[dict[str, Any]]:
    settled_refs = {
        disposition.get("batch_item_ref")
        for disposition in _dispositions_for_input(record, item)
        if disposition.get("batch_item_ref")
    }
    return [
        batch_item for batch_item in (item.get("batch_items") or [])
        if _batch_item_ref(batch_item) not in settled_refs
    ]


def _batch_item_ref(batch_item: dict[str, Any]) -> str:
    return str(batch_item.get("unit_id") or batch_item.get("path") or "")


def _input_is_classified(record: RunRecord, item: dict[str, Any]) -> bool:
    dispositions = _dispositions_for_input(record, item)
    if any(disposition.get("kind") == "defer" for disposition in dispositions):
        return True
    batch_items = list(item.get("batch_items") or [])
    if batch_items:
        return not _pending_batch_items(record, item)
    return bool(dispositions)


def _pending_capture_inputs(root: Path) -> list[dict[str, Any]]:
    """Return standalone capture evidence that has no recorded disposition.

    Source-provider captures are owned by their Source Signal adapter.  A
    standalone capture remains selectable until a Run records its disposition;
    merely snapshotting it into an open Run is not selection coverage.
    """
    classified = {
        (item.get("path"), item.get("digest"))
        for record in _records(root)
        for item in record.inputs
        if item.get("digest") and (
            (
                item.get("type") == "capture-evidence"
                and _input_is_classified(record, item)
            )
            or (
                not item.get("type")
                and record.status == "closed"
                and str(item.get("path") or "").startswith("capture/")
            )
        )
    }
    pending: list[dict[str, Any]] = []
    capture_root = root / "capture"
    if not capture_root.is_dir():
        return pending
    for path in sorted(capture_root.rglob("*.md")):
        if _is_provider_managed_capture(root, path):
            continue
        digest = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
        relpath = path.relative_to(root).as_posix()
        if (relpath, digest) in classified:
            continue
        pending.append(
            {
                "path": relpath,
                "digest": digest,
                "type": "capture-evidence",
            }
        )
    return pending


# ---------- deterministic interaction contract ----------

_SOURCE_PRIORITY = {
    "skill-projection": 10,
    "pending-proposal": 20,
    "pending-inbox": 30,
    "context-drift": 40,
    "import-update": 50,
    "workspace-project": 60,
    "internal-content": 70,
    "web-clipping": 80,
    "agent-memory": 90,
}

_BACKGROUND_PROGRESS = {
    "progress_reporting": "heartbeat-only",
    "safe_heartbeat": {
        "running": True,
        "owner_decision_ready": False,
    },
    "progress_scope": ["owner-decision-ready"],
    "progress_forbidden": [
        "processed-count",
        "remaining-count",
        "source-title",
        "disposition-kind",
        "theme",
        "reason",
        "observation-detail",
    ],
}


def next_contract(root: Path, *, budget: int = DEFAULT_BUDGET) -> dict[str, Any]:
    """Return one machine-readable next step for the open Run.

    The contract removes workflow choice from the operator while leaving the
    semantic judgment inside the selected bounded input to the agent.
    """
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")

    mandatory = [
        item for item in _ask_items(root)
        if item.type in {"conflict", "unqualified-change"}
    ]
    if mandatory:
        item = mandatory[0]
        return {
            "run_id": record.id,
            "action": "decide-integrity",
            "owner_visibility": "decision",
            "ask_id": item.id,
            "ask_type": item.type,
            "title": item.title,
            "detail": item.detail,
            "constraints": ["present this one decision to the owner"],
        }

    unclassified = [
        item for item in record.inputs if not _input_is_classified(record, item)
    ]
    source_inputs = [
        item for item in unclassified if item.get("type") == "source-signal"
    ]
    if source_inputs:
        source_inputs.sort(
            key=lambda item: (
                _SOURCE_PRIORITY.get(_source_kind(item), 999),
                item.get("path", ""),
            )
        )
        item = source_inputs[0]
        kind = _source_kind(item)
        pending_batch_items = _pending_batch_items(record, item)
        if pending_batch_items:
            review_unit = pending_batch_items[0]
            return {
                "run_id": record.id,
                "action": "classify-source-item",
                "owner_visibility": "silent",
                **_BACKGROUND_PROGRESS,
                "input_ref": item.get("path", ""),
                "source_kind": kind,
                "handler": item.get("handler", "source-review"),
                "summary": item.get("summary", ""),
                "review_unit": review_unit,
                "source_batch_size": int(item.get("batch_size") or 0),
                "remaining_in_batch": len(pending_batch_items),
                "total_count": int(item.get("total_count") or 0),
                "remaining_count": int(item.get("remaining_count") or 0),
                "excluded_source_counts": dict(
                    item.get("excluded_source_counts") or {}
                ),
                "constraints": _source_constraints(kind, per_item=True),
            }
        return {
            "run_id": record.id,
            "action": "classify-source",
            "owner_visibility": "silent",
            **_BACKGROUND_PROGRESS,
            "input_ref": item.get("path", ""),
            "source_kind": kind,
            "handler": item.get("handler", "source-review"),
            "summary": item.get("summary", ""),
            "detail": item.get("detail", ""),
            "batch_items": item.get("batch_items", []),
            "batch_size": int(item.get("batch_size") or 0),
            "total_count": int(item.get("total_count") or 0),
            "remaining_count": int(item.get("remaining_count") or 0),
            "constraints": _source_constraints(kind),
        }

    capture_inputs = [
        item for item in unclassified if item.get("type") == "capture-evidence"
    ]
    if capture_inputs:
        item = sorted(capture_inputs, key=lambda row: row.get("path", ""))[0]
        return {
            "run_id": record.id,
            "action": "classify-evidence",
            "owner_visibility": "silent",
            **_BACKGROUND_PROGRESS,
            "input_ref": item.get("path", ""),
            "constraints": ["record exactly one disposition for this evidence"],
        }

    candidate_decisions = sum(
        1 for decision in record.decisions if decision.get("type") == "candidate"
    )
    candidate_budget = max(0, max(0, budget) - candidate_decisions)
    candidates = [item for item in _ask_items(root) if item.type == "candidate"]
    if candidates and candidate_budget:
        item = candidates[0]
        return {
            "run_id": record.id,
            "action": "decide-candidate",
            "owner_visibility": "decision",
            "ask_id": item.id,
            "ask_type": item.type,
            "title": item.title,
            "detail": item.detail,
            "review_budget_remaining": candidate_budget,
            "constraints": [
                "present the complete card in simple language, including why now, actual source events, existing coverage, why this belongs in an owner-governed durable asset, promotion ground, future effect, exact patch, and decision question",
                "do not collapse the card into only the proposed rule",
                "do not decide for the owner",
            ],
        }

    return {
        "run_id": record.id,
        "action": "close",
        "owner_visibility": "summary",
        "constraints": [
            "run forge run close",
            "report the returned open, dirty, and remaining-source facts verbatim",
        ],
    }


def _source_kind(item: dict[str, Any]) -> str:
    return str(
        item.get("source_kind")
        or str(item.get("path") or "").removeprefix("source://")
    )


def _source_constraints(kind: str, *, per_item: bool = False) -> list[str]:
    unit_rule = (
        "record exactly one disposition for this Review Unit using --item"
        if per_item else
        "record exactly one disposition for this source"
    )
    if kind == "agent-memory":
        return [
            "inspect only the listed Review Unit and its evidence pointers",
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
            unit_rule,
        ]
    if kind == "web-clipping":
        return [
            "check existing canonical sinks before creating new knowledge",
            "do not invoke deep knowledge intake without explicit owner request",
            unit_rule,
        ]
    return [unit_rule]


def _is_provider_managed_capture(root: Path, path: Path) -> bool:
    """Avoid presenting one source through both a batch and raw capture input."""
    try:
        relpath = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    if relpath.startswith("capture/web clipping/"):
        return True
    if not relpath.startswith("capture/import/"):
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    frontmatter = _FRONTMATTER_RE.match(text)
    if frontmatter is None:
        return False
    try:
        metadata = yaml.safe_load(frontmatter.group(1)) or {}
    except yaml.YAMLError:
        return False
    source = str(metadata.get("source") or "") if isinstance(metadata, dict) else ""
    return source.startswith(("codex-memory-history:", "claude-code-memory:"))


# ---------- ask / decide ----------

def ask(root: Path, budget: int = DEFAULT_BUDGET) -> list[AskItem]:
    """Return mandatory integrity issues plus at most ``budget`` candidates."""
    items = _ask_items(root)
    mandatory = [i for i in items if i.type in {"conflict", "unqualified-change"}]
    candidates = [i for i in items if i.type == "candidate"]
    return mandatory + candidates[: max(0, budget)]


def decide(root: Path, ask_id: str, decision: str, note: str = "") -> dict[str, Any]:
    """Execute one owner decision immediately (AC-RUN-5)."""
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")
    item = next((i for i in _ask_items(root) if i.id == ask_id), None)
    if item is None:
        raise ValueError(f"unknown ask item: {ask_id}")
    if decision not in ("approve", "reject", "observe"):
        raise ValueError(f"decision must be approve|reject|observe, got {decision!r}")
    if item.type != "candidate" and decision == "observe":
        raise ValueError("observe is only valid for a candidate")

    if item.type == "conflict":
        outcome = _decide_conflict(root, record, ask_id, decision, note)
    elif item.type == "unqualified-change":
        outcome = _decide_rule_change(root, record, item, decision, note)
    elif item.type == "candidate":
        outcome = _decide_candidate(root, record, ask_id, decision, note)
    else:
        raise ValueError(f"unsupported ask item type: {item.type}")

    record.decisions.append(
        {"ask_id": ask_id, "type": item.type, "decision": decision, "note": note,
         "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    )
    _write_record(root, record)
    return outcome


def _decide_candidate(
    root: Path, record: RunRecord, candidate_id: str, decision: str, note: str
) -> dict[str, Any]:
    candidate = promotion.get_candidate(root, candidate_id)
    if candidate is None or candidate.state != "pending":
        raise ValueError(f"no pending candidate: {candidate_id}")
    if decision == "reject":
        promotion.transition_candidate(root, candidate_id, "rejected", note=note)
        return {"state": "rejected", "candidate": candidate_id}
    if decision == "observe":
        _, observation = promotion.return_candidate_to_observation(
            root, candidate_id, note=note
        )
        return {
            "state": "observing",
            "candidate": candidate_id,
            "observation": observation.id,
        }
    result = ledgerlib.apply_write(
        root,
        target=candidate.target,
        anchor=candidate.anchor,
        mode=candidate.mode,
        proposed_text=candidate.proposed_text,
        origin=f"run:{record.id}",
        evidence=candidate.evidence,
        title=candidate.title,
        verified_rule=load_zones(root).zone_for(candidate.target) == "rule",
    )
    if result.state != "applied":
        return {
            "state": result.state,
            "candidate": candidate_id,
            "entry": result.entry_id,
            "error": result.error,
        }
    ledger_entry = result.entry_id
    promotion.transition_candidate(
        root, candidate_id, "promoted", note=note, ledger_entry=ledger_entry
    )
    return {"state": "promoted", "candidate": candidate_id, "entry": ledger_entry}


def _decide_conflict(
    root: Path, record: RunRecord, entry_id: str, decision: str, note: str
) -> dict[str, Any]:
    entry = next((e for e in ledgerlib.list_entries(root) if e.id == entry_id), None)
    if entry is None or entry.state != "held-conflict":
        raise ValueError(f"no held conflict entry: {entry_id}")
    if decision == "approve":
        result = ledgerlib.apply_write(
            root,
            target=entry.target,
            anchor=entry.anchor,
            mode=entry.mode,
            proposed_text=entry.after_text,
            origin=f"run:{record.id}",
            evidence=entry.evidence,
            title=entry.title,
            force=True,
        )
        _set_entry_state(entry, "decided-approved")
        return {"state": result.state, "entry": result.entry_id, "error": result.error}
    _set_entry_state(entry, "rejected", note)
    return {"state": "rejected", "entry": entry_id}


def _decide_rule_change(
    root: Path, record: RunRecord, item: AskItem, decision: str, note: str
) -> dict[str, Any]:
    relpath = item.id.split(":", 1)[1]
    snapshot_path = verified_snapshot_path(root, relpath)
    old_verified = snapshot_path.read_text(encoding="utf-8") if snapshot_path.is_file() else ""
    current = (root / relpath).read_text(encoding="utf-8")
    if decision == "approve":
        update_verified_snapshot(root, relpath, current)
        entry_id = _book_rule_decision(
            root, record, relpath, "rule-approve", old_verified, current, note
        )
        runtime_paths = rebuild_outputs(root)
        scoped = [
            relpath,
            str(snapshot_path.relative_to(root)),
            f"system/ledger/{entry_id}.md",
        ] + [str(p.resolve().relative_to(root)) for p in runtime_paths]
        _git.add(root, scoped)
        _git.commit(root, f"run: approve rule change {relpath}", trailers={"Ledger-Id": entry_id})
        return {"state": "approved", "entry": entry_id}
    # reject: disk goes back to the verified truth
    (root / relpath).write_text(old_verified, encoding="utf-8")
    entry_id = _book_rule_decision(
        root, record, relpath, "rule-reject", current, old_verified, note
    )
    runtime_paths = rebuild_outputs(root)
    scoped = [relpath, f"system/ledger/{entry_id}.md"] + [
        str(p.resolve().relative_to(root)) for p in runtime_paths
    ]
    _git.add(root, scoped)
    _git.commit(root, f"run: reject rule change {relpath}", trailers={"Ledger-Id": entry_id})
    return {"state": "rejected", "entry": entry_id}


# ---------- internals ----------

def list_ask_items(root: Path) -> list[AskItem]:
    """Public read-only view of pending ask items (portal embedding)."""
    return _ask_items(Path(root).resolve())


def _ask_items(root: Path) -> list[AskItem]:
    items: list[AskItem] = []
    for entry in ledgerlib.list_entries(root):
        if entry.state == "held-conflict":
            items.append(
                AskItem(
                    id=entry.id,
                    type="conflict",
                    title=f"冲突:{entry.title or entry.target}",
                    detail=(
                        f"{entry.target} @ {entry.anchor}\n"
                        f"--- 已认证/现状 ---\n{entry.before_text}\n"
                        f"--- 新提议 ---\n{entry.after_text}"
                    ),
                )
            )
    for drift in gate_drifts(root):
        items.append(
            AskItem(
                id=f"rule:{drift.relpath}",
                type="unqualified-change",
                title=f"未建候选卡的规则区变更:{drift.relpath}",
                detail=_diff_text(drift.verified_text, drift.current_text),
            )
        )
    for candidate in promotion.list_candidates(root):
        items.append(
            AskItem(
                id=candidate.id,
                type="candidate",
                title=candidate.title,
                detail=_candidate_review_detail(candidate),
            )
        )
    return items


def _candidate_review_detail(candidate: promotion.Candidate) -> str:
    ground_detail = {
        "repeated": (
            "两个以上独立经历: " + "；".join(candidate.event_ids)
        ),
        "owner-directed": (
            "owner 明确要求长期沉淀: " + candidate.owner_request
        ),
        "high-risk": (
            f"可验证的高风险不变量: {candidate.risk_invariant}；"
            f"失败时: {candidate.risk_failure}"
        ),
    }.get(candidate.ground, f"历史候选依据: {candidate.ground}")
    return (
        f"为什么现在提出:{candidate.source_context}\n"
        f"来源经历:{'；'.join(candidate.event_ids)}\n"
        f"证据指针:{'；'.join(candidate.evidence)}\n"
        f"现有资产对照:{candidate.existing_coverage}\n"
        f"为什么值得成为长期资产:{candidate.asset_fit}\n"
        f"问题:{candidate.problem}\n"
        f"晋升为什么成立:{ground_detail}；{candidate.promotion_rationale}\n"
        f"建议:{candidate.proposal}\n"
        f"适用范围:{candidate.scope}\n"
        f"不适用:{'；'.join(candidate.exclusions)}\n"
        f"写入后的影响:{candidate.expected_effect}\n"
        f"准确写入位置:{candidate.target} @ {candidate.anchor or '(whole file)'} "
        f"[{candidate.mode}]\n"
        f"准确写入内容:\n{candidate.proposed_text}\n"
        f"验证:{candidate.verification}\n"
        f"请你决定:{candidate.decision_question}"
    )


def _certifiable(root: Path) -> list[tuple[str, int, int]]:
    """State files with uncertified changes, oldest certification first."""
    from forge.layout import detect

    out: list[tuple[str, int, int]] = []
    zones = load_zones(root)
    section_dir = detect(root).section_dir
    if not section_dir.is_dir():
        return out
    for path in sorted(section_dir.glob("*.md")):
        relpath = path.relative_to(root).as_posix()
        if zones.zone_for(relpath) == "rule":
            continue
        changed = uncertified_diff(root, relpath)
        if not changed:
            continue
        info = certified_info(root, relpath)
        days = _days_since(info.date) if info else 10**3
        out.append((relpath, days, len(changed)))
    out.sort(key=lambda t: (-t[1], -t[2]))
    return out


def _state_freshness(root: Path) -> list[dict[str, Any]]:
    return [
        {"path": relpath, "days_since_certified": days, "uncertified_changes": changed}
        for relpath, days, changed in _certifiable(root)
    ]


def _diff_text(old: str, new: str) -> str:
    import difflib

    return "\n".join(
        difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2)
    )


def _days_since(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    now = datetime.now(then.tzinfo) if then.tzinfo else datetime.now()
    return max(0, (now - then).days)


def _set_entry_state(entry: ledgerlib.LedgerEntry, state: str, note: str = "") -> None:
    assert entry.path is not None
    text = entry.path.read_text(encoding="utf-8")
    text = re.sub(r"^state: .*$", f"state: {state}", text, count=1, flags=re.MULTILINE)
    if note:
        text += f"\n## Decision note\n\n{note}\n"
    entry.path.write_text(text, encoding="utf-8")


def _book_rule_decision(
    root: Path,
    record: RunRecord,
    relpath: str,
    mode: str,
    before: str,
    after: str,
    note: str,
) -> str:
    entry_id = ledgerlib._new_entry_id(root, f"{mode} {Path(relpath).stem}")
    entry_path = ledgerlib.ledger_dir(root) / f"{entry_id}.md"
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(
        ledgerlib._render_entry(
            entry_id=entry_id,
            title=f"{mode}: {relpath}" + (f" · {note}" if note else ""),
            state="applied",
            origin=f"run:{record.id}",
            target=relpath,
            anchor="",
            mode=mode,
            base_digest="",
            applied_range=None,
            evidence=[],
            before_text=before,
            after_text=after,
        ),
        encoding="utf-8",
    )
    return entry_id


def _records(root: Path) -> list[RunRecord]:
    directory = run_dir(root)
    if not directory.is_dir():
        return []
    out: list[RunRecord] = []
    for path in sorted(directory.glob("run-*.md")):
        text = path.read_text(encoding="utf-8")
        frontmatter = _FRONTMATTER_RE.match(text)
        if frontmatter is None:
            continue
        try:
            fm = yaml.safe_load(frontmatter.group(1)) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict) or fm.get("kind") != "forge-run":
            continue
        out.append(
            RunRecord(
                id=str(fm.get("id") or path.stem),
                status=str(fm.get("status") or ""),
                opened_at=str(fm.get("opened_at") or ""),
                closed_at=str(fm.get("closed_at") or ""),
                inputs=[dict(i) for i in (fm.get("inputs") or [])],
                dispositions=[dict(d) for d in (fm.get("dispositions") or [])],
                decisions=[dict(d) for d in (fm.get("decisions") or [])],
                expired_observations=[str(x) for x in (fm.get("expired_observations") or [])],
                path=path,
            )
        )
    return out


def _write_record(root: Path, record: RunRecord, report: dict[str, Any] | None = None) -> None:
    fm: dict[str, Any] = {
        "kind": "forge-run",
        "id": record.id,
        "status": record.status,
        "opened_at": record.opened_at,
        "closed_at": record.closed_at,
        "inputs": record.inputs,
        "dispositions": record.dispositions,
        "decisions": record.decisions,
        "expired_observations": record.expired_observations,
    }
    body = "# Forge run " + record.id + "\n"
    if report:
        fm["report"] = report
        disposition_text = "、".join(
            f"{kind} {count}" for kind, count in report["dispositions"].items()
        ) or "无"
        body += (
            f"\n结算报告:落账 {report['settled']} 笔 · 裁决 {report['decisions']} 条 "
            f"· {_candidate_summary_text(report)} "
            f"· 完整性问题 {report['integrity_issues']} 条 "
            f"· 输入去向 {disposition_text} "
            f"· 观察中 {report['observing_units']} 条 "
            f"· 观察到期 {report['expired_observations']} 条 "
            f"· 顺延来源 {report['unresolved_sources']} 条 "
            f"· 剩余可筛选单元 {report['unprocessed_review_units']} 条\n"
        )
    path = run_dir(root) / f"{record.id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + body,
        encoding="utf-8",
    )
    record.path = path


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key, "")
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _with_final_facts(
    root: Path,
    report: dict[str, Any],
    current_source_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    source_paths = {
        str(signal.get("path") or "")
        for signal in current_source_signals
        if signal.get("path")
    }
    open_run_id = next((r.id for r in _records(root) if r.status == "open"), None)
    try:
        porcelain = _git.git(root, ["status", "--porcelain"], allow_empty_output=True)
    except Exception:
        porcelain = "<status unavailable>"
    pending_candidates = sum(
        1 for candidate in promotion.list_candidates(root, include_decided=True)
        if candidate.state == "pending"
    )
    observing = sum(
        1 for observation in promotion.list_observations(root, include_closed=True)
        if observation.state == "open"
    )
    selection = _selection_facts(
        root,
        current_source_signals,
        pending_candidates=pending_candidates,
        observing=observing,
    )
    if report.get("unresolved_sources"):
        final_state = "incomplete"
    elif selection["unprocessed_review_units"]:
        final_state = "batch-complete"
    else:
        final_state = "complete"
    report.update(
        {
            "final_state": final_state,
            "open_run": open_run_id,
            "worktree_clean": not bool(porcelain.strip()),
            "remaining_sources": _remaining_source_count(current_source_signals),
            "remaining_source_paths": sorted(source_paths),
            **selection,
        }
    )
    return report


def _candidate_summary_text(report: dict[str, Any]) -> str:
    conclusion = report.get("candidate_conclusion")
    if conclusion == "available":
        return f"候选待审 {report.get('pending_candidates', 0)} 条"
    if conclusion == "unknown":
        return (
            "候选结论 未知"
            f"（{report.get('unprocessed_review_units', 0)} 个可筛选单元尚未处理）"
        )
    observing = int(report.get("observing_units") or 0)
    if observing:
        return f"候选结论 无（筛选完成，观察中 {observing} 条）"
    return "候选结论 无（可筛选单元已处理完）"


def _remaining_source_count(source_signals: list[dict[str, Any]]) -> int:
    """Count concrete remaining inputs, falling back to one per generic signal."""
    return sum(max(1, int(signal.get("total_count") or 0)) for signal in source_signals)
