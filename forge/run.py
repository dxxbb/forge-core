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
    source_signal_counts: dict[str, int] = {}
    for signal in signals:
        kind = signal.get("path", "").removeprefix("source://")
        if kind:
            source_signal_counts[kind] = source_signal_counts.get(kind, 0) + 1
    return {
        "last_run_closed_at": last_closed or None,
        "days_since_last_run": _days_since(last_closed),
        "open_run": next((r.id for r in records if r.status == "open"), None),
        "source_attention": bool(signals),
        "source_signal_counts": source_signal_counts,
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
    processed = {
        i["digest"] for r in _records(root) for i in r.inputs if i.get("digest")
    }
    inputs: list[dict[str, Any]] = []
    capture_root = root / "capture"
    if capture_root.is_dir():
        for path in sorted(capture_root.rglob("*.md")):
            if _is_provider_managed_capture(root, path):
                continue
            digest = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
            if digest in processed:
                continue
            inputs.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "digest": digest,
                    "type": "capture-evidence",
                }
            )
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
    classified = {d.get("input_digest") for d in record.dispositions}
    unclassified = [i for i in record.inputs if i.get("digest") not in classified]
    if unclassified:
        paths = ", ".join(i.get("path", "") for i in unclassified[:3])
        raise RuntimeError(f"unclassified input(s): {paths}")
    current_signals_by_path = {
        signal.get("path", ""): signal for signal in (current_source_signals or [])
    }
    disposition_by_digest = {
        d.get("input_digest", ""): d for d in record.dispositions
    }
    unresolved_sources: list[str] = []
    for item in record.inputs:
        if item.get("type") != "source-signal":
            continue
        current_signal = current_signals_by_path.get(item.get("path", ""))
        if current_signal is None:
            continue
        disposition = disposition_by_digest.get(item.get("digest", ""), {})
        if disposition.get("kind") == "defer":
            unresolved_sources.append(item.get("path", ""))
            continue
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
    record.status = "closed"
    record.closed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "empty": False,
        "settled": len(settled),
        "decisions": len(record.decisions),
        "deferred": len(remaining),
        "pending_candidates": sum(1 for item in remaining if item.type == "candidate"),
        "integrity_issues": sum(
            1 for item in remaining if item.type in {"conflict", "unqualified-change"}
        ),
        "rule_changes_decided": sum(
            1 for d in record.decisions if d.get("type") == "unqualified-change"
        ),
        "dispositions": _count_by(record.dispositions, "kind"),
        "expired_observations": len(record.expired_observations),
        "unresolved_sources": len(unresolved_sources),
        "remaining_sources": _remaining_source_count(current_source_signals or []),
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
        _git.commit(root, f"run: close {record.id}", trailers={"Run-Id": record.id})
    except Exception as exc:  # noqa: BLE001 — restore resumable run state, then fail loud
        try:
            _git.git(root, ["reset", "--", *scoped], allow_empty_output=True)
        except Exception:
            pass
        record.status = "open"
        record.closed_at = ""
        _write_record(root, record)
        raise RuntimeError(f"failed to commit run close {record.id}: {exc}") from exc
    final_signals = (
        refresh_source_signals()
        if refresh_source_signals is not None
        else (current_source_signals or [])
    )
    return _with_final_facts(root, report, final_signals)


