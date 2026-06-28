"""Asset zoning + the compile gate.

The run design splits the canonical asset into two zones (see
docs/run-design.md §2.1):

- rule zone: behavior-steering content. Delta-gated — the compiler refuses
  unapproved drift by compiling from the last verified snapshot.
- state zone: informational content. Flows freely, every write ledgered.

Zoning is declared by an owner-held config file (``zones.yaml`` next to the
section/config dirs). Content cannot self-declare its zone; the zones file
itself is always rule-zone.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from forge.layout import detect

ZONES_FILENAME = "zones.yaml"
DEFAULT_RULE_BUDGET_LINES = 150
# Early-warning ratio for the rule-zone budget: compression pressure should
# arrive before the cap does, not when it is already hit.
RULE_BUDGET_WARN_RATIO = 0.87


def rule_budget_warn_threshold(budget: int) -> int:
    """Line count at which the rule-zone budget starts warning (~87% of cap)."""
    return int(budget * RULE_BUDGET_WARN_RATIO)


@dataclass
class Zones:
    root: Path
    exists: bool
    rule_globs: list[str] = field(default_factory=list)
    budget_lines: int = DEFAULT_RULE_BUDGET_LINES
    # Workspace-wide soft budget for compiled outputs (forge/budget.py).
    # None = not configured; per-config `output_budget` frontmatter overrides.
    output_budget_lines: int | None = None
    output_budget_tokens: int | None = None

    @property
    def zones_relpath(self) -> str:
        layout = detect(self.root)
        return (layout.source_root / ZONES_FILENAME).relative_to(self.root).as_posix()

    def zone_for(self, relpath: str | Path) -> str:
        normalized = Path(relpath).as_posix()
        if normalized == self.zones_relpath:
            return "rule"
        for pattern in self.rule_globs:
            if fnmatch.fnmatch(normalized, pattern):
                return "rule"
        return "state"


@dataclass
class GateDrift:
    """A rule-zone file whose content differs from its verified snapshot."""

    relpath: str
    current_text: str
    verified_text: str
    snapshot_missing: bool = False


def zones_path(root: Path) -> Path:
    return detect(Path(root)).source_root / ZONES_FILENAME


def verified_dir(root: Path) -> Path:
    return Path(root) / "system" / "verified"


def verified_snapshot_path(root: Path, relpath: str | Path) -> Path:
    return verified_dir(root) / Path(relpath)


def rule_zone_files(root: Path) -> list[str]:
    """All existing files currently claimed by the rule zone (workspace-relative)."""
    root = Path(root).resolve()
    zones = load_zones(root)
    if not zones.exists:
        return []
    out: set[str] = set()
    for pattern in zones.rule_globs:
        # Globs are workspace-relative; match real files only.
        for path in root.glob(pattern):
            if path.is_file():
                out.add(path.relative_to(root).as_posix())
    zones_file = zones_path(root)
    if zones_file.is_file():
        out.add(zones_file.relative_to(root).as_posix())
    return sorted(out)


def zone_init(root: Path) -> list[str]:
    """Certify the current rule-zone content as the verified baseline.

    Bootstrap step (AC-ZONE-4): until this runs, the gate has no baseline and
    must report itself as inactive rather than silently pretend protection.
    """
    root = Path(root).resolve()
    baselined: list[str] = []
    for relpath in rule_zone_files(root):
        _write_snapshot(root, relpath, (root / relpath).read_text(encoding="utf-8"))
        baselined.append(relpath)
    return baselined


def update_verified_snapshot(root: Path, relpath: str, content: str) -> None:
    """Owner-approved content becomes the new verified baseline for a file."""
    _write_snapshot(Path(root).resolve(), relpath, content)


def gate_initialized(root: Path) -> bool:
    return verified_dir(root).is_dir()


def gate_drifts(root: Path) -> list[GateDrift]:
    """Rule-zone files whose current content departs from the verified baseline."""
    root = Path(root).resolve()
    drifts: list[GateDrift] = []
    for relpath in rule_zone_files(root):
        current = (root / relpath).read_text(encoding="utf-8")
        snapshot = verified_snapshot_path(root, relpath)
        if not snapshot.is_file():
            drifts.append(
                GateDrift(
                    relpath=relpath,
                    current_text=current,
                    verified_text="",
                    snapshot_missing=True,
                )
            )
            continue
        verified = snapshot.read_text(encoding="utf-8")
        if current != verified:
            drifts.append(
                GateDrift(relpath=relpath, current_text=current, verified_text=verified)
            )
    return drifts


def _write_snapshot(root: Path, relpath: str, content: str) -> None:
    snapshot = verified_snapshot_path(root, relpath)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(content, encoding="utf-8")


# ---------- certification (state zone) ----------
#
# Certification is the state-zone counterpart of the rule zone's verified
# snapshot: the owner stamps "this file, as it reads now, is right". Reads
# highlight everything since the stamp; the conflict guard protects only
# certified content (AC-CERT-*, AC-LEDGER-7).

@dataclass
class CertifiedInfo:
    relpath: str
    date: str
    snapshot_path: Path


def certified_dir(root: Path) -> Path:
    return Path(root) / "system" / "certified"


def certified_snapshot_path(root: Path, relpath: str | Path) -> Path:
    return certified_dir(root) / Path(relpath)


def certify(root: Path, relpath: str) -> CertifiedInfo:
    """Stamp the current content of a state file as owner-confirmed."""
    from datetime import datetime

    root = Path(root).resolve()
    content = (root / relpath).read_text(encoding="utf-8")
    snapshot = certified_snapshot_path(root, relpath)
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(content, encoding="utf-8")
    date = datetime.now().astimezone().isoformat(timespec="seconds")
    index = _certified_index(root)
    index[Path(relpath).as_posix()] = date
    _write_certified_index(root, index)
    return CertifiedInfo(relpath=Path(relpath).as_posix(), date=date, snapshot_path=snapshot)


def certified_info(root: Path, relpath: str) -> CertifiedInfo | None:
    root = Path(root).resolve()
    normalized = Path(relpath).as_posix()
    date = _certified_index(root).get(normalized)
    snapshot = certified_snapshot_path(root, normalized)
    if not date or not snapshot.is_file():
        return None
    return CertifiedInfo(relpath=normalized, date=str(date), snapshot_path=snapshot)


def uncertified_diff(root: Path, relpath: str) -> list[str]:
    """Lines that changed since certification (unified-diff body, no headers).

    Empty when unchanged; whole file counts as new when never certified.
    """
    import difflib

    root = Path(root).resolve()
    current = (root / relpath).read_text(encoding="utf-8")
    info = certified_info(root, relpath)
    baseline = info.snapshot_path.read_text(encoding="utf-8") if info else ""
    if baseline == current:
        return []
    diff = difflib.unified_diff(
        baseline.splitlines(), current.splitlines(), lineterm="", n=0
    )
    return [line for line in diff if line and not line.startswith(("---", "+++", "@@"))]


def _certified_index(root: Path) -> dict[str, str]:
    index_path = certified_dir(root) / "index.yaml"
    if not index_path.is_file():
        return {}
    data = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _write_certified_index(root: Path, index: dict[str, str]) -> None:
    index_path = certified_dir(root) / "index.yaml"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        yaml.safe_dump(index, sort_keys=True, allow_unicode=True), encoding="utf-8"
    )


def rule_budget_usage(root: Path) -> tuple[int, int]:
    """(compiled lines used by rule-zone sections, configured budget)."""
    from forge.compiler.section import Section

    root = Path(root).resolve()
    zones = load_zones(root)
    if not zones.exists:
        return 0, zones.budget_lines
    section_dir = detect(root).section_dir
    used = 0
    for relpath in rule_zone_files(root):
        path = root / relpath
        try:
            path.relative_to(section_dir)
        except ValueError:
            continue
        if path.suffix == ".md":
            used += Section.from_file(path).line_count
    return used, zones.budget_lines


def gated_sections(root: Path):
    """Load sections with the compile gate applied (AC-GATE-1).

    Rule-zone section files that drifted from their verified snapshot are
    loaded FROM the snapshot — agents keep reading owner-approved rules no
    matter what was written to disk. Returns ``(sections, drifts)`` so callers
    can surface diagnostics. With no zones config or no baseline the gate is
    inactive and this is exactly ``load_sections`` (AC-ZONE-4: never pretend
    protection that is not there).
    """
    from forge.compiler.loader import load_sections
    from forge.compiler.section import Section

    root = Path(root).resolve()
    sections = load_sections(root)
    zones = load_zones(root)
    if not zones.exists or not gate_initialized(root):
        return sections, []
    drifts = gate_drifts(root)
    section_dir = detect(root).section_dir
    for drift in drifts:
        if drift.snapshot_missing:
            continue
        abs_path = root / drift.relpath
        try:
            abs_path.relative_to(section_dir)
        except ValueError:
            continue  # rule-zone file outside the section dir: no compile effect
        gated = Section.from_file(verified_snapshot_path(root, drift.relpath))
        if gated.name in sections:
            sections[gated.name] = gated
    return sections, drifts


def load_zones(root: Path) -> Zones:
    root = Path(root).resolve()
    path = zones_path(root)
    if not path.is_file():
        return Zones(root=root, exists=False)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"zones config must be a mapping: {path}")
    rule_globs = [str(p) for p in (data.get("rule_zone") or []) if str(p).strip()]
    budget = data.get("budget_lines")
    out_budget = data.get("output_budget") or {}
    if not isinstance(out_budget, dict):
        raise ValueError(f"`output_budget` must be a mapping: {path}")
    return Zones(
        root=root,
        exists=True,
        rule_globs=rule_globs,
        budget_lines=int(budget) if budget else DEFAULT_RULE_BUDGET_LINES,
        output_budget_lines=int(out_budget["lines"]) if out_budget.get("lines") else None,
        output_budget_tokens=int(out_budget["tokens"]) if out_budget.get("tokens") else None,
    )
