"""Anchored-block patch mechanics, shared by the ledger and the audit graph.

An anchor names a block inside a markdown file: a heading anchor owns
everything up to the next heading of the same or a higher level; a non-heading
anchor owns its line up to the next blank line. Patches replace that block,
append to the file, or create it — never guess a location.
"""

from __future__ import annotations

import hashlib
import re

_HEADING_RE = re.compile(r"^(#+)\s")


def anchored_block(text: str, anchor: str) -> tuple[int, int] | None:
    """Locate the block an anchor names: (start_line, end_line), 1-based inclusive."""
    lines = text.splitlines()
    idx = next((i for i, ln in enumerate(lines) if ln.strip() == anchor.strip()), None)
    if idx is None:
        idx = next((i for i, ln in enumerate(lines) if anchor in ln), None)
    if idx is None:
        return None
    heading = _HEADING_RE.match(lines[idx])
    if heading:
        level = len(heading.group(1))
        end = len(lines)
        for j in range(idx + 1, len(lines)):
            nxt = _HEADING_RE.match(lines[j])
            if nxt and len(nxt.group(1)) <= level:
                end = j
                break
        return idx + 1, end
    end = idx + 1
    for j in range(idx + 1, len(lines)):
        if not lines[j].strip():
            break
        end = j + 1
    return idx + 1, end


def extract_block(text: str, anchor: str) -> str | None:
    """The anchored block's current text, or None when the anchor is absent."""
    located = anchored_block(text, anchor)
    if located is None:
        return None
    start, end = located
    return "\n".join(text.splitlines()[start - 1 : end])


def block_digest(block_text: str) -> str:
    """Content fingerprint of a block (stale-guard baseline)."""
    return "sha1:" + hashlib.sha1(block_text.encode("utf-8")).hexdigest()


def apply_patch(text: str, *, anchor: str, mode: str, proposed_text: str) -> str:
    """Return the file text after applying the patch. Raises on unlocatable anchor."""
    proposed = proposed_text.rstrip("\n")
    if mode == "append" or (mode == "replace" and not anchor):
        base = text.rstrip("\n")
        return (base + "\n\n" + proposed + "\n") if base else (proposed + "\n")
    if mode == "replace":
        located = anchored_block(text, anchor)
        if located is None:
            raise ValueError(f"anchor not located: {anchor!r}")
        start, end = located
        lines = text.splitlines()
        new_lines = lines[: start - 1] + proposed.split("\n") + lines[end:]
        return "\n".join(new_lines) + "\n"
    if mode == "create":
        return proposed + "\n"
    raise ValueError(f"unknown patch mode: {mode!r}")
