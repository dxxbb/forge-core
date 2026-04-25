"""forge ingest: import an existing CLAUDE.md / .cursorrules / similar file
into a forge workspace by classifying it into the 5 SP MVP sections.

Two paths:
- LLM path (default): call Anthropic API with a fixed classification prompt,
  get JSON back, write each non-empty section to sp/section/<name>.md.
- --no-llm path: dump everything into sp/section/imported.md as one block,
  user splits manually.

The LLM path is what the project's "review-gate" architecture is *built for*:
the LLM proposes a classification, forge writes it to working tree, user
reviews via `forge diff`, edits anything wrong, then `forge approve`. Bad
classification doesn't matter — it lands in working tree, not approved state.
"""

from forge.ingest.classifier import classify, write_sections, IngestError

__all__ = ["classify", "write_sections", "IngestError"]
