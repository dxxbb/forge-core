"""forge ingest: read existing context files, dump or emit. NO LLM call.

The agent (Claude Code, Codex, etc.) IS the LLM. forge does not duplicate.

Two paths:
- Default (CLI-direct): dump everything into sp/section/workspace.md. User
  splits manually with $EDITOR.
- --emit (agent-driven): print to stdout with provenance headers; agent reads,
  classifies in own context, writes per-section files via Write tool.

Sources: --from <path>, --from-stdin, --from-claude-memory.
Discovery: --detect lists candidates without reading.
"""

from forge.ingest.classifier import classify, write_sections, IngestError

__all__ = ["classify", "write_sections", "IngestError"]
