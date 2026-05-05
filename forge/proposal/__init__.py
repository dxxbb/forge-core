"""forge proposal — review-gated PR proposal schema, validation, rendering.

A `proposal.md` under `system/pr/<id>/` is the artifact agents present to the
user for approval. v0.3 adds an opt-in YAML schema in the proposal frontmatter
that captures the §0.5 "monitor item view" tree (per-item disposition +
propagation tree). When that schema is present, `forge pr render` can produce
a deterministic, human-readable §0.5 view from the data — agents stop hand-
writing markdown trees, and rendering becomes consistent across PRs.

The schema is opt-in: proposals without an `items:` block continue to work
under `forge pr done` / `forge approve` exactly as before.

Modules:
  schema   — dataclasses + load/dump for the proposal frontmatter
  validate — schema-completeness checks (forge proposal validate)
  renderer — deterministic text rendering (forge pr render)
  scaffold — `forge proposal new` stub generator
"""

from forge.proposal.schema import (
    Proposal,
    Item,
    SubItem,
    PropagationBranch,
    PropagationNode,
    DecideOption,
    Disposition,
    load_proposal,
    dump_proposal,
)
from forge.proposal.validate import validate_proposal, ValidationIssue

__all__ = [
    "Proposal",
    "Item",
    "SubItem",
    "PropagationBranch",
    "PropagationNode",
    "DecideOption",
    "Disposition",
    "load_proposal",
    "dump_proposal",
    "validate_proposal",
    "ValidationIssue",
]
