"""forge doctor: health-check a workspace.

Checks (severity):

  ERROR   — config references a section name that doesn't exist
  ERROR   — a required_section is not included in the config's sections list
  ERROR   — duplicate section names across sp/section/ files
  WARNING — orphan section (not referenced by any config)
  WARNING — section.kind == 'derived' but upstream is empty
  WARNING — config target references an unregistered adapter
  INFO    — personalOS asset coverage: per-asset-dir count of files referenced
            (in any form: inline, pointer, summary, L2 index) by some section's
            upstream, vs not. Reported, never failed — bridge form is a
            judgment call, not a contract.

INFO lines summarize counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.layout import detect
from forge.targets import available_adapters


# personalOS asset directories that may be referenced by sections. Each is
# treated as a content store the agent might reach via:
#   - inline (section body summarizes / paraphrases the asset)
#   - L1 pointer (section body says "see <path>")
#   - L2 index (section points to an index file that points to assets)
#   - summary (section has a TLDR; asset has the full)
#   - archive-only (intentionally not bridged)
# `forge doctor` reports *coverage* (how many bridged vs not) without judging.
ASSET_DIRS = (
    "assist config",
    "user space",
    "workspace",
    "public knowledge base",
)


@dataclass
class DoctorReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format_lines(self) -> list[str]:
        out: list[str] = []
        for e in self.errors:
            out.append(f"ERROR   {e}")
        for w in self.warnings:
            out.append(f"WARN    {w}")
        for i in self.info:
            out.append(f"INFO    {i}")
        return out


def run(root: Path) -> DoctorReport:
    report = DoctorReport()

    try:
        sections = load_sections(root)
    except ValueError as e:
        # load_sections raises ValueError on duplicates etc. — surface as error
        report.errors.append(f"section load failed: {e}")
        return report

    try:
        configs = load_all_configs(root)
    except ValueError as e:
        report.errors.append(f"config load failed: {e}")
        return report

    report.info.append(f"sections: {len(sections)}")
    report.info.append(f"configs: {len(configs)}")

    adapters = set(available_adapters())

    # Per-config checks
    section_refs: dict[str, set[str]] = {}  # section_name -> set of configs that use it
    for cname, cfg in configs.items():
        if cfg.target not in adapters:
            report.warnings.append(
                f"config `{cname}` target `{cfg.target}` is not a registered adapter "
                f"(available: {sorted(adapters)})"
            )
        for s in cfg.sections:
            section_refs.setdefault(s, set()).add(cname)
            if s not in sections:
                report.errors.append(
                    f"config `{cname}` references unknown section `{s}`"
                )
        # required_sections coverage
        req_missing = [r for r in cfg.required_sections if r not in cfg.sections]
        if req_missing:
            report.errors.append(
                f"config `{cname}` declares required_sections {req_missing} "
                f"but they are not in sections list"
            )
        # also check required sections actually exist as files (could be in sections but undefined)
        req_undefined = [r for r in cfg.required_sections if r not in sections]
        for r in req_undefined:
            if r not in cfg.sections:
                continue  # already reported above as unknown
            report.errors.append(
                f"config `{cname}` requires section `{r}` but no section file defines it"
            )

    # Section-level checks
    for sname, sec in sections.items():
        if sname not in section_refs:
            report.warnings.append(f"section `{sname}` is not referenced by any config (orphan)")
        if sec.kind == "derived" and not sec.upstream:
            report.warnings.append(
                f"section `{sname}` has kind=derived but empty upstream — "
                f"provenance will be weaker"
            )

    # personalOS asset coverage (info-only; bridge form is a judgment call)
    coverage = _asset_coverage(root, sections)
    for line in coverage:
        report.info.append(line)

    return report


def _asset_coverage(root: Path, sections: dict) -> list[str]:
    """Report how many asset files each personalOS dir has bridged via section
    upstream, vs not. No judgment — just visibility.

    Skipped on legacy layouts (no asset directories to walk)."""
    if detect(root).name != "v0428":
        return []

    # Build the set of upstream references across all sections, normalized to
    # workspace-relative posix paths (or just the basename — we accept both
    # ways of writing upstream).
    referenced: set[str] = set()
    for sec in sections.values():
        for u in sec.upstream:
            u = u.strip()
            if not u:
                continue
            referenced.add(u)
            referenced.add(Path(u).name)
            try:
                p = (root / u).resolve()
                if p.is_relative_to(root):
                    referenced.add(p.relative_to(root).as_posix())
            except (OSError, ValueError):
                pass

    out: list[str] = []
    for d in ASSET_DIRS:
        asset_dir = root / d
        if not asset_dir.is_dir():
            continue
        files = [p for p in asset_dir.rglob("*.md") if p.is_file()]
        if not files:
            continue
        bridged = 0
        unbridged: list[str] = []
        for p in files:
            rel = p.relative_to(root).as_posix()
            if rel in referenced or p.name in referenced:
                bridged += 1
            else:
                unbridged.append(rel)
        out.append(f"asset coverage `{d}/`: {bridged}/{len(files)} files bridged via section upstream")
        # Surface up to a few unbridged paths so the user can decide if any
        # need a section bridge or are intentionally archive-only.
        for path in unbridged[:5]:
            out.append(f"  not bridged: {path}")
        if len(unbridged) > 5:
            out.append(f"  ... +{len(unbridged) - 5} more")
    return out
