"""Read context sources, dump or emit. NO LLM call.

forge runs inside an agent (Claude Code, Codex, etc.) — the agent IS the LLM.
forge shouldn't shell out to a separate API for classification. The agent
calls `forge ingest --emit`, reads the structured stdout, classifies in its
own context, and writes the per-section files via Write tool.

For users running CLI without an agent, the default mode dumps everything
into `sp/section/workspace.md` and they split manually with $EDITOR.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SECTIONS = ("about-me", "preferences", "workspace", "knowledge-base", "skills")

SECTION_TYPE = {
    "about-me": "identity",
    "preferences": "preference",
    "workspace": "workspace",
    "knowledge-base": "knowledge-base",
    "skills": "skill",
}


# Reference prompt for agents. forge does NOT call an LLM with this; the agent
# uses it (or its own equivalent) when running `forge ingest --emit`.
CLASSIFY_PROMPT_REFERENCE = """\
Split this user's existing AI context (CLAUDE.md / .cursorrules / Claude
auto-memory / etc.) into 5 sections:

1. **about-me** — identity. Who they are, role, work style.
2. **preferences** — agent rules. Boundaries, output style, "don't / always".
3. **workspace** — current active projects, what they're focused on now.
4. **knowledge-base** — long-term topic indexes, domain references.
5. **skills** — reusable craft / workflows / procedures.

Preserve user's actual words. Empty section is fine if no relevant content.
Write each section to `sp/section/<name>.md` with this frontmatter:

    ---
    name: <name>
    type: <identity|preference|workspace|knowledge-base|skill>
    ---

    <body>
"""


class IngestError(Exception):
    """Raised when ingest fails (file missing, write conflict)."""


@dataclass
class ClassificationResult:
    """Holds the loaded text + metadata. Never carries LLM-classified sections —
    that's the agent's job now. Kept around so write_sections() can write the
    no-classify dump path."""
    sections: dict[str, str]  # all 5 keys, only "workspace" populated for dump path
    method: str  # "dump" (default CLI), "emit" (agent path)
    source_path: Path | None
    raw_text: str

    def non_empty(self) -> dict[str, str]:
        return {k: v for k, v in self.sections.items() if v.strip()}


def classify(text: str, **_kwargs) -> ClassificationResult:
    """Wrap text into a ClassificationResult with everything in workspace.md.

    No LLM call. The `**_kwargs` is for backward compat with old call sites
    that passed `use_llm=` etc.; arguments are ignored.
    """
    return ClassificationResult(
        sections={
            "about-me": "",
            "preferences": "",
            "workspace": text.strip(),
            "knowledge-base": "",
            "skills": "",
        },
        method="dump",
        source_path=None,
        raw_text=text,
    )


def write_sections(
    result: ClassificationResult,
    workspace: Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Write `result.sections` into workspace/sp/section/. Returns paths written.

    Refuses to overwrite a section that doesn't have a `[TODO:` template marker
    unless `overwrite=True`.
    """
    section_dir = workspace / "sp" / "section"
    if not section_dir.exists():
        raise IngestError(
            f"{section_dir} does not exist. "
            f"Run `forge new {workspace}` first to scaffold the workspace."
        )

    written: list[Path] = []
    source_note = (
        f"\n\n[ingested from {result.source_path} via forge ingest "
        f"({result.method}). "
        f"Review carefully — content was dumped, not classified; "
        f"edit, then run `forge review` and `forge approve`.]\n"
        if result.source_path
        else ""
    )

    for name, body in result.sections.items():
        if not body.strip():
            continue
        path = section_dir / f"{name}.md"

        if path.exists() and not overwrite:
            existing = path.read_text(encoding="utf-8")
            if "[TODO:" not in existing:
                raise IngestError(
                    f"{path} already exists with non-template content. "
                    f"Use --overwrite to replace, or merge manually."
                )

        type_field = SECTION_TYPE.get(name, "section")
        frontmatter = f"---\nname: {name}\ntype: {type_field}\n---\n\n"
        path.write_text(frontmatter + body.strip() + source_note, encoding="utf-8")
        written.append(path)

    return written
