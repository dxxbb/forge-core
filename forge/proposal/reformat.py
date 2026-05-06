"""Frontmatter reformatter (v0.3.2).

Re-serialize an existing `proposal.md`'s YAML frontmatter through the
project-wide `_ForgeDumper` so multi-line strings come out as block scalars
(`|`) instead of v0.3.1's flow-with-`\\n`-escapes or folded-`'…'` forms.

Body is preserved verbatim — including the `<!-- BEGIN AUTO-RENDERED -->` /
`<!-- END -->` auto-rendered §0.5 view. Reformat only touches the frontmatter
between the leading `---` lines.

Reformat is idempotent: a file that's already block-scalar-shaped round-trips
to itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from forge.proposal.schema import _split_frontmatter, forge_yaml_dump


@dataclass
class ReformatResult:
    path: Path
    changed: bool        # True iff the new text differs from the original
    before_bytes: int
    after_bytes: int
    backup: Path | None  # set when caller asked to keep a `.bak`


def reformat_text(text: str) -> tuple[str, bool]:
    """Re-dump the frontmatter through `_ForgeDumper`. Body is untouched.

    Returns (new_text, changed). When the file has no frontmatter or the YAML
    is malformed, returns the original text with changed=False — caller is
    expected to surface a clearer error path (validate / load_proposal).
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


def reformat_file(path: Path, *, backup: bool = True) -> ReformatResult:
    """Reformat `path` in place. Optionally writes `path.with_suffix('.md.bak')`
    before mutating; caller may delete the backup once they've verified the
    result.
    """
    original = path.read_text(encoding="utf-8")
    new_text, changed = reformat_text(original)
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


def needs_reformat(text: str) -> bool:
    """Heuristic: True iff reformat would change the text."""
    _, changed = reformat_text(text)
    return changed
