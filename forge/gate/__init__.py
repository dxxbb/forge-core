"""Gate: PR-style review flow for canonical source changes.

State lives in `.forge/` at the workspace root:

    .forge/
        approved/
            sp/section/*.md
            sp/config/*.md
        output/<config-name>.md   # last rendered outputs
        changelog.md              # append-only audit
        manifest.json             # { approved_hash, approved_at, adapter_versions, ... }
"""

from forge.gate.state import GateState
from forge.gate.diff import source_diff, output_diff
from forge.gate.actions import init, diff_summary, approve, reject, build, status
from forge.gate.doctor import run as doctor, DoctorReport

__all__ = [
    "GateState",
    "source_diff",
    "output_diff",
    "init",
    "diff_summary",
    "approve",
    "reject",
    "build",
    "status",
    "doctor",
    "DoctorReport",
]