def record_disposition(
    root: Path,
    input_ref: str,
    kind: str,
    *,
    sink: str = "",
    note: str = "",
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
    item = next(
        (
            i
            for i in record.inputs
            if i.get("path") == input_ref or i.get("digest") == input_ref
        ),
        None,
    )
    if item is None:
        raise ValueError(f"input not found in open run: {input_ref}")
    if kind == "defer" and item.get("type") != "source-signal":
        raise ValueError("defer is only valid for a source signal")
    if kind in {"covered", "one-off", "volatile-state"} and not sink.strip():
        raise ValueError(f"{kind} disposition requires a concrete sink")
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
    if item.get("type") == "source-signal" and kind != "defer":
        settlement = _settle_source_batch(
            root,
            item,
            disposition_kind=kind,
            sink=sink.strip(),
        )
        if settlement["items"]:
            disposition["source_settled"] = True
            disposition["settled_items"] = settlement["items"]
            disposition["settled_paths"] = settlement["paths"]
    record.dispositions = [
        d for d in record.dispositions if d.get("input_digest") != item["digest"]
    ]
    record.dispositions.append(disposition)
    _write_record(root, record)
    return disposition


def _settle_source_batch(
    root: Path,
    item: dict[str, Any],
    *,
    disposition_kind: str,
    sink: str,
) -> dict[str, list[str]]:
    source_kind = _source_kind(item)
    if source_kind == "agent-memory" and item.get("batch_items"):
        from forge.governance.claude_memory import settle_run_source_batch

        items = settle_run_source_batch(root, list(item.get("batch_items") or []))
        return {"items": items, "paths": []}
    if source_kind == "web-clipping" and item.get("batch_items"):
        from forge.governance.web_clipping import settle_run_source_batch

        paths = settle_run_source_batch(
            root,
            list(item.get("batch_items") or []),
            disposition_kind=disposition_kind,
            sink=sink,
            at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        return {"items": paths, "paths": paths}
    return {"items": [], "paths": []}


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
            "ask_id": item.id,
            "ask_type": item.type,
            "title": item.title,
            "detail": item.detail,
            "constraints": ["present this one decision to the owner"],
        }

    classified = {d.get("input_digest") for d in record.dispositions}
    unclassified = [
        item for item in record.inputs if item.get("digest") not in classified
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
        return {
            "run_id": record.id,
            "action": "classify-source",
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
            "ask_id": item.id,
            "ask_type": item.type,
            "title": item.title,
            "detail": item.detail,
            "review_budget_remaining": candidate_budget,
            "constraints": ["present this one candidate card to the owner"],
        }

    return {
        "run_id": record.id,
        "action": "close",
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


def _source_constraints(kind: str) -> list[str]:
    if kind == "agent-memory":
        return [
            "inspect only the listed batch items",
            "do not invoke another workflow without explicit owner request",
            "record exactly one disposition for this batch",
        ]
    if kind == "web-clipping":
        return [
            "check existing canonical sinks before creating new knowledge",
            "do not invoke deep knowledge intake without explicit owner request",
            "record exactly one disposition for this batch",
        ]
    return ["record exactly one disposition for this source"]


def _is_provider_managed_capture(root: Path, path: Path) -> bool:
    """Avoid presenting one source through both a batch and raw capture input."""
    try:
        relpath = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False
    return relpath.startswith("capture/web clipping/")


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
        exclusions = "；".join(candidate.exclusions)
        items.append(
            AskItem(
                id=candidate.id,
                type="candidate",
                title=candidate.title,
                detail=(
                    f"问题:{candidate.problem}\n"
                    f"建议:{candidate.proposal}\n"
                    f"适用范围:{candidate.scope}\n"
                    f"不适用:{exclusions}\n"
                    f"目标:{candidate.target} @ {candidate.anchor or '(whole file)'}\n"
                    f"验证:{candidate.verification}"
                ),
            )
        )
    return items


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
        disposition_text = "、".join(
            f"{kind} {count}" for kind, count in report["dispositions"].items()
        ) or "无"
        body += (
            f"\n结算报告:落账 {report['settled']} 笔 · 裁决 {report['decisions']} 条 "
            f"· 候选待下轮 {report['pending_candidates']} 条 "
            f"· 完整性问题 {report['integrity_issues']} 条 "
            f"· 输入去向 {disposition_text} "
            f"· 观察到期 {report['expired_observations']} 条 "
            f"· 顺延来源 {report['unresolved_sources']} 条 "
            f"· 剩余来源 {report['remaining_sources']} 条\n"
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
    if report.get("unresolved_sources"):
        final_state = "incomplete"
    elif source_paths:
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
        }
    )
    return report


def _remaining_source_count(source_signals: list[dict[str, Any]]) -> int:
    """Count concrete remaining inputs, falling back to one per generic signal."""
    return sum(max(1, int(signal.get("total_count") or 0)) for signal in source_signals)
