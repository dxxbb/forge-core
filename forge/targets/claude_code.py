"""Claude Code adapter: produce CLAUDE.md.

Output format:

    # <config.name> · compiled by forge-core

    <provenance header comment>

    <preamble>

    ## <section-1 name>

    <section-1 body>

    ## <section-2 name>

    <section-2 body>

    ...

    <postamble>
    <config body>

Sections are emitted as level-2 headings using the section name. If the
section body already starts with an H1/H2 heading matching the name, the
adapter does NOT duplicate it.
"""

from __future__ import annotations

import re

from forge.targets.base import TargetAdapter
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.compiler.provenance import build_block, render_markdown_header


class ClaudeCodeAdapter(TargetAdapter):
    name = "claude-code"
    default_filename = "CLAUDE.md"

    def render(self, sections: list[Section], config: Config) -> str:
        parts: list[str] = []
        parts.append(f"# {config.name}")
        parts.append("")
        parts.append(
            "<!-- compiled by forge-core. do not edit by hand. "
            "edit sp/section/ and run `forge approve`. -->"
        )
        parts.append(render_markdown_header(build_block(sections, config), "html"))
        parts.append("")
        if config.preamble.strip():
            parts.append(config.preamble.strip())
            parts.append("")
        for sec in sections:
            heading = _section_heading(sec)
            if heading:
                parts.append(heading)
                parts.append("")
            parts.append(sec.body.strip())
            parts.append("")
        if config.postamble.strip():
            parts.append(config.postamble.strip())
            parts.append("")
        if config.body.strip():
            parts.append(config.body.strip())
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"


def _section_heading(sec: Section) -> str:
    """Return `## <name>` unless the body already starts with an H1/H2 on the same topic."""
    body = sec.body.lstrip()
    first_line = body.splitlines()[0] if body else ""
    if re.match(r"^#{1,2}\s", first_line):
        return ""
    pretty = sec.name.replace("-", " ").replace("_", " ")
    return f"## {pretty}"
