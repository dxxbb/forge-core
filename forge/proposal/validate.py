"""Schema validator for proposal frontmatter.

Reports each violation as a ValidationIssue with a YAML-style path
(e.g. `items[2].sub_items[0].propagation`) and a hint about how to fix.

The check is structural — it confirms the schema is internally consistent and
fillable. It does NOT check that the *content* makes sense (e.g. that an
APPLY rationale is convincing); that's a human review concern.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from forge.proposal.schema import (
    Disposition,
    Item,
    Proposal,
    SubItem,
    PropagationBranch,
    PropagationNode,
    DecideOption,
    load_proposal,
)


@dataclass
class ValidationIssue:
    path: str          # e.g. "items[3].sub_items[2].rationale"
    message: str       # what's wrong
    hint: str = ""     # how to fix

    def format(self) -> str:
        out = f"{self.path}: {self.message}"
        if self.hint:
            out += f"\n  hint: {self.hint}"
        return out


# Required-fields-by-disposition table.
# Each entry says: for disposition X, these fields must be non-empty
# (additionally to monitor_info / extracted / rationale which are universal).
_REQUIRED_BY_DISPO: dict[Disposition, set[str]] = {
    Disposition.APPLY: {"propagation"},
    Disposition.COVERED: {"covered_by"},
    Disposition.ARCHIVE: {"propagation"},   # archive trail is one trivial branch
    Disposition.DECIDE: {"options"},
    Disposition.NA: {"reason"},
    Disposition.MIXED: {"sub_items"},
}


def validate_proposal(proposal: Proposal) -> list[ValidationIssue]:
    """Return list of issues; empty list means schema is complete."""
    issues: list[ValidationIssue] = []

    # ---- top-level
    if not proposal.items:
        issues.append(ValidationIssue(
            path="items",
            message="proposal has no items[] (schema not opted in)",
            hint="add at least one item describing a monitored source",
        ))
        return issues  # pointless to keep checking

    if not proposal.kind:
        issues.append(ValidationIssue("kind", "missing", "set kind: pr"))
    if not proposal.type:
        issues.append(ValidationIssue("type", "missing", "e.g. context-import"))
    if not proposal.status:
        issues.append(ValidationIssue("status", "missing", "e.g. pending / approved / rejected"))
    if not proposal.created_at:
        issues.append(ValidationIssue("created_at", "missing", "ISO-8601 timestamp"))

    # ---- items
    seen_item_ids: set[str] = set()
    seen_sub_ids_by_item: dict[str, set[str]] = {}

    for idx, item in enumerate(proposal.items):
        prefix = f"items[{idx}]"
        if not item.id:
            issues.append(ValidationIssue(f"{prefix}.id", "missing", "e.g. \"1\""))
        elif item.id in seen_item_ids:
            issues.append(ValidationIssue(f"{prefix}.id", f"duplicate id `{item.id}`"))
        seen_item_ids.add(item.id)

        if not item.monitor_info:
            issues.append(ValidationIssue(
                f"{prefix}.monitor_info",
                "missing",
                "the original monitor report line for this source",
            ))
        if not item.disposition:
            issues.append(ValidationIssue(
                f"{prefix}.disposition",
                "missing",
                "one of APPLY|COVERED|ARCHIVE|DECIDE|NA|MIXED",
            ))
            continue  # rest of checks depend on disposition

        # MIXED: requires sub_items
        if item.disposition == Disposition.MIXED:
            if not item.sub_items:
                issues.append(ValidationIssue(
                    f"{prefix}.sub_items",
                    "MIXED item must declare sub_items[]",
                    "list each sub-source as a SubItem with its own disposition",
                ))
                continue
            # validate each sub
            sub_ids: set[str] = set()
            for j, sub in enumerate(item.sub_items):
                _validate_sub_item(sub, f"{prefix}.sub_items[{j}]", item.id, sub_ids, issues)
            seen_sub_ids_by_item[item.id] = sub_ids
            # validate shared_with cross-references
            for j, sub in enumerate(item.sub_items):
                _validate_shared_with(
                    sub, f"{prefix}.sub_items[{j}]", sub_ids, issues
                )
            continue

        # Non-MIXED items: own extracted/rationale/disposition payload
        if not item.extracted:
            issues.append(ValidationIssue(
                f"{prefix}.extracted",
                "missing extracted info",
                "summarize the file path, key facts, citations",
            ))
        if not item.rationale:
            issues.append(ValidationIssue(
                f"{prefix}.rationale",
                "missing rationale",
                "why this disposition? cite covering asset / new content / boundary",
            ))

        _validate_disposition_payload(
            owner=item,
            prefix=prefix,
            issues=issues,
        )


    return issues


def _validate_sub_item(
    sub: SubItem,
    prefix: str,
    parent_id: str,
    sub_ids_seen: set[str],
    issues: list[ValidationIssue],
) -> None:
    if not sub.id:
        issues.append(ValidationIssue(f"{prefix}.id", "missing", f"e.g. \"{parent_id}.1\""))
    elif sub.id in sub_ids_seen:
        issues.append(ValidationIssue(f"{prefix}.id", f"duplicate id `{sub.id}`"))
    sub_ids_seen.add(sub.id)

    if not sub.extracted:
        issues.append(ValidationIssue(
            f"{prefix}.extracted",
            "missing extracted info",
            "what file / when / what fact / user quote",
        ))
    if not sub.disposition:
        issues.append(ValidationIssue(
            f"{prefix}.disposition",
            "missing",
            "one of APPLY|COVERED|ARCHIVE|DECIDE|NA",
        ))
        return
    if sub.disposition == Disposition.MIXED:
        issues.append(ValidationIssue(
            f"{prefix}.disposition",
            "sub-items cannot be MIXED",
            "MIXED is only valid at top-level",
        ))
        return

    if sub.disposition not in (Disposition.NA, Disposition.COVERED) and not sub.rationale:
        issues.append(ValidationIssue(
            f"{prefix}.rationale",
            "missing rationale",
            "why this disposition?",
        ))

    _validate_disposition_payload(owner=sub, prefix=prefix, issues=issues)


def _validate_shared_with(
    sub: SubItem,
    prefix: str,
    sibling_sub_ids: set[str],
    issues: list[ValidationIssue],
) -> None:
    """Check that any propagation branch's `shared_with` references valid siblings."""
    for k, branch in enumerate(sub.propagation):
        for ref in branch.shared_with:
            if ref not in sibling_sub_ids:
                issues.append(ValidationIssue(
                    f"{prefix}.propagation[{k}].shared_with",
                    f"shared_with references unknown sibling `{ref}`",
                    "must match an existing sub-item id under the same parent",
                ))


