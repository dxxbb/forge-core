"""forge doctor: health-check a workspace.

Checks (severity):

  ERROR   — config references a section name that doesn't exist
  ERROR   — a required_section is not included in the config's sections list
  ERROR   — duplicate section names across sp/section/ files
  WARNING — orphan section (not referenced by any config)
  WARNING — section.kind == 'derived' but upstream is empty
  WARNING — config target references an unregistered adapter

INFO lines summarize counts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.targets import available_adapters


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

    return report
