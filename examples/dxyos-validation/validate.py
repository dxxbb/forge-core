"""End-to-end validation: run forge-core on a real dxyOS workspace.

Usage:
    python validate.py [--dxyos-root ~/dxy_OS]

Copies the five dxyOS SP sections into a staging directory, writes a
forge-compatible config, and runs the full flow: init → build → snapshot →
mutate → diff → approve → second snapshot → compare.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE / "_staging"

# The five canonical sections that dxyOS maintains.
SECTION_FILES = [
    "about user.md",
    "workspace.md",
    "knowledge base.md",
    "preference.md",
    "skill.md",
]

CONFIG_CLAUDE = """---
name: master
target: claude-code
sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
preamble: |
  Compiled personal context for Claude Code. Five sections from dxyOS SP.
---
"""

CONFIG_AGENTS = """---
name: master-agents
target: agents-md
sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
preamble: |
  Compiled personal context for AGENTS.md-compatible runtimes.
---
"""


def stage_dxyos(dxyos_root: Path) -> Path:
    """Copy dxyOS sections into STAGING/sp/ with forge-core's expected layout."""
    src_section_dir = dxyos_root / "01 assist" / "SP" / "section"
    if not src_section_dir.exists():
        raise SystemExit(f"not a dxyOS root: {dxyos_root} (missing {src_section_dir})")

    if STAGING.exists():
        shutil.rmtree(STAGING)
    section_dir = STAGING / "sp" / "section"
    config_dir = STAGING / "sp" / "config"
    section_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    copied: list[str] = []
    missing: list[str] = []
    for fname in SECTION_FILES:
        src = src_section_dir / fname
        if not src.exists():
            missing.append(fname)
            continue
        shutil.copy2(src, section_dir / fname)
        copied.append(fname)

    if missing:
        print(f"WARN: missing sections: {missing}")

    (config_dir / "master.md").write_text(CONFIG_CLAUDE, encoding="utf-8")
    (config_dir / "master-agents.md").write_text(CONFIG_AGENTS, encoding="utf-8")

    print(f"staged {len(copied)} sections + 2 configs into {STAGING}")
    return STAGING


def run(root: Path, dxyos_root: Path) -> None:
    """Run the full flow and report metrics."""
    # Imports are local so the script fails loudly if forge-core isn't installed.
    from forge.compiler.loader import load_sections, load_all_configs
    from forge.gate import actions as gate
    from forge.bench import harness as bench

    print("=" * 60)
    print("step 1/6: load sections")
    sections = load_sections(root)
    for name, sec in sections.items():
        print(f"  loaded `{name}` ({sec.byte_size}B, {sec.line_count}L)")
    assert len(sections) == 5, f"expected 5 sections, got {len(sections)}"

    print()
    print("step 2/6: load configs")
    configs = load_all_configs(root)
    for name, cfg in configs.items():
        print(f"  loaded `{name}` target={cfg.target} sections={cfg.sections}")
    assert len(configs) == 2, f"expected 2 configs, got {len(configs)}"

    print()
    print("step 3/6: init + build")
    if (root / ".forge").exists():
        shutil.rmtree(root / ".forge")
    state = gate.init(root)
    print(f"  .forge initialized at {state.forge_dir}")
    output_dir = state.output_dir
    outputs = sorted(output_dir.glob("*.md"))
    assert len(outputs) == 2, f"expected 2 output files, got {len(outputs)}"

    print()
    print("step 4/6: content completeness check")
    compiled_claude = (output_dir / "CLAUDE.md").read_text(encoding="utf-8")
    compiled_agents = (output_dir / "AGENTS.md").read_text(encoding="utf-8")
    for sname, sec in sections.items():
        # pick a distinctive substring from the section body (first 40 chars of first non-empty line)
        body_lines = [line for line in sec.body.splitlines() if line.strip()]
        if not body_lines:
            continue
        needle = body_lines[0][:40]
        if needle in compiled_claude and needle in compiled_agents:
            print(f"  [ok]    `{sname}` present in both outputs")
        else:
            print(f"  [FAIL]  `{sname}` missing (needle={needle!r})")
            raise SystemExit(1)

    print()
    print("step 5/6: compare against dxyOS's hand-compiled CLAUDE.md")
    dxyos_claude = dxyos_root / "CLAUDE.md"
    if dxyos_claude.exists():
        existing = dxyos_claude.read_text(encoding="utf-8")
        ex_bytes = len(existing.encode("utf-8"))
        compiled_bytes = len(compiled_claude.encode("utf-8"))
        ratio = compiled_bytes / ex_bytes if ex_bytes else 0
        print(f"  dxyOS CLAUDE.md      : {ex_bytes}B")
        print(f"  forge-core CLAUDE.md : {compiled_bytes}B ({ratio:.2f}x)")
        # dxyOS uses @-imports so its own CLAUDE.md can be shorter; our compiled version
        # includes the resolved section bodies inline. We just note the ratio.
    else:
        print(f"  (no {dxyos_claude} to compare against, skipped)")

    print()
    print("step 6/6: gate + bench flow on real content")
    snap_v1 = bench.snapshot(root, "dxyos-v1")
    print(f"  snapshot v1: {list(snap_v1.outputs.keys())}")
    # mutate: append a tiny note to preference section
    pref = root / "sp" / "section" / "preference.md"
    if pref.exists():
        pref.write_text(
            pref.read_text(encoding="utf-8") + "\n\n- (validation marker)\n",
            encoding="utf-8",
        )
        diff = gate.diff_summary(root)
        assert diff.changed, "expected diff to show changes after mutation"
        print(f"  diff: {len(diff.output_diffs)} output file(s) would change")
        result = gate.approve(root, note="validation marker")
        print(f"  approved hash={result.approved_hash[:12]}")
        snap_v2 = bench.snapshot(root, "dxyos-v2")
        cmp = bench.compare(root, "dxyos-v1", "dxyos-v2")
        for fname, d in cmp.output_deltas.items():
            sign = "+" if d["bytes_delta"] >= 0 else ""
            print(
                f"  {fname} delta: {sign}{d['bytes_delta']}B, {sign}{d['lines_delta']}L"
            )

    print()
    print("=" * 60)
    print("VALIDATION PASSED")
    print(f"  5 sections loaded, 2 configs, 2 outputs rendered")
    print(f"  full gate + bench flow completed on real dxyOS content")
    print(f"  staging: {root}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--dxyos-root",
        default="~/dxy_OS",
        help="Path to dxyOS workspace root (default: ~/dxy_OS)",
    )
    args = p.parse_args()
    dxyos_root = Path(args.dxyos_root).expanduser().resolve()
    staging = stage_dxyos(dxyos_root)
    run(staging, dxyos_root)


if __name__ == "__main__":
    main()