def _validate_disposition_payload(
    *,
    owner: Item | SubItem,
    prefix: str,
    issues: list[ValidationIssue],
) -> None:
    """Check disposition-specific fields on an Item or SubItem."""
    dispo = owner.disposition
    if dispo is None:
        return

    required = _REQUIRED_BY_DISPO.get(dispo, set())

    if "propagation" in required:
        if not owner.propagation:
            issues.append(ValidationIssue(
                f"{prefix}.propagation",
                f"{dispo.value} item must declare a propagation tree",
                "at least one branch with a node",
            ))
        else:
            for k, branch in enumerate(owner.propagation):
                _validate_branch(
                    branch,
                    f"{prefix}.propagation[{k}]",
                    require_modification=(dispo == Disposition.APPLY),
                    issues=issues,
                )

    if "covered_by" in required and not owner.covered_by:
        issues.append(ValidationIssue(
            f"{prefix}.covered_by",
            "COVERED item must specify covered_by",
            "e.g. `feedback-log.md §1`",
        ))

    if "options" in required:
        if not owner.options:
            issues.append(ValidationIssue(
                f"{prefix}.options",
                "DECIDE item must declare options[]",
                "at least 2 options (one can be `do nothing`)",
            ))
        else:
            seen_opt_ids: set[str] = set()
            for k, opt in enumerate(owner.options):
                opt_prefix = f"{prefix}.options[{k}]"
                if not opt.id:
                    issues.append(ValidationIssue(
                        f"{opt_prefix}.id", "missing", "e.g. \"A\""
                    ))
                elif opt.id in seen_opt_ids:
                    issues.append(ValidationIssue(
                        f"{opt_prefix}.id", f"duplicate option id `{opt.id}`"
                    ))
                seen_opt_ids.add(opt.id)
                if not opt.description:
                    issues.append(ValidationIssue(
                        f"{opt_prefix}.description",
                        "missing description",
                        "one-line summary of what this option means",
                    ))
                # propagation may be empty for the "do nothing" option, but
                # if it's non-empty each branch must have a valid node
                for m, branch in enumerate(opt.propagation):
                    _validate_branch(
                        branch,
                        f"{opt_prefix}.propagation[{m}]",
                        require_modification=False,
                        issues=issues,
                    )

    if "reason" in required and not owner.reason:
        issues.append(ValidationIssue(
            f"{prefix}.reason",
            "NA item must specify reason",
            "e.g. `auto-memory index, not asset content`",
        ))


def _validate_branch(
    branch: PropagationBranch,
    prefix: str,
    *,
    require_modification: bool,
    issues: list[ValidationIssue],
) -> None:
    if not branch.branch:
        issues.append(ValidationIssue(
            f"{prefix}.branch", "missing branch label", "e.g. 'a' / 'b' / 'c'"
        ))
    _validate_node(
        branch.node, f"{prefix}.node",
        require_modification=require_modification,
        issues=issues,
    )


def _validate_node(
    node: PropagationNode,
    prefix: str,
    *,
    require_modification: bool,
    issues: list[ValidationIssue],
) -> None:
    has_path = bool(node.path)
    has_label = bool(node.label or node.layer)
    if not (has_path or has_label):
        issues.append(ValidationIssue(
            f"{prefix}", "node has neither path nor label",
            "give the file path or describe what this node represents",
        ))
    is_terminal = node.terminal or not node.children
    if require_modification and not node.modification and not is_terminal:
        issues.append(ValidationIssue(
            f"{prefix}.modification",
            "non-terminal APPLY node must specify modification",
            "describe what changes here (line count / what's added)",
        ))
    for k, child in enumerate(node.children):
        _validate_branch(
            child, f"{prefix}.children[{k}]",
            require_modification=require_modification,
            issues=issues,
        )


def validate_file(path: Path) -> list[ValidationIssue]:
    """Convenience: load + validate a `proposal.md` file."""
    text = path.read_text(encoding="utf-8")
    try:
        proposal = load_proposal(text)
    except ValueError as e:
        return [ValidationIssue("proposal", str(e), "fix YAML frontmatter")]
    return validate_proposal(proposal)
