"""Claude Code adapter：产出 CLAUDE.md。

产物结构：

    <可选 output_frontmatter YAML>

    # <config.name>

    <!-- forge-core provenance 注释块 -->

    ## <section-1 name>
    <section-1 body>

    ## <section-2 name>
    <section-2 body>

    ...

每段 section 以 `## <name>` 作为 heading emit。如果开启 demote_section_headings，
section body 自带的 leading heading 会被 strip，其他 heading 全部降一级。

注意 v0.2 后：Config 不再接 preamble / postamble / body。要在产物开头或结尾
加文字，请写成一个独立的 section 并挂进 `sections:` 列表。
"""

from __future__ import annotations

import re

import yaml

from forge import __version__
from forge.targets.base import TargetAdapter
from forge.compiler.section import Section
from forge.compiler.config import Config
from forge.compiler.provenance import build_block, render_markdown_header


def _emit_output_frontmatter(user_fm: dict) -> str:
    """Return deterministic YAML frontmatter with user fields + stable generator."""
    merged: dict = dict(user_fm)
    # Always inject (do not override user-provided values)
    merged.setdefault("generated_by", f"forge-core@{__version__}")
    dumped = yaml.safe_dump(merged, sort_keys=False, allow_unicode=True).rstrip()
    return f"---\n{dumped}\n---"


class ClaudeCodeAdapter(TargetAdapter):
    name = "claude-code"
    default_filename = "CLAUDE.md"

    def render(self, sections: list[Section], config: Config) -> str:
        parts: list[str] = []
        if config.output_frontmatter:
            parts.append(_emit_output_frontmatter(config.output_frontmatter))
            parts.append("")
        parts.append(f"# {config.name}")
        parts.append("")
        parts.append(
            "<!-- compiled by forge-core. do not edit by hand. "
            "edit sp/section/ and run `forge approve`. -->"
        )
        parts.append(render_markdown_header(build_block(sections, config), "html"))
        parts.append("")
        for sec in sections:
            if sec.type == "wrapper":
                # wrapper 类型：原样输出 body，不加 heading、不做 demote。
                # 用来承载前言 / 结语 / 分隔文字之类"不是主体 section"的内容。
                parts.append(sec.body.strip())
                parts.append("")
                continue
            parts.append(_section_heading(sec))
            parts.append("")
            body = sec.body.strip()
            if config.demote_section_headings:
                body = _demote_headings(body)
            parts.append(body)
            parts.append("")
        return "\n".join(parts).rstrip() + "\n"


def _section_heading(sec: Section) -> str:
    """Always emit `## <name>` as the section boundary.

    If the section body itself starts with an H1, we still emit our H2 first; the
    body's H1 then becomes a sub-heading. Predictable structure > clever dedup.
    Callers can also enable config.demote_section_headings to shift all body
    headings down one level.
    """
    pretty = sec.name.replace("-", " ").replace("_", " ")
    pretty = pretty[0].upper() + pretty[1:] if pretty else pretty
    return f"## {pretty}"


def _demote_headings(text: str) -> str:
    """Normalize a section body so it fits cleanly under forge's `## <name>` wrapper.

    Two transforms (in order):
    1. If the body starts with an ATX heading (after leading blank lines), STRIP
       it — it's semantically redundant with the adapter's own section heading.
    2. Demote every remaining ATX heading down one level (# → ##, ## → ###, …).

    Matches the pipeline dxyOS previously used (confirmed by diff of
    pre-migration CLAUDE.md against section files).
    """
    lines = text.splitlines()
    # 1) strip leading heading if the body opens with one
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and re.match(r"^#{1,5}\s", lines[i]):
        lines = lines[:i] + lines[i + 1 :]
        # also drop the blank immediately after, if any
        if i < len(lines) and not lines[i].strip():
            lines = lines[:i] + lines[i + 1 :]
    # 2) demote everything that's still a heading
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,5})(\s)", line)
        if m:
            out.append(m.group(1) + "#" + line[len(m.group(1)) :])
        else:
            out.append(line)
    return "\n".join(out).lstrip("\n")
