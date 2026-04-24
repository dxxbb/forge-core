"""End-to-end validation: run forge-core on a real dxyOS workspace.

Usage:
    python validate.py [--dxyos-root ~/dxy_OS] [--verbose]

Takes the five dxyOS SP sections and validates forge-core can produce a compiled
CLAUDE.md that is *semantically equivalent* to dxyOS's hand-maintained SP output.

Steps:
    1. Load all 5 sections (with spaces in filenames, dxyOS-style frontmatter).
    2. Load 2 forge-compatible configs.
    3. Run init + build; verify outputs exist and are reproducible.
    4. Semantic equivalence: line-level recall of dxyOS's own SP-compiled CLAUDE.md
       inside forge-core's CLAUDE.md (>= threshold).
    5. Completeness: every section body contributes to the compiled output.
    6. forge doctor: schema health check passes.
    7. Full gate + bench round-trip: snapshot, mutate, diff, approve, snapshot, compare.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
STAGING = HERE / "_staging"

SECTION_FILES = [
    "about user.md",
    "workspace.md",
    "knowledge base.md",
    "preference.md",
    "skill.md",
]

PREFACE_SECTION = """---
name: _preface
type: wrapper
---

Compiled personal context. Five SP sections (dxyOS MVP schema).
"""

CONFIG_CLAUDE = """---
name: master
target: claude-code
sections:
  - _preface
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
required_sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
demote_section_headings: true
---
"""

CONFIG_AGENTS = """---
name: master-agents
target: agents-md
sections:
  - _preface
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
required_sections:
  - about user
  - workspace
  - knowledge base
  - preference
  - skill
