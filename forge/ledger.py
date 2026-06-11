"""The ledger: every canonical write recorded, scoped-committed, revertible.

One write -> one entry (``system/ledger/<id>.md``) -> one scoped commit carrying
a ``Ledger-Id:`` trailer. The entry stores the before/after block so a single
write can be reverted without archaeology, and ``blame`` can answer "why is
this line here". See docs/run-design.md §2.3 / §4.2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from forge import patch as patchlib
from forge.gate import _git
from forge.gate.actions import build as rebuild_outputs

LEDGER_DIR = Path("system") / "ledger"


@dataclass
class ApplyResult:
    entry_id: str
    state: str  # applied | stale | failed
    commit: str | None = None
    error: str = ""


@dataclass
class LedgerEntry:
    id: str
    title: str
    state: str
    created_at: str
    origin: str
    target: str
    anchor: str
    mode: str
    base_digest: str
    applied_range: tuple[int, int] | None
    evidence: list[str] = field(default_factory=list)
    before_text: str = ""
    after_text: str = ""
    path: Path | None = None


def ledger_dir(root: Path) -> Path:
    return Path(root) / LEDGER_DIR


def apply_write(
    root: Path,
    *,
    target: str,
    proposed_text: str,
    origin: str,
    anchor: str = "",
    mode: str = "replace",
    evidence: list[str] | None = None,
    title: str = "",
    base_digest: str | None = None,
    force: bool = False,
) -> ApplyResult:
    """Write one block into a canonical file through the full pipeline:

    stale check -> apply -> rebuild runtime -> scoped commit (target + runtime
    + the entry itself). All-or-nothing: any failure restores every written
    byte (AC-LEDGER-5).
    """
    root = Path(root).resolve()
    target_path = root / target
    entry_id = _new_entry_id(root, title or Path(target).stem)

    # -- prepare new content (no writes yet) --
    if mode == "create":
        if target_path.exists():
            return ApplyResult(entry_id, "failed", error=f"target already exists: {target}")
        before_block, current_text = "", ""
        new_text = patchlib.apply_patch("", anchor="", mode="create", proposed_text=proposed_text)
    else:
        if not target_path.is_file():
            return ApplyResult(entry_id, "failed", error=f"target missing: {target}")
        current_text = target_path.read_text(encoding="utf-8")
        if mode == "replace" and anchor:
            block = patchlib.extract_block(current_text, anchor)
            if block is None:
                return ApplyResult(entry_id, "failed", error=f"anchor not located: {anchor!r}")
            if base_digest and patchlib.block_digest(block) != base_digest:
                return ApplyResult(
                    entry_id, "stale",
                    error="base digest drifted: target block changed since the patch was drafted",
                )
            before_block = block
        else:
            before_block = ""
        try:
            new_text = patchlib.apply_patch(
                current_text, anchor=anchor, mode=mode, proposed_text=proposed_text
            )
        except ValueError as e:
            return ApplyResult(entry_id, "failed", error=str(e))

    # Conflict guard (AC-LEDGER-7): certified truth is never silently
    # rewritten. A write that drops certified lines is held for the next run;
    # purely additive updates keep flowing (AC-CERT-3).
    if mode == "replace" and anchor and not force:
        conflict = _conflict_with_certified(root, target, anchor, proposed_text)
        if conflict:
            entry_path = ledger_dir(root) / f"{entry_id}.md"
            entry_path.parent.mkdir(parents=True, exist_ok=True)
            entry_path.write_text(
                _render_entry(
                    entry_id=entry_id,
                    title=title or target,
                    state="held-conflict",
                    origin=origin,
                    target=target,
                    anchor=anchor,
                    mode=mode,
                    base_digest=base_digest or patchlib.block_digest(before_block),
                    applied_range=None,
                    evidence=evidence or [],
                    before_text=before_block,
                    after_text=proposed_text.rstrip("\n"),
                ),
                encoding="utf-8",
            )
            return ApplyResult(entry_id, "held", error=conflict)

    applied_range = _applied_range(new_text, current_text, anchor, mode, proposed_text)

    # -- write phase, rolled back wholesale on any failure --
    written: dict[Path, str | None] = {}  # path -> original content (None = did not exist)
    try:
        _record_original(written, target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(new_text, encoding="utf-8")

        runtime_paths = [p for p in rebuild_outputs(root)]

        entry_path = ledger_dir(root) / f"{entry_id}.md"
        _record_original(written, entry_path)
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(
            _render_entry(
                entry_id=entry_id,
                title=title or target,
                state="applied",
                origin=origin,
                target=target,
                anchor=anchor,
                mode=mode,
                base_digest=base_digest or (patchlib.block_digest(before_block) if before_block else ""),
                applied_range=applied_range,
                evidence=evidence or [],
                before_text=before_block,
                after_text=proposed_text.rstrip("\n"),
            ),
            encoding="utf-8",
        )

        scoped = [target, str(entry_path.relative_to(root))]
        scoped += [str(p.resolve().relative_to(root)) for p in runtime_paths]
        _git.add(root, scoped)
        sha = _git.commit(
            root,
            f"ledger: {title or target}",
            trailers={"Ledger-Id": entry_id},
        )
        return ApplyResult(entry_id, "applied", commit=sha)
    except Exception as e:  # noqa: BLE001 — atomicity boundary: restore everything
        for path, original in written.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original, encoding="utf-8")
        try:
            rebuild_outputs(root)
        except Exception:  # noqa: BLE001 — best-effort runtime restore
            pass
        return ApplyResult(entry_id, "failed", error=str(e))


def revert(root: Path, entry_id: str) -> ApplyResult:
    """Reverse one applied entry (AC-LEDGER-6). Refuses on drifted content."""
    root = Path(root).resolve()
    entry = next((e for e in list_entries(root) if e.id == entry_id), None)
    if entry is None:
        return ApplyResult(entry_id, "failed", error=f"entry not found: {entry_id}")
    if entry.state != "applied":
        return ApplyResult(entry_id, "failed", error=f"entry is {entry.state}, not applied")
    target_path = root / entry.target
    if not target_path.is_file():
        return ApplyResult(entry_id, "failed", error=f"target missing: {entry.target}")
    text = target_path.read_text(encoding="utf-8")
    if not entry.after_text or entry.after_text not in text:
        return ApplyResult(
            entry_id, "failed",
            error="entry's written block no longer present verbatim — refusing to guess a revert",
        )
    new_text = text.replace(entry.after_text, entry.before_text, 1)
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)

    revert_id = _new_entry_id(root, f"revert {entry.title or entry.target}")
    written: dict[Path, str | None] = {}
    try:
        _record_original(written, target_path)
        target_path.write_text(new_text, encoding="utf-8")

        _record_original(written, entry.path)  # type: ignore[arg-type]
        entry.path.write_text(  # type: ignore[union-attr]
            entry.path.read_text(encoding="utf-8").replace(  # type: ignore[union-attr]
                "state: applied", "state: reverted", 1
            ),
            encoding="utf-8",
        )

        runtime_paths = rebuild_outputs(root)

        revert_path = ledger_dir(root) / f"{revert_id}.md"
        _record_original(written, revert_path)
        revert_path.write_text(
            _render_entry(
                entry_id=revert_id,
                title=f"revert: {entry.title or entry.target}",
                state="applied",
                origin=f"revert:{entry_id}",
                target=entry.target,
                anchor=entry.anchor,
                mode="revert",
                base_digest=patchlib.block_digest(entry.after_text),
                applied_range=None,
                evidence=[f"system/ledger/{entry_id}.md"],
                before_text=entry.after_text,
                after_text=entry.before_text,
            ),
            encoding="utf-8",
        )

        scoped = [
            entry.target,
            str(revert_path.relative_to(root)),
            str(entry.path.relative_to(root)),  # type: ignore[union-attr]
        ] + [str(p.resolve().relative_to(root)) for p in runtime_paths]
        _git.add(root, scoped)
        sha = _git.commit(
            root, f"ledger: revert {entry_id}", trailers={"Ledger-Id": revert_id}
        )
        return ApplyResult(revert_id, "applied", commit=sha)
    except Exception as e:  # noqa: BLE001 — atomicity boundary
        for path, original in written.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original, encoding="utf-8")
        return ApplyResult(revert_id, "failed", error=str(e))


def blame(root: Path, target: str, line_no: int) -> LedgerEntry | None:
    """Which write produced this line (AC-LEDGER-8)? Newest match wins."""
    root = Path(root).resolve()
    target_path = root / target
    if not target_path.is_file():
        return None
    lines = target_path.read_text(encoding="utf-8").splitlines()
    if not (1 <= line_no <= len(lines)):
        return None
    content = lines[line_no - 1].strip()
    entries = sorted(
        (e for e in list_entries(root) if e.target == target and e.state == "applied"),
        key=lambda e: e.id,
        reverse=True,
    )
    if content:
        for entry in entries:
            if content in entry.after_text:
                return entry
    for entry in entries:
        if entry.applied_range and entry.applied_range[0] <= line_no <= entry.applied_range[1]:
            return entry
    return None


@dataclass
class ReconcileReport:
    ledgered: list[str] = field(default_factory=list)
    rule_drifts: list[str] = field(default_factory=list)


# Canonical content roots eligible for reconcile booking. Build products,
# ledger/run records, and .forge internals are never booked.
_RECONCILE_PREFIXES = (
    "context build/sections/",
    "context build/config/",
    "assist config/",
    "user space/",
    "public knowledge base/",
    "workbench/",
    "capture/",
)

# Never booked: ledger entries copy file content, and private/secret material
# must not be duplicated into system/ledger.
_RECONCILE_EXCLUDES = ("user space/private/",)


def reconcile(root: Path) -> ReconcileReport:
    """Book out-of-band edits (AC-LEDGER-3).

    State-zone working-tree changes become manual-reconciled entries with their
    own scoped commits; rule-zone drift is reported, never auto-booked — the
    compile gate owns that path.
    """
    from forge.zone import load_zones

    root = Path(root).resolve()
    report = ReconcileReport()
    zones = load_zones(root)
    status = _git.git(root, ["status", "--porcelain"], allow_empty_output=True)
    relpaths: list[str] = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        relpath = line[3:].strip().strip('"')
        if (
            any(relpath.startswith(p) for p in _RECONCILE_PREFIXES)
            and not relpath.startswith("context build/runtime/")
            and not any(relpath.startswith(p) for p in _RECONCILE_EXCLUDES)
        ):
            relpaths.append(relpath)
    for relpath in sorted(set(relpaths)):
        if zones.zone_for(relpath) == "rule":
            report.rule_drifts.append(relpath)
            continue
        path = root / relpath
        if not path.is_file():
            continue
        after = path.read_text(encoding="utf-8")
        try:
            before = _git.show_at_ref(root, "HEAD", relpath)
        except Exception:  # noqa: BLE001 — untracked file has no HEAD version
            before = ""
        if before == after:
            continue
        entry_id = _new_entry_id(root, f"reconcile {Path(relpath).stem}")
        entry_path = ledger_dir(root) / f"{entry_id}.md"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        entry_path.write_text(
            _render_entry(
                entry_id=entry_id,
                title=f"reconcile: {relpath}",
                state="applied",
                origin="manual-reconciled",
                target=relpath,
                anchor="",
                mode="file",
                base_digest=patchlib.block_digest(before),
                applied_range=None,
                evidence=[],
                before_text=before,
                after_text=after,
            ),
            encoding="utf-8",
        )
        runtime_paths = rebuild_outputs(root)
        scoped = [relpath, str(entry_path.relative_to(root))] + [
            str(p.resolve().relative_to(root)) for p in runtime_paths
        ]
        _git.add(root, scoped)
        _git.commit(root, f"ledger: reconcile {relpath}", trailers={"Ledger-Id": entry_id})
        report.ledgered.append(relpath)
    return report


def list_entries(root: Path) -> list[LedgerEntry]:
    root = Path(root).resolve()
    out: list[LedgerEntry] = []
    directory = ledger_dir(root)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("led-*.md")):
        entry = _parse_entry(path)
        if entry is not None:
            out.append(entry)
    return out


# ---------- internals ----------

def _conflict_with_certified(root: Path, target: str, anchor: str, proposed_text: str) -> str:
    """Non-empty reason when the write drops owner-certified lines."""
    from forge.zone import certified_info

    info = certified_info(root, target)
    if info is None:
        return ""
    cert_block = patchlib.extract_block(
        info.snapshot_path.read_text(encoding="utf-8"), anchor
    )
    if cert_block is None:
        return ""
    proposed_lines = {ln.strip() for ln in proposed_text.splitlines() if ln.strip()}
    missing = [
        ln.strip()
        for ln in cert_block.splitlines()
        if ln.strip() and ln.strip() not in proposed_lines
    ]
    if missing:
        return (
            f"write contradicts certified content (drops {len(missing)} certified "
            f"line(s), e.g. {missing[0]!r}); held for the next forge run"
        )
    return ""


def _record_original(written: dict[Path, str | None], path: Path) -> None:
    if path not in written:
        written[path] = path.read_text(encoding="utf-8") if path.is_file() else None


def _applied_range(
    new_text: str, old_text: str, anchor: str, mode: str, proposed_text: str
) -> tuple[int, int] | None:
    proposed_lines = proposed_text.rstrip("\n").split("\n")
    if mode == "replace" and anchor:
        located = patchlib.anchored_block(old_text, anchor)
        if located is None:
            return None
        start = located[0]
        return start, start + len(proposed_lines) - 1
    if mode in ("append", "replace"):
        old_count = len(old_text.rstrip("\n").splitlines()) if old_text.strip() else 0
        start = old_count + (2 if old_count else 1)  # blank separator line
        return start, start + len(proposed_lines) - 1
    if mode == "create":
        return 1, len(proposed_lines)
    return None


def _slugify(text: str) -> str:
    # ASCII-only ids: git quotepath / URLs / grep all stay friendly.
    # The human-readable (possibly Chinese) title lives in the frontmatter.
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (slug or "entry")[:48]


def _new_entry_id(root: Path, title: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"led-{stamp}-{_slugify(title)}"
    candidate, n = base, 0
    while (ledger_dir(root) / f"{candidate}.md").exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def _render_entry(
    *,
    entry_id: str,
    title: str,
    state: str,
    origin: str,
    target: str,
    anchor: str,
    mode: str,
    base_digest: str,
    applied_range: tuple[int, int] | None,
    evidence: list[str],
    before_text: str,
    after_text: str,
) -> str:
    fm: dict[str, Any] = {
        "kind": "ledger-entry",
        "id": entry_id,
        "title": title,
        "state": state,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "origin": origin,
        "patch": {
            "target": target,
            "anchor": anchor,
            "mode": mode,
            "base_digest": base_digest,
            "applied_range": list(applied_range) if applied_range else None,
        },
        "evidence": evidence,
    }
    return (
        "---\n"
        + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).strip()
        + "\n---\n\n"
        + "## Before\n\n```text\n" + (before_text or "(empty)") + "\n```\n\n"
        + "## After\n\n```text\n" + (after_text or "(empty)") + "\n```\n"
    )


_FENCE_RE = re.compile(r"## (Before|After)\n\n```text\n(.*?)\n```", re.DOTALL)


def _parse_entry(path: Path) -> LedgerEntry | None:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict) or fm.get("kind") != "ledger-entry":
        return None
    patch = fm.get("patch") or {}
    blocks = {m.group(1): m.group(2) for m in _FENCE_RE.finditer(text)}
    rng = patch.get("applied_range")
    return LedgerEntry(
        id=str(fm.get("id") or path.stem),
        title=str(fm.get("title") or ""),
        state=str(fm.get("state") or ""),
        created_at=str(fm.get("created_at") or ""),
        origin=str(fm.get("origin") or ""),
        target=str(patch.get("target") or ""),
        anchor=str(patch.get("anchor") or ""),
        mode=str(patch.get("mode") or ""),
        base_digest=str(patch.get("base_digest") or ""),
        applied_range=(int(rng[0]), int(rng[1])) if rng else None,
        evidence=[str(x) for x in (fm.get("evidence") or [])],
        before_text="" if blocks.get("Before") == "(empty)" else blocks.get("Before", ""),
        after_text="" if blocks.get("After") == "(empty)" else blocks.get("After", ""),
        path=path,
    )
