"""Proposal frontmatter schema (dataclasses + YAML I/O).

The schema captures the §0.5 "monitor item view" tree:

    PR
    ├── item 1     {monitor_info, extracted, disposition, rationale, propagation}
    ├── item 2     ...
    └── item 3 (MIXED, sub_items[])
        ├── sub-item 3.1   {same fields}
        ├── ...
        └── sub-item 3.N

Disposition is one of: APPLY | COVERED | ARCHIVE | DECIDE | NA | MIXED.

The proposal `.md` file uses YAML frontmatter (delimited by `---` lines). When
`items:` is present, this module can deserialize it; the body of the file may
contain a placeholder comment (`<!-- §0.5 will be auto-rendered ... -->`) or
arbitrary markdown — body content is preserved on round-trip.

Round-trip rule: load_proposal followed by dump_proposal should preserve the
schema content; the body is opaque to this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


# ----------------------------------------------------------------------------
# YAML dumper: force block-scalar (`|`) style for any string containing newlines
# ----------------------------------------------------------------------------
#
# v0.3.1 default `yaml.safe_dump` produces two ugly forms for multi-line strings
# in our schema:
#   • flow scalar with literal `\n` escapes (632–746 chars on a single line), or
#   • folded `'…'` scalar with `''` quote-escaping and double-newline paragraph
#     breaks plus 6-space indentation.
# Both are unreadable inside Obsidian and create churn on round-trip. v0.3.2
# normalizes every multi-line string to YAML literal block scalar (`|`) so the
# frontmatter stays close to the literal text the agent wrote.

class _ForgeDumper(yaml.SafeDumper):
    """SafeDumper subclass that prefers block-scalar `|` for multi-line strings."""


def _represent_str(dumper: yaml.SafeDumper, data: str):
    if "\n" in data:
        # Strip trailing whitespace on each line; a trailing space on a literal
        # block scalar line forces yaml to fall back to a quoted style.
        cleaned = "\n".join(line.rstrip() for line in data.split("\n"))
        return dumper.represent_scalar("tag:yaml.org,2002:str", cleaned, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_ForgeDumper.add_representer(str, _represent_str)


def forge_yaml_dump(data: Any) -> str:
    """Project-wide YAML dump: block-scalar for multi-line strings, unicode kept,
    field order preserved, lines not auto-wrapped."""
    return yaml.dump(
        data,
        Dumper=_ForgeDumper,
        sort_keys=False,
        allow_unicode=True,
        width=10**9,
        default_flow_style=False,
    )


class Disposition(str, Enum):
    """Per-item disposition icon enum.

    APPLY     ✅ — distill into asset/section change
    COVERED   ⏭ — already covered by existing asset, skip
    ARCHIVE   📦 — capture only, no propagation
    DECIDE    ❓ — needs user decision (multiple options)
    NA        ➖ — index file / not asset content / not applicable
    MIXED     🔀 — composite item, sub_items[] each have their own disposition
    """

    APPLY = "APPLY"
    COVERED = "COVERED"
    ARCHIVE = "ARCHIVE"
    DECIDE = "DECIDE"
    NA = "NA"
    MIXED = "MIXED"

    @property
    def icon(self) -> str:
        return _ICONS[self]

    @classmethod
    def parse(cls, raw: Any) -> "Disposition":
        if isinstance(raw, Disposition):
            return raw
        if not isinstance(raw, str):
            raise ValueError(f"disposition must be a string, got {type(raw).__name__}")
        key = raw.strip().upper().replace("/", "_")
        # accept some friendly aliases
        aliases = {
            "N_A": "NA",
            "N/A": "NA",
            "ARCHIVEONLY": "ARCHIVE",
            "ARCHIVE-ONLY": "ARCHIVE",
            "ARCHIVE_ONLY": "ARCHIVE",
        }
        key = aliases.get(key, key)
        try:
            return cls[key]
        except KeyError as e:
            valid = ", ".join(d.value for d in cls)
            raise ValueError(f"unknown disposition `{raw}` (valid: {valid})") from e

    @classmethod
    def is_placeholder(cls, raw: Any) -> bool:
        """True when `raw` is the scaffold placeholder enum hint (still unfilled)."""
        if not isinstance(raw, str):
            return False
        s = raw.strip()
        # match <APPLY|COVERED|ARCHIVE|DECIDE|NA|MIXED> or simply contains "|"
        return s.startswith("<") and s.endswith(">") and "|" in s


_ICONS = {
    Disposition.APPLY: "✅",       # ✅
    Disposition.COVERED: "⏭",     # ⏭
    Disposition.ARCHIVE: "\U0001F4E6",  # 📦
    Disposition.DECIDE: "❓",      # ❓
    Disposition.NA: "➖",          # ➖
    Disposition.MIXED: "\U0001F500",   # 🔀
}


@dataclass
class PropagationNode:
    """A single node in the propagation tree.

    A node represents a file the change touches. `modification` is a one-line
    or multi-line summary of how the file changes; `children` may carry deeper
    propagation (e.g. asset → section → runtime).
    """

    path: str = ""
    label: str = ""        # e.g. "监控源", "Layer 1 · asset", "auto-gen"
    layer: str = ""        # e.g. "Layer 1 · asset"  (optional, can be in label)
    modification: str = ""  # body of "├─ 修改: ..."; empty for terminal/passthrough
    terminal: bool = False  # explicit "(终止)" marker
    children: list["PropagationBranch"] = field(default_factory=list)

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {}
        if self.path:
            out["path"] = self.path
        if self.label:
            out["label"] = self.label
        if self.layer:
            out["layer"] = self.layer
        if self.modification:
            out["modification"] = self.modification
        if self.terminal:
            out["terminal"] = True
        if self.children:
            out["children"] = [c.to_yaml() for c in self.children]
        return out

    @classmethod
    def from_yaml(cls, data: dict | None) -> "PropagationNode":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"node must be a mapping, got {type(data).__name__}")
        return cls(
            path=str(data.get("path", "") or ""),
            label=str(data.get("label", "") or ""),
            layer=str(data.get("layer", "") or ""),
            modification=str(data.get("modification", "") or ""),
            terminal=bool(data.get("terminal", False)),
            children=[
                PropagationBranch.from_yaml(c) for c in (data.get("children") or [])
            ],
        )


@dataclass
class PropagationBranch:
    """Branch wrapper: branch label (`a`, `a1`, `b`, `c` …) + node.

    The §0.5 syntax `└─ a:` / `└─ b:` denotes branches. We model branches
    explicitly so renderers can produce the same labels deterministically.
    """

    branch: str = "a"             # 'a', 'a1', 'b', 'c', ...
    shared_with: list[str] = field(default_factory=list)  # sub-item ids that share this branch
    node: PropagationNode = field(default_factory=PropagationNode)

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {"branch": self.branch}
        if self.shared_with:
            out["shared_with"] = list(self.shared_with)
        out["node"] = self.node.to_yaml()
        return out

    @classmethod
    def from_yaml(cls, data: dict | None) -> "PropagationBranch":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"branch must be a mapping, got {type(data).__name__}")
        return cls(
            branch=str(data.get("branch", "a") or "a"),
            shared_with=[str(s) for s in (data.get("shared_with") or [])],
            node=PropagationNode.from_yaml(data.get("node")),
        )


@dataclass
class DecideOption:
    """One option of a DECIDE disposition.

    Each option has its own propagation tree (or empty propagation for the
    "do nothing" option).
    """

    id: str = "A"                 # 'A', 'B', 'C', ...
    description: str = ""
    propagation: list[PropagationBranch] = field(default_factory=list)

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {"id": self.id}
        if self.description:
            out["description"] = self.description
        out["propagation"] = [b.to_yaml() for b in self.propagation]
        return out

    @classmethod
    def from_yaml(cls, data: dict | None) -> "DecideOption":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"option must be a mapping, got {type(data).__name__}")
        return cls(
            id=str(data.get("id", "A") or "A"),
            description=str(data.get("description", "") or ""),
            propagation=[
                PropagationBranch.from_yaml(b) for b in (data.get("propagation") or [])
            ],
        )


@dataclass
class SubItem:
    """A sub-item under a MIXED parent."""

    id: str = ""                          # e.g. "3.1"
    monitor_info: str = ""                # optional; usually inherited from parent
    extracted: str = ""
    disposition: Disposition | None = None
    disposition_note: str = ""            # short tagline next to icon
    rule: str = ""                        # for APPLY: the new rule's title (e.g. "§10")
    rationale: str = ""
    propagation: list[PropagationBranch] = field(default_factory=list)
    risk: str = ""

    # COVERED-specific
    covered_by: str = ""                  # location where the content already lives

    # NA-specific
    reason: str = ""                      # why NA

    # DECIDE-specific
    options: list[DecideOption] = field(default_factory=list)
    recommendation: str = ""              # e.g. "A"

    # v0.7 propagation-resolver inputs (optional). When `modified_files` is
    # populated, `forge proposal validate` will auto-derive `propagation` by
    # reverse-looking-up `sections.upstream`. Authors may keep filling
    # `propagation` by hand — in that case the resolver skips with a warning.
    modified_files: list[str] = field(default_factory=list)
    modifications: dict[str, str] = field(default_factory=dict)
    propagation_hints: dict[str, str] = field(default_factory=dict)

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {"id": self.id}
        if self.monitor_info:
            out["monitor_info"] = self.monitor_info
        if self.extracted:
            out["extracted"] = self.extracted
        if self.disposition is not None:
            out["disposition"] = self.disposition.value
        if self.disposition_note:
            out["disposition_note"] = self.disposition_note
        if self.rule:
            out["rule"] = self.rule
        if self.rationale:
            out["rationale"] = self.rationale
        if self.modified_files:
            out["modified_files"] = list(self.modified_files)
        if self.modifications:
            out["modifications"] = dict(self.modifications)
        if self.propagation_hints:
            out["propagation_hints"] = dict(self.propagation_hints)
        if self.propagation:
            out["propagation"] = [b.to_yaml() for b in self.propagation]
        if self.risk:
            out["risk"] = self.risk
        if self.covered_by:
            out["covered_by"] = self.covered_by
        if self.reason:
            out["reason"] = self.reason
        if self.options:
            out["options"] = [o.to_yaml() for o in self.options]
        if self.recommendation:
            out["recommendation"] = self.recommendation
        return out

    @classmethod
    def from_yaml(cls, data: dict | None) -> "SubItem":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"sub-item must be a mapping, got {type(data).__name__}")
        d_raw = data.get("disposition")
        if d_raw and not Disposition.is_placeholder(d_raw):
            disposition = Disposition.parse(d_raw)
        else:
            disposition = None
        return cls(
            id=str(data.get("id", "") or ""),
            monitor_info=str(data.get("monitor_info", "") or ""),
            extracted=str(data.get("extracted", "") or ""),
            disposition=disposition,
            disposition_note=str(data.get("disposition_note", "") or ""),
            rule=str(data.get("rule", "") or ""),
            rationale=str(data.get("rationale", "") or ""),
            propagation=[
                PropagationBranch.from_yaml(b) for b in (data.get("propagation") or [])
            ],
            risk=str(data.get("risk", "") or ""),
            covered_by=str(data.get("covered_by", "") or ""),
            reason=str(data.get("reason", "") or ""),
            options=[DecideOption.from_yaml(o) for o in (data.get("options") or [])],
            recommendation=str(data.get("recommendation", "") or ""),
            modified_files=[str(p) for p in (data.get("modified_files") or [])],
            modifications=_load_str_dict(data.get("modifications")),
            propagation_hints=_load_str_dict(data.get("propagation_hints")),
        )


@dataclass
class Item:
    """A top-level monitor item in §0.5 view.

    A MIXED item carries `sub_items[]`; non-MIXED items use propagation/options
    on the item itself.
    """

    id: str = ""                              # e.g. "1", "2", "3"
    monitor_info: str = ""
    extracted: str = ""
    disposition: Disposition | None = None
    disposition_note: str = ""
    rule: str = ""
    rationale: str = ""
    propagation: list[PropagationBranch] = field(default_factory=list)
    risk: str = ""
    covered_by: str = ""
    reason: str = ""
    options: list[DecideOption] = field(default_factory=list)
    recommendation: str = ""
    sub_items: list[SubItem] = field(default_factory=list)

    # v0.7 — see SubItem for semantics.
    modified_files: list[str] = field(default_factory=list)
    modifications: dict[str, str] = field(default_factory=dict)
    propagation_hints: dict[str, str] = field(default_factory=dict)

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {"id": self.id}
        if self.monitor_info:
            out["monitor_info"] = self.monitor_info
        if self.extracted:
            out["extracted"] = self.extracted
        if self.disposition is not None:
            out["disposition"] = self.disposition.value
        if self.disposition_note:
            out["disposition_note"] = self.disposition_note
        if self.rule:
            out["rule"] = self.rule
        if self.rationale:
            out["rationale"] = self.rationale
        if self.modified_files:
            out["modified_files"] = list(self.modified_files)
        if self.modifications:
            out["modifications"] = dict(self.modifications)
        if self.propagation_hints:
            out["propagation_hints"] = dict(self.propagation_hints)
        if self.propagation:
            out["propagation"] = [b.to_yaml() for b in self.propagation]
        if self.risk:
            out["risk"] = self.risk
        if self.covered_by:
            out["covered_by"] = self.covered_by
        if self.reason:
            out["reason"] = self.reason
        if self.options:
            out["options"] = [o.to_yaml() for o in self.options]
        if self.recommendation:
            out["recommendation"] = self.recommendation
        if self.sub_items:
            out["sub_items"] = [s.to_yaml() for s in self.sub_items]
        return out

    @classmethod
    def from_yaml(cls, data: dict | None) -> "Item":
        if data is None:
            return cls()
        if not isinstance(data, dict):
            raise ValueError(f"item must be a mapping, got {type(data).__name__}")
        d_raw = data.get("disposition")
        if d_raw and not Disposition.is_placeholder(d_raw):
            disposition = Disposition.parse(d_raw)
        else:
            disposition = None
        return cls(
            id=str(data.get("id", "") or ""),
            monitor_info=str(data.get("monitor_info", "") or ""),
            extracted=str(data.get("extracted", "") or ""),
            disposition=disposition,
            disposition_note=str(data.get("disposition_note", "") or ""),
            rule=str(data.get("rule", "") or ""),
            rationale=str(data.get("rationale", "") or ""),
            propagation=[
                PropagationBranch.from_yaml(b) for b in (data.get("propagation") or [])
            ],
            risk=str(data.get("risk", "") or ""),
            covered_by=str(data.get("covered_by", "") or ""),
            reason=str(data.get("reason", "") or ""),
            options=[DecideOption.from_yaml(o) for o in (data.get("options") or [])],
            recommendation=str(data.get("recommendation", "") or ""),
            sub_items=[SubItem.from_yaml(s) for s in (data.get("sub_items") or [])],
            modified_files=[str(p) for p in (data.get("modified_files") or [])],
            modifications=_load_str_dict(data.get("modifications")),
            propagation_hints=_load_str_dict(data.get("propagation_hints")),
        )


@dataclass
class Proposal:
    """The full schema-aware proposal frontmatter.

    Top-level fields beyond `items` (kind/type/status/...) are kept on the
    `extra` dict so we don't strip unknown frontmatter fields on round-trip.
    """

    kind: str = "pr"
    type: str = "context-import"
    status: str = "pending"
    created_at: str = ""
    revised_at: str = ""
    inbox_sources: list[str] = field(default_factory=list)
    capture_sources: list[str] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    body: str = ""

    # ------------------------------------------------------------------ I/O

    def to_yaml(self) -> dict:
        out: dict[str, Any] = {}
        out["kind"] = self.kind
        out["type"] = self.type
        out["status"] = self.status
        if self.created_at:
            out["created_at"] = self.created_at
        if self.revised_at:
            out["revised_at"] = self.revised_at
        if self.inbox_sources:
            out["inbox_sources"] = list(self.inbox_sources)
        if self.capture_sources:
            out["capture_sources"] = list(self.capture_sources)
        if self.items:
            out["items"] = [i.to_yaml() for i in self.items]
        if self.summary:
            out["summary"] = dict(self.summary)
        # extra fields keep order at the end
        for k, v in self.extra.items():
            if k not in out:
                out[k] = v
        return out


# ----------------------------------------------------------------- helpers

_KNOWN_TOP_KEYS = {
    "kind", "type", "status", "created_at", "revised_at",
    "inbox_sources", "capture_sources", "items", "summary",
}


def _load_str_dict(raw: Any) -> dict[str, str]:
    """Coerce an optional YAML mapping into ``dict[str, str]``.

    None / empty → empty dict. Non-mapping values raise ValueError so the
    schema layer surfaces malformed YAML instead of silently dropping data.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"expected a mapping, got {type(raw).__name__}"
        )
    return {str(k): str(v) for k, v in raw.items()}


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_yaml, body). Both may be empty.

    A proposal MUST start with `---\\n`; otherwise treat the whole text as
    body and return empty frontmatter.
    """
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return "", text
    # find the closing `---` on a line by itself
    nl = text.find("\n", 4)
    rest = text
    end = -1
    # search for closing "\n---" followed by EOF or newline
    cursor = 4
    while True:
        idx = rest.find("\n---", cursor)
        if idx < 0:
            return "", text  # malformed → treat as body-only
        after = idx + 4
        if after == len(rest) or rest[after] in ("\n", "\r"):
            end = idx
            # body starts after the newline that terminates this `---` line
            body_start = after
            if body_start < len(rest) and rest[body_start] == "\r":
                body_start += 1
            if body_start < len(rest) and rest[body_start] == "\n":
                body_start += 1
            # Include the newline that precedes `---` in the frontmatter slice
            # (rest[4:end+1]) so a literal block scalar (`|`) ending on the
            # last frontmatter line still terminates on a clean line break —
            # otherwise PyYAML loads the trailing `\n` away and round-trip
            # flips the chomp indicator from `|` (clip) to `|-` (strip).
            fm_end = end + 1 if end < len(rest) and rest[end] == "\n" else end
            return rest[4:fm_end], rest[body_start:]
        cursor = after


def load_proposal(text: str) -> Proposal:
    """Parse a `proposal.md` text into a Proposal object.

    Tolerant: malformed/empty frontmatter → empty Proposal whose .body is the
    full input text. Raises ValueError only when items[]/sub_items[] is
    structurally bad (wrong types).
    """
    fm_text, body = _split_frontmatter(text)
    fm: dict[str, Any] = {}
    if fm_text.strip():
        try:
            loaded = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"frontmatter YAML parse error: {e}") from e
        if not isinstance(loaded, dict):
            raise ValueError(
                f"frontmatter must be a mapping, got {type(loaded).__name__}"
            )
        fm = loaded

    extra = {k: v for k, v in fm.items() if k not in _KNOWN_TOP_KEYS}

    items_raw = fm.get("items") or []
    if not isinstance(items_raw, list):
        raise ValueError(f"items must be a list, got {type(items_raw).__name__}")

    return Proposal(
        kind=str(fm.get("kind", "pr") or "pr"),
        type=str(fm.get("type", "context-import") or "context-import"),
        status=str(fm.get("status", "pending") or "pending"),
        created_at=str(fm.get("created_at", "") or ""),
        revised_at=str(fm.get("revised_at", "") or ""),
        inbox_sources=[str(s) for s in (fm.get("inbox_sources") or [])],
        capture_sources=[str(s) for s in (fm.get("capture_sources") or [])],
        items=[Item.from_yaml(i) for i in items_raw],
        summary=dict(fm.get("summary") or {}),
        extra=extra,
        body=body,
    )


def dump_proposal(proposal: Proposal) -> str:
    """Serialize a Proposal back to `---\\nyaml\\n---\\n\\nbody` text."""
    fm = proposal.to_yaml()
    fm_text = forge_yaml_dump(fm)
    # Do NOT rstrip: a trailing `\n` after a literal block scalar (`|`) is
    # semantically meaningful (clip vs strip indicator). Just normalize the
    # boundary so we have exactly one newline before the closing `---`.
    if not fm_text.endswith("\n"):
        fm_text += "\n"
    body = proposal.body or ""
    if body and not body.startswith("\n"):
        body = "\n" + body
    out = f"---\n{fm_text}---\n{body}"
    # Ensure file ends with exactly one trailing newline.
    return out.rstrip("\n") + "\n"


def has_schema(proposal: Proposal) -> bool:
    """True iff this proposal opts in to v0.3 schema rendering (has items)."""
    return bool(proposal.items)


def load_proposal_file(path: Path) -> Proposal:
    return load_proposal(path.read_text(encoding="utf-8"))
