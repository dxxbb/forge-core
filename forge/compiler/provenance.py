"""Provenance: compute the per-output header block that records what the compile consumed.

The goal: given any compiled CLAUDE.md / AGENTS.md, a reader can trace every
section back to its source file, upstream chain, generator, and a stable hash.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from forge.compiler.section import Section
from forge.compiler.config import Config


def compute_digest(sections: list[Section], config: Config) -> str:
    """SHA256 over (ordered) section bodies + config identity. 12 hex chars."""
    h = hashlib.sha256()
    h.update(config.name.encode("utf-8"))
    h.update(b"\0")
    h.update(config.target.encode("utf-8"))
    h.update(b"\0")
    for sec in sections:
        h.update(sec.name.encode("utf-8"))
        h.update(b"\0")
        h.update(sec.body.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:12]


def build_block(sections: list[Section], config: Config) -> dict:
    """Structured provenance record — consumed by adapters to render a header."""
    return {
        "config": config.name,
        "target": config.target,
        "digest": compute_digest(sections, config),
        "compiled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sections": [
            {
                "name": sec.name,
                "type": sec.type,
                "kind": sec.kind,
                "updated_at": sec.updated_at,
                "source": sec.source,
                "upstream": list(sec.upstream),
                "generated_by": sec.generated_by,
                "bytes": sec.byte_size,
            }
            for sec in sections
        ],
    }


def render_markdown_header(block: dict, comment_style: str = "html") -> str:
    """Render the provenance block as a compact markdown comment.

    comment_style='html' → `<!-- ... -->` (CLAUDE.md friendly)
    comment_style='blockquote' → `> ...` lines (AGENTS.md convention, visible)
    """
    lines: list[str] = []
    header = (
        f"forge-core provenance · config={block['config']} "
        f"target={block['target']} digest={block['digest']} "
        f"compiled_at={block['compiled_at']}"
    )
    sec_lines: list[str] = []
    for sec in block["sections"]:
        bits = [sec["name"]]
        if sec["type"]:
            bits.append(f"type={sec['type']}")
        if sec["kind"]:
            bits.append(f"kind={sec['kind']}")
        if sec["updated_at"]:
            bits.append(f"updated={sec['updated_at']}")
        if sec["source"]:
            bits.append(f"source={sec['source']}")
        if sec["upstream"]:
            bits.append(f"upstream=[{', '.join(sec['upstream'])}]")
        if sec["generated_by"]:
            bits.append(f"generated_by={sec['generated_by']}")
        bits.append(f"{sec['bytes']}B")
        sec_lines.append("  - " + " · ".join(bits))

    if comment_style == "html":
        lines.append("<!--")
        lines.append(header)
        lines.extend(sec_lines)
        lines.append("-->")
    elif comment_style == "blockquote":
        lines.append(f"> {header}")
        for sl in sec_lines:
            lines.append(f">{sl}")
    else:
        raise ValueError(f"unknown comment_style: {comment_style}")
    return "\n".join(lines)
