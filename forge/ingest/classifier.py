"""Classify an unstructured text blob into 5 SP MVP sections.

LLM path uses Anthropic SDK. No-LLM path just dumps everything into one section.
"""

from __future__ import annotations

import json
import os
import re
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


CLASSIFY_PROMPT = """\
You are helping classify a user's existing AI agent context file (such as a
CLAUDE.md, .cursorrules, or similar) into 5 sections matching forge-core's
"SP MVP" schema:

1. **about-me** — identity. Who the user is, what they do, work style as a person.
2. **preferences** — rules for agent behavior. Boundaries, output style preferences, working norms ("don't do X", "always Y").
3. **workspace** — current active projects, topics being tracked, what they're focused on right now.
4. **knowledge-base** — index/pointers to long-term topics or domain references the user maintains.
5. **skills** — craft / workflows / procedures the agent should know about (e.g. "when user says 'review the diff', do X").

Read the input below and split it into these 5 sections. Reorganize content
into the section it best belongs in, even if the original document grouped
things differently. Preserve the user's actual words as much as possible —
don't paraphrase or compress. If a section has no relevant content in the
input, use an empty string for that key.

Output ONLY a single JSON object with these exact keys, no other text:

{"about_me": "...", "preferences": "...", "workspace": "...", "knowledge_base": "...", "skills": "..."}

Each value is a markdown string (the body content for that section).

Input:
---
%s
---

Output the JSON object now.
"""


class IngestError(Exception):
    """Raised when ingest fails (file missing, API error, parse error)."""


@dataclass
class ClassificationResult:
    sections: dict[str, str]  # section name -> body markdown
    method: str  # "llm" or "no-llm"
    source_path: Path | None
    raw_text: str  # original input

    def non_empty(self) -> dict[str, str]:
        return {k: v for k, v in self.sections.items() if v.strip()}


def classify(
    text: str,
    *,
    use_llm: bool,
    model: str = "claude-opus-4-7",
    api_key: str | None = None,
) -> ClassificationResult:
    """Classify text into 5 sections.

    use_llm=False: dump into a single 'imported' section under skills (catch-all)
                   — actually we put it in a special 'imported' name and let
                   the user move it. But to fit the 5-section schema exactly,
                   stick everything into 'workspace' as least-bad default.

    use_llm=True: call Anthropic API.
    """
    if not use_llm:
        # Dump everything into one bucket. Pick "workspace" since that's the
        # most context-shaped catch-all (about-me / preferences are too
        # specific). User splits manually after.
        return ClassificationResult(
            sections={
                "about-me": "",
                "preferences": "",
                "workspace": text.strip(),
                "knowledge-base": "",
                "skills": "",
            },
            method="no-llm",
            source_path=None,
            raw_text=text,
        )

    # LLM path
    try:
        import anthropic
    except ImportError as e:
        raise IngestError(
            "LLM classification needs the `anthropic` package: pip install anthropic\n"
            "Or use --no-llm to skip API and dump into one section for manual split."
        ) from e

    if api_key is None and not os.environ.get("ANTHROPIC_API_KEY"):
        raise IngestError(
            "ANTHROPIC_API_KEY not set.\n"
            "Either: export ANTHROPIC_API_KEY=sk-ant-...\n"
            "Or: run with --no-llm (dumps into one section, you split manually)."
        )

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    prompt = CLASSIFY_PROMPT % text

    try:
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        raise IngestError(f"Anthropic API call failed: {e}") from e

    output = "".join(b.text for b in response.content if b.type == "text").strip()
    parsed = _extract_json(output)
    if parsed is None:
        raise IngestError(
            f"could not parse JSON from model response. Raw output:\n{output[:300]}"
        )

    # Map keys with underscores back to dashes for filenames
    sections = {
        "about-me": _safe_str(parsed.get("about_me", "")),
        "preferences": _safe_str(parsed.get("preferences", "")),
        "workspace": _safe_str(parsed.get("workspace", "")),
        "knowledge-base": _safe_str(parsed.get("knowledge_base", "")),
        "skills": _safe_str(parsed.get("skills", "")),
    }

    return ClassificationResult(
        sections=sections,
        method="llm",
        source_path=None,
        raw_text=text,
    )


def write_sections(
    result: ClassificationResult,
    workspace: Path,
    *,
    overwrite: bool = False,
) -> list[Path]:
    """Write classified sections into workspace/sp/section/.

    Returns list of files written. Raises IngestError if a target file would
    be clobbered without --overwrite.
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
        f"Review carefully — classification may not be perfect; "
        f"edit, then run `forge diff` and `forge approve`.]\n"
        if result.source_path
        else ""
    )

    for name, body in result.sections.items():
        if not body.strip():
            continue
        path = section_dir / f"{name}.md"

        if path.exists() and not overwrite:
            existing = path.read_text(encoding="utf-8")
            # If the section is just a TODO placeholder, treat as overwritable
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


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fenced code block
    m = re.search(r"```(?:json)?\s*\n?(.+?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # First { ... last }
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _safe_str(v) -> str:
    return v if isinstance(v, str) else ""
