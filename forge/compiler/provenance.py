"""Provenance: compute the per-output header block that records what the compile consumed.

The goal: given any compiled CLAUDE.md / AGENTS.md, a reader can trace every
section back to its source file, upstream chain, generator, and a stable hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from forge import __version__
from forge.compiler.section import Section
from forge.compiler.config import Config


def compute_digest(sections: list[Section], config: Config) -> str:
    """SHA256 over the normalized render input. 12 hex chars.

    The digest is meant to identify the rendered artifact's semantic inputs, not
    just section bodies. Include every field core adapters consume or expose in
    provenance, plus the forge-core version so adapter behavior changes get a
    new digest.
    """
    payload = {
        "forge_core_version": __version__,
        "config": {
            "name": config.name,
            "target": config.target,
            "sections": list(config.sections),
            "required_sections": list(config.required_sections),
            "output_frontmatter": _normalize(config.output_frontmatter),
            "demote_section_headings": config.demote_section_headings,
            "meta": _normalize(config.meta),
        },
        "sections": [
            {
                "name": sec.name,
                "type": sec.type,
                "kind": sec.kind,
                "updated_at": sec.updated_at,
                "source": sec.source,
                "upstream": list(sec.upstream),
                "generated_by": sec.generated_by,
                "meta": _normalize(sec.meta),
                "body": sec.body,
            }
            for sec in sections
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def build_block(sections: list[Section], config: Config) -> dict:
    """Structured provenance record — consumed by adapters to render a header."""
    return {
        "config": config.name,
        "target": config.target,
        "forge_core_version": __version__,
        "digest": compute_digest(sections, config),
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
        f"target={block['target']} version={block['forge_core_version']} "
        f"digest={block['digest']}"
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


def _normalize(value: Any) -> Any:
    """Return JSON-stable data for hashing, preserving useful scalar values."""
    if isinstance(value, dict):
        return {
            str(k): _normalize(v)
            for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
        }
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    if isinstance(value, tuple):
        return [_normalize(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