demote_section_headings: true
---
"""

# Threshold for line-level recall vs dxyOS's own SP output.
# Lower than 1.0 because forge-core wraps sections with its own headers/provenance,
# and dxyOS's compiled CLAUDE.md has its own wrapper text. The real content lines
# should all appear.
RECALL_THRESHOLD = 0.90


def stage_dxyos(dxyos_root: Path) -> Path:
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

    (section_dir / "_preface.md").write_text(PREFACE_SECTION, encoding="utf-8")
    (config_dir / "master.md").write_text(CONFIG_CLAUDE, encoding="utf-8")
    (config_dir / "master-agents.md").write_text(CONFIG_AGENTS, encoding="utf-8")

    print(f"staged {len(copied)} sections + 1 wrapper + 2 configs into {STAGING}")
    return STAGING


def normalize_lines(text: str) -> list[str]:
    """Return non-empty, non-trivial content lines (stripped). Drops headers, YAML, comments."""
    out: list[str] = []
    in_fm = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line == "---":
            in_fm = not in_fm
            continue
        if in_fm:
            continue
        # skip our own provenance comments
        if line.startswith("<!--") or line.startswith("-->") or line.startswith("> forge-core"):
            continue
        # skip ATX headers — we only care about body content
        if line.lstrip().startswith("#"):
            continue
        out.append(line.strip())
    return out


def line_recall(source_lines: list[str], target_text: str) -> float:
    """Fraction of meaningful source lines that appear as a substring in target."""
    if not source_lines:
        return 1.0
    hit = 0
    for line in source_lines:
        # use the first 60 chars as a robust needle (chinese/english mixed safe)
        needle = line[:60] if len(line) > 10 else line
        if needle and needle in target_text:
            hit += 1
    return hit / len(source_lines)


def run(root: Path, dxyos_root: Path, verbose: bool) -> None:
    from forge.compiler.loader import load_sections, load_all_configs
    from forge.gate import actions as gate
    from forge.gate.doctor import run as doctor
    from forge.bench import harness as bench

    divider = "=" * 64
    print(divider)
    print("STEP 1/7 — load sections")
    sections = load_sections(root)
    for name, sec in sections.items():
        print(f"  [ok] `{name}` {sec.byte_size}B / {sec.line_count}L  kind={sec.kind or '-'} upstream={len(sec.upstream)}")
    # 5 content sections + 1 wrapper section
    assert len(sections) == 6, f"expected 6 sections (5 content + 1 wrapper), got {len(sections)}"

    print()
    print("STEP 2/7 — load configs")
    configs = load_all_configs(root)
    for name, cfg in configs.items():
        print(f"  [ok] `{name}` target={cfg.target} required={len(cfg.required_sections)}")
    assert len(configs) == 2

    print()
    print("STEP 3/7 — init + build")
    if (root / ".forge").exists():
        shutil.rmtree(root / ".forge")
    state = gate.init(root)
    compiled_claude = (state.output_dir / "CLAUDE.md").read_text("utf-8")
    compiled_agents = (state.output_dir / "AGENTS.md").read_text("utf-8")
    print(f"  [ok] CLAUDE.md {len(compiled_claude.encode('utf-8'))}B / {compiled_claude.count(chr(10))}L")
    print(f"  [ok] AGENTS.md {len(compiled_agents.encode('utf-8'))}B / {compiled_agents.count(chr(10))}L")
    # determinism
    time.sleep(1.1)
    gate.build(root)
    compiled_claude_2 = (state.output_dir / "CLAUDE.md").read_text("utf-8")
    assert compiled_claude == compiled_claude_2, "compile is not deterministic"
    print("  [ok] compile is deterministic")

    print()
    print("STEP 4/7 — semantic equivalence vs dxyOS's SP output")
    dxyos_sp_output = dxyos_root / "01 assist" / "SP" / "output" / "claude code" / "CLAUDE.md"
    if dxyos_sp_output.exists():
        dxyos_claude = dxyos_sp_output.read_text("utf-8")
        dxyos_lines = normalize_lines(dxyos_claude)
        recall_claude = line_recall(dxyos_lines, compiled_claude)
        recall_agents = line_recall(dxyos_lines, compiled_agents)
        print(f"  dxyOS SP output    : {len(dxyos_claude.encode('utf-8'))}B ({len(dxyos_lines)} content lines)")
        print(f"  forge CLAUDE.md    : {len(compiled_claude.encode('utf-8'))}B")
        print(f"  line recall CLAUDE : {recall_claude:.1%} (threshold {RECALL_THRESHOLD:.0%})")
        print(f"  line recall AGENTS : {recall_agents:.1%}")
        if recall_claude < RECALL_THRESHOLD:
            if verbose:
                miss = [l for l in dxyos_lines if l[:60] not in compiled_claude]
                print(f"  missing lines ({len(miss)}):")
                for m in miss[:20]:
                    print(f"    - {m[:120]}")
            raise SystemExit(f"FAIL: recall {recall_claude:.1%} below threshold {RECALL_THRESHOLD:.0%}")
        print(f"  [ok] semantic equivalence >= {RECALL_THRESHOLD:.0%}")
    else:
        print(f"  (skipped — no {dxyos_sp_output} to compare against)")

    print()
    print("STEP 5/7 — per-section completeness")
    for sname, sec in sections.items():
        body_lines = [l for l in sec.body.splitlines() if l.strip() and not l.startswith("#")]
        if not body_lines:
            continue
        needle = body_lines[0][:40]
        if needle in compiled_claude and needle in compiled_agents:
            print(f"  [ok] `{sname}` body present in both outputs")
        else:
            raise SystemExit(f"FAIL: `{sname}` missing (needle={needle!r})")

    print()
    print("STEP 6/7 — forge doctor")
    report = doctor(root)
    for line in report.format_lines():
        print(f"  {line}")
    if not report.ok:
        raise SystemExit("FAIL: doctor reported errors")
    print("  [ok] no doctor errors")

    print()
    print("STEP 7/7 — full gate + bench round-trip on real content")
    snap_v1 = bench.snapshot(root, "dxyos-v1")
    pref = root / "sp" / "section" / "preference.md"
    if pref.exists():
        pref.write_text(
            pref.read_text("utf-8") + "\n\n- (validation marker added by validate.py)\n",
            encoding="utf-8",
        )
        diff = gate.diff_summary(root)
        assert diff.changed, "expected diff to show changes"
        result = gate.approve(root, note="validation marker")
        snap_v2 = bench.snapshot(root, "dxyos-v2")
        cmp = bench.compare(root, "dxyos-v1", "dxyos-v2")
        for fname, d in cmp.output_deltas.items():
            sign = "+" if d["bytes_delta"] >= 0 else ""
            print(f"  [ok] {fname} delta {sign}{d['bytes_delta']}B / {sign}{d['lines_delta']}L")

    print()
    print("STEP BONUS — writing side-by-side diff for human review")
    if dxyos_sp_output.exists():
        import difflib
        dxyos_claude_text = dxyos_sp_output.read_text("utf-8")
        forge_claude_text = (state.output_dir / "CLAUDE.md").read_text("utf-8")
        diff_lines = list(
            difflib.unified_diff(
                dxyos_claude_text.splitlines(),
                forge_claude_text.splitlines(),
                fromfile="dxyOS/01 assist/SP/output/claude code/CLAUDE.md",
                tofile="forge-core/.forge/output/CLAUDE.md",
                lineterm="",
            )
        )
        diff_path = root / "diff-vs-dxyos.txt"
        diff_path.write_text("\n".join(diff_lines) + "\n", encoding="utf-8")
        print(f"  wrote {diff_path} ({len(diff_lines)} diff lines)")

    print()
    print(divider)
    print("VALIDATION PASSED")
    print(f"  5 sections / 2 configs / 2 outputs / doctor clean / gate + bench round-trip ok")
    print(f"  staging: {root}")
    print(f"  for side-by-side comparison: less {root}/diff-vs-dxyos.txt")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dxyos-root", default="~/dxy_OS", help="Path to dxyOS workspace root")
    p.add_argument("--verbose", action="store_true", help="Dump missing lines on recall failure")
    args = p.parse_args()
    dxyos_root = Path(args.dxyos_root).expanduser().resolve()
    staging = stage_dxyos(dxyos_root)
    run(staging, dxyos_root, verbose=args.verbose)


if __name__ == "__main__":
    main()
