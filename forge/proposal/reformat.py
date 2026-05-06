"""Frontmatter reformatter (v0.3.2 / v0.3.3).

Re-serialize an existing `proposal.md`'s YAML frontmatter through the
project-wide `_ForgeDumper` so multi-line strings come out as block scalars
(`|`) instead of v0.3.1's flow-with-`\\n`-escapes or folded-`'…'` forms.

v0.3.3 also offers an opt-in (default-on) "break long lines" pass: any string
field whose plain scalar would exceed `BREAK_LONG_LINES_THRESHOLD` cols is
broken at CJK / ASCII punctuation by inserting `\\n`, then dumped as a block
scalar (`|`). This keeps Obsidian / terminal viewers from folding plain
scalars at unpredictable widths. Pass `break_long_lines=False` to disable
(restored v0.3.2 behavior).

Body is preserved verbatim — including the `<!-- BEGIN AUTO-RENDERED -->` /
`<!-- END -->` auto-rendered §0.5 view. Reformat only touches the frontmatter
between the leading `---` lines.

Reformat is idempotent: a file that's already block-scalar-shaped round-trips
to itself (when `break_long_lines` matches between calls).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from forge.proposal.schema import _split_frontmatter, forge_yaml_dump


# v0.3.3: long single-line strings (no `\n`) longer than this many display
# cols are eligible for break-long-lines. Triggered only when reformat is
# called with `break_long_lines=True` (default).
BREAK_LONG_LINES_THRESHOLD = 90

# Punctuation after which we may insert `\n` to break a long plain scalar.
#
# v0.3.4: split into two classes (mirrors renderer._CJK_BREAK_AFTER /
# _ASCII_BREAK_AFTER) to avoid mid-token cuts on dot-extension filenames /
# IPs / domains / version strings (e.g. `CLAUDE.md`, `192.168.1.1`,
# `example.com`, `v0.3.3`).
#
# `_CJK_BREAK_AFTER`  — fullwidth CJK punct + close brackets + flow-arrow
#                       (break IMMEDIATELY after).
# `_ASCII_BREAK_AFTER` — narrow ASCII punct (`.,;!?`); only register as a
#                       break candidate when the next char is whitespace or
#                       end-of-string.
_CJK_BREAK_AFTER = "，。；：、！？）】」』→"
_ASCII_BREAK_AFTER = ",;.!?)"
# Backward-compat alias (some tests import this).
_BREAK_AFTER_CHARS = _CJK_BREAK_AFTER + _ASCII_BREAK_AFTER


@dataclass
class ReformatResult:
    path: Path
    changed: bool        # True iff the new text differs from the original
    before_bytes: int
    after_bytes: int
    backup: Path | None  # set when caller asked to keep a `.bak`


def _display_cols(s: str) -> int:
    """Approximate terminal column width: CJK / fullwidth = 2, else 1."""
    import unicodedata
    w = 0
    for ch in s:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            w += 2
        else:
            w += 1
    return w


def _break_long_string(s: str, *, threshold: int = BREAK_LONG_LINES_THRESHOLD) -> str:
    """Insert `\n` after CJK / ASCII punctuation so each line fits within
    `threshold` display cols.

    Only activates per-line: each input line is inspected separately, and
    only "long enough" lines are broken. Empty / short lines pass through
    unchanged. Strings that already contain `\n` are processed line-by-line
    so a mixed input (some short, one long) is broken cleanly.

    Conservative: when no punctuation break-point exists within the budget,
    the line is left alone (we don't hard-cut mid-word).
    """
    out: list[str] = []
    for line in s.split("\n"):
        if _display_cols(line) <= threshold:
            out.append(line)
            continue
        out.extend(_break_one_line(line, threshold=threshold))
    return "\n".join(out)


def _break_one_line(line: str, *, threshold: int) -> list[str]:
    """Break a single (no-`\n`) line at punctuation boundaries so each piece
    fits within `threshold` cols. If no break exists at all, return [line]."""
    pieces: list[str] = []
    remaining = line
    while _display_cols(remaining) > threshold:
        cut = _find_punct_break(remaining, threshold)
        if cut <= 0:
            break
        head = remaining[:cut].rstrip(" ")
        tail = remaining[cut:].lstrip(" ")
        if not head or not tail:
            break
        pieces.append(head)
        remaining = tail
    pieces.append(remaining)
    return pieces


def _find_punct_break(s: str, budget: int) -> int:
    """Return the largest index after which inserting `\n` keeps `s[:idx]`
    within `budget` cols AND `s[idx-1]` is a break-point punctuation char.

    Returns 0 if no such position exists.

    v0.3.4: ASCII `.,;!?` are break candidates ONLY when followed by space
    or end-of-string, so file extensions (`CLAUDE.md`), IPs, domains, and
    version strings stay intact across line breaks.
    """
    cols = 0
    last_punct_idx = 0
    for i, ch in enumerate(s):
        import unicodedata
        ch_cols = 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
        if cols + ch_cols > budget:
            return last_punct_idx
        cols += ch_cols
        if ch in _CJK_BREAK_AFTER:
            last_punct_idx = i + 1
        elif ch in _ASCII_BREAK_AFTER:
            next_ch = s[i + 1] if i + 1 < len(s) else ""
            if next_ch == "" or next_ch == " ":
                last_punct_idx = i + 1
    return last_punct_idx


def _walk_break_long(node: Any, threshold: int) -> Any:
    """Recursively walk a YAML-loaded structure (dict / list / str scalars)
    and break long string scalars in place."""
    if isinstance(node, dict):
        return {k: _walk_break_long(v, threshold) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk_break_long(v, threshold) for v in node]
    if isinstance(node, str):
        return _break_long_string(node, threshold=threshold)
    return node


def reformat_text(
    text: str, *, break_long_lines: bool = True
) -> tuple[str, bool]:
    """Re-dump the frontmatter through `_ForgeDumper`. Body is untouched.

    Returns (new_text, changed). When the file has no frontmatter or the YAML
    is malformed, returns the original text with changed=False — caller is
    expected to surface a clearer error path (validate / load_proposal).

    v0.3.3: when `break_long_lines=True` (default), also inserts `\n` into
    plain scalar string fields whose display width exceeds 90 cols, breaking
    at CJK / ASCII punctuation. Pass False to keep the v0.3.2 behavior
    (no content mutation; only YAML style normalization).
    """
    fm_text, body = _split_frontmatter(text)
    if not fm_text.strip():
        return text, False
    try:
        loaded: Any = yaml.safe_load(fm_text)
    except yaml.YAMLError:
        return text, False
    if not isinstance(loaded, dict):
        return text, False

    if break_long_lines:
        loaded = _walk_break_long(loaded, BREAK_LONG_LINES_THRESHOLD)

    new_fm = forge_yaml_dump(loaded)
    # Do NOT rstrip the dump: trailing `\n` after a literal block scalar (`|`)
    # is meaningful (clip vs strip). Just ensure exactly one newline before
    # the closing `---`.
    if not new_fm.endswith("\n"):
        new_fm += "\n"
    if body and not body.startswith("\n"):
        body = "\n" + body
    new_text = f"---\n{new_fm}---\n{body}"
    # Ensure file ends with exactly one trailing newline.
    new_text = new_text.rstrip("\n") + "\n"
    return new_text, (new_text != text)


def reformat_file(
    path: Path, *, backup: bool = True, break_long_lines: bool = True
) -> ReformatResult:
    """Reformat `path` in place. Optionally writes `path.with_suffix('.md.bak')`
    before mutating; caller may delete the backup once they've verified the
    result.
    """
    original = path.read_text(encoding="utf-8")
    new_text, changed = reformat_text(original, break_long_lines=break_long_lines)
    bak: Path | None = None
    if changed:
        if backup:
            bak = path.with_name(path.name + ".bak")
            bak.write_text(original, encoding="utf-8")
        path.write_text(new_text, encoding="utf-8")
    return ReformatResult(
        path=path,
        changed=changed,
        before_bytes=len(original.encode("utf-8")),
        after_bytes=len(new_text.encode("utf-8")),
        backup=bak,
    )


def needs_reformat(text: str, *, break_long_lines: bool = True) -> bool:
    """Heuristic: True iff reformat would change the text."""
    _, changed = reformat_text(text, break_long_lines=break_long_lines)
    return changed
