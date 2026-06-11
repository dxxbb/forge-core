"""The forge run: deterministic backbone of the settlement conversation.

The run is the only governance workflow (docs/run-design.md §2.2): the owner
opens it, the agent settles state updates through the ledger, the CLI produces
a budgeted question list (conflicts -> rule changes -> certifications due),
decisions execute immediately, and close writes the report. Between runs the
system demands nothing from anyone.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from forge import ledger as ledgerlib
from forge.gate import _git
from forge.gate.actions import build as rebuild_outputs
from forge.zone import (
    certified_info,
    certify,
    gate_drifts,
    load_zones,
    uncertified_diff,
    update_verified_snapshot,
    verified_snapshot_path,
)

RUN_DIR = Path("system") / "run"
DEFAULT_BUDGET = 5
CERT_DUE_DAYS = 14


@dataclass
class AskItem:
    id: str
    type: str  # conflict | rule-change | certification-due
    title: str
    detail: str
    deferred: bool = False


@dataclass
class RunRecord:
    id: str
    status: str
    opened_at: str
    closed_at: str
    inputs: list[dict[str, str]] = field(default_factory=list)
    decisions: list[dict[str, str]] = field(default_factory=list)
    path: Path | None = None


def run_dir(root: Path) -> Path:
    return Path(root) / RUN_DIR


# ---------- status ----------

def status(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    records = _records(root)
    closed = [r for r in records if r.status == "closed"]
    last_closed = max((r.closed_at for r in closed), default="")
    items = _ask_items(root)
    freshness = _state_freshness(root)
    return {
        "last_run_closed_at": last_closed or None,
        "days_since_last_run": _days_since(last_closed),
        "open_run": next((r.id for r in records if r.status == "open"), None),
        "ask_counts": {
            t: sum(1 for i in items if i.type == t)
            for t in ("conflict", "rule-change", "certification-due")
        },
        "state_freshness": freshness,
    }


# ---------- open / close ----------

def open_run(root: Path) -> RunRecord:
    """Create the run record, or resume the one still open (AC-RUN-2)."""
    root = Path(root).resolve()
    existing = next((r for r in _records(root) if r.status == "open"), None)
    if existing is not None:
        return existing
    processed = {
        i["digest"] for r in _records(root) for i in r.inputs if i.get("digest")
    }
    inputs: list[dict[str, str]] = []
    capture_root = root / "capture"
    if capture_root.is_dir():
        for path in sorted(capture_root.rglob("*.md")):
            digest = hashlib.sha1(path.read_bytes()).hexdigest()[:16]
            if digest in processed:
                continue
            inputs.append({"path": path.relative_to(root).as_posix(), "digest": digest})
    base_id = "run-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id, n = base_id, 0
    while (run_dir(root) / f"{run_id}.md").exists():
        n += 1
        run_id = f"{base_id}-{n}"
    record = RunRecord(
        id=run_id,
        status="open",
        opened_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        closed_at="",
        inputs=inputs,
    )
    _write_record(root, record)
    return record


def close_run(root: Path) -> dict[str, Any]:
    """Rebuild, report, mark closed, and commit the run's bookkeeping (AC-RUN-6)."""
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")
    rebuild_outputs(root)
    settled = [
        e for e in ledgerlib.list_entries(root) if e.origin == f"run:{record.id}"
    ]
    remaining = _ask_items(root)
    record.status = "closed"
    record.closed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    report = {
        "settled": len(settled),
        "decisions": len(record.decisions),
        "deferred": len(remaining),
        "rule_changes_decided": sum(
            1 for d in record.decisions if d.get("type") == "rule-change"
        ),
    }
    _write_record(root, record, report=report)
    scoped = [str((run_dir(root) / f"{record.id}.md").relative_to(root))]
    scoped += [
        str(e.path.relative_to(root))
        for e in ledgerlib.list_entries(root)
        if e.path is not None and e.state in ("held-conflict", "rejected")
    ]
    try:
        _git.add(root, scoped)
        _git.commit(root, f"run: close {record.id}", trailers={"Run-Id": record.id})
    except Exception:  # noqa: BLE001 — closing must not fail on a no-op commit
        pass
    return report


# ---------- ask / decide ----------

def ask(root: Path, budget: int = DEFAULT_BUDGET) -> list[AskItem]:
    """The budgeted question list, in fixed priority order (AC-RUN-4):
    conflicts (never compressed) -> rule changes -> certifications due."""
    items = _ask_items(root)
    conflicts = [i for i in items if i.type == "conflict"]
    rest = [i for i in items if i.type != "conflict"]
    allowed = max(0, budget - len(conflicts))
    for idx, item in enumerate(rest):
        item.deferred = idx >= allowed
    return conflicts + rest


def decide(root: Path, ask_id: str, decision: str, note: str = "") -> dict[str, Any]:
    """Execute one owner decision immediately (AC-RUN-5)."""
    root = Path(root).resolve()
    record = next((r for r in _records(root) if r.status == "open"), None)
    if record is None:
        raise RuntimeError("no open run — `forge run open` first")
    item = next((i for i in _ask_items(root) if i.id == ask_id), None)
    if item is None:
        raise ValueError(f"unknown ask item: {ask_id}")
    if decision not in ("approve", "reject"):
        raise ValueError(f"decision must be approve|reject, got {decision!r}")

    if item.type == "conflict":
        outcome = _decide_conflict(root, record, ask_id, decision, note)
    elif item.type == "rule-change":
        outcome = _decide_rule_change(root, record, item, decision, note)
    else:
        outcome = _decide_certification(root, record, item, decision)

    record.decisions.append(
        {"ask_id": ask_id, "type": item.type, "decision": decision, "note": note,
         "at": datetime.now().astimezone().isoformat(timespec="seconds")}
    )
    _write_record(root, record)
    return outcome


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


def _decide_certification(
    root: Path, record: RunRecord, item: AskItem, decision: str
) -> dict[str, Any]:
    relpath = item.id.split(":", 1)[1]
    if decision != "approve":
        return {"state": "skipped", "relpath": relpath}
    info = certify(root, relpath)
    scoped = [
        str(info.snapshot_path.relative_to(root)),
        "system/certified/index.yaml",
    ]
    _git.add(root, scoped)
    _git.commit(root, f"run: certify {relpath}", trailers={"Run-Id": record.id})
    return {"state": "certified", "relpath": relpath, "date": info.date}


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
                type="rule-change",
                title=f"规则区变更:{drift.relpath}",
                detail=_diff_text(drift.verified_text, drift.current_text),
            )
        )
    zones = load_zones(root)
    if zones.exists:
        for relpath, days, changed in _certifiable(root):
            # Only files the owner has certified at least once enter the ask
            # budget; never-certified files surface in status freshness but do
            # not nag — certification starts at the owner's first stamp.
            if certified_info(root, relpath) is None:
                continue
            items.append(
                AskItem(
                    id=f"cert:{relpath}",
                    type="certification-due",
                    title=f"待认证:{relpath}({days} 天,{changed} 处变更)",
                    detail="\n".join(uncertified_diff(root, relpath)[:20]),
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
        if not text.startswith("---"):
            continue
        parts = text.split("---", 2)
        if len(parts) < 3:
            continue
        try:
            fm = yaml.safe_load(parts[1]) or {}
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
                decisions=[dict(d) for d in (fm.get("decisions") or [])],
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
        "decisions": record.decisions,
    }
    body = "# Forge run " + record.id + "\n"
    if report:
        body += (
            f"\n结算报告:落账 {report['settled']} 笔 · 裁决 {report['decisions']} 条 "
            f"· 顺延 {report['deferred']} 条\n"
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
