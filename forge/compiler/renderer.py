"""Renderer: drive a target adapter over (sections, config) to produce output text."""

from __future__ import annotations

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
        ordered.append(sections[sname])
    return adapter.render(ordered, config)
