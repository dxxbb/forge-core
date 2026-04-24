"""Bench: minimal structural before/after harness for compiled outputs.

v0.1 answers "did my change to sp/ do what I expected structurally?" — not
"is the agent smarter?" The latter comes in v0.3 with real agent runs.
"""

from forge.bench.harness import snapshot, compare, list_snapshots, Snapshot, Comparison

__all__ = ["snapshot", "compare", "list_snapshots", "Snapshot", "Comparison"]
