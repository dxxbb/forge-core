"""Renderer: drive a target adapter over (sections, config) to produce output text."""

from __future__ import annotations

import re
from dataclasses import replace

from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.targets import get_adapter


def render(sections: dict[str, Section], config: Config) -> str:
    """Render the compiled output for a single config.

    Looks up the adapter by config.target and delegates.
    Raises KeyError if a referenced section is missing.
    """
    adapter = get_adapter(config.target)
    ordered: list[Section] = []
    for sname in config.sections:
        if sname not in sections:
            raise KeyError(
                f"config `{config.name}` references unknown section `{sname}` "
                f"(available: {sorted(sections.keys())})"
            )
        section = sections[sname]
        if sname in config.section_views:
            section = _apply_section_view(section, config.section_views[sname], config.name)
        ordered.append(section)
    return adapter.render(ordered, config)


def _apply_section_view(section: Section, view: dict, config_name: str) -> Section:
    mode = str(view.get("mode") or "full")
    if mode == "full":
        return section
    if mode == "marked":
        marker = str(view.get("marker") or "runtime")
        body = _extract_marked_view(section.body, marker, section.name, config_name)
        return replace(section, body=body)
    raise ValueError(
        f"config `{config_name}` section `{section.name}` has unsupported "
        f"view mode `{mode}`"
    )


def _extract_marked_view(body: str, marker: str, section_name: str, config_name: str) -> str:
    escaped = re.escape(marker)
    pattern = re.compile(
        rf"^[ \t]*<!--\s*forge:view\s+{escaped}\s+begin\s*-->[ \t]*\n"
        rf"(?P<body>.*?)"
        rf"^[ \t]*<!--\s*forge:view\s+{escaped}\s+end\s*-->[ \t]*$",
        re.MULTILINE | re.DOTALL,
    )
    matches = list(pattern.finditer(body))
    if not matches:
        raise ValueError(
            f"config `{config_name}` section `{section_name}` requested marked "
            f"view `{marker}`, but no matching forge:view begin/end block exists"
        )
    if len(matches) > 1:
        raise ValueError(
            f"config `{config_name}` section `{section_name}` requested marked "
            f"view `{marker}`, but {len(matches)} blocks exist"
        )
    return matches[0].group("body").strip()
