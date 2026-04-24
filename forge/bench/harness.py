"""Structural bench: snapshot compiled outputs, then compare two snapshots."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.gate.state import GateState


@dataclass
class Snapshot:
    name: str
    created_at: str
    outputs: dict[str, dict]  # filename -> {bytes, lines, section_sizes}
    sections: dict[str, dict]  # section_name -> {bytes, lines}


@dataclass
class Comparison:
    before: str
    after: str
    output_deltas: dict[str, dict]  # filename -> {bytes_before, bytes_after, bytes_delta, ...}
    section_deltas: dict[str, dict]  # section_name -> {bytes_before, bytes_after, bytes_delta}
    added_sections: list[str]
    removed_sections: list[str]


def _bench_dir(root: Path) -> Path:
    return GateState(root).forge_dir / "bench"


def snapshot(root: Path, name: str) -> Snapshot:
    """Capture a named snapshot of current compiled outputs + section metadata."""
    state = GateState(root)
    if not state.output_dir.exists():
        raise RuntimeError(
            f"no compiled outputs at {state.output_dir}. Run `forge build` or `forge approve` first."
        )
    bdir = _bench_dir(root) / name
    bdir.mkdir(parents=True, exist_ok=True)

    # copy output files
    out_info: dict[str, dict] = {}
    for src in sorted(state.output_dir.glob("*.md")):
        dst = bdir / src.name
        shutil.copy2(src, dst)
        text = src.read_text(encoding="utf-8")
        out_info[src.name] = {
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n") + (1 if text else 0),
        }

    # section sizes (from current sp/)
    sec_info: dict[str, dict] = {}
    for s in load_sections(root).values():
        sec_info[s.name] = {"bytes": s.byte_size, "lines": s.line_count}

    snap = Snapshot(
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        outputs=out_info,
        sections=sec_info,
    )
    (bdir / "manifest.json").write_text(
        json.dumps(asdict(snap), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return snap


def list_snapshots(root: Path) -> list[str]:
    bd = _bench_dir(root)
    if not bd.exists():
        return []
    return sorted(p.name for p in bd.iterdir() if p.is_dir())


def compare(root: Path, before: str, after: str) -> Comparison:
    """Structurally compare two named snapshots."""
    a = _load_snap(root, before)
    b = _load_snap(root, after)

    out_deltas: dict[str, dict] = {}
    all_out = sorted(set(a.outputs) | set(b.outputs))
    for fname in all_out:
        ax = a.outputs.get(fname, {"bytes": 0, "lines": 0})
        bx = b.outputs.get(fname, {"bytes": 0, "lines": 0})
        out_deltas[fname] = {
            "bytes_before": ax["bytes"],
            "bytes_after": bx["bytes"],
            "bytes_delta": bx["bytes"] - ax["bytes"],
            "lines_before": ax["lines"],
            "lines_after": bx["lines"],
            "lines_delta": bx["lines"] - ax["lines"],
        }

    sec_deltas: dict[str, dict] = {}
    added: list[str] = []
    removed: list[str] = []
    all_sec = sorted(set(a.sections) | set(b.sections))
    for sname in all_sec:
        if sname not in a.sections:
            added.append(sname)
            bx = b.sections[sname]
            sec_deltas[sname] = {
                "bytes_before": 0,
                "bytes_after": bx["bytes"],
                "bytes_delta": bx["bytes"],
            }
            continue
        if sname not in b.sections:
            removed.append(sname)
            ax = a.sections[sname]
            sec_deltas[sname] = {
                "bytes_before": ax["bytes"],
                "bytes_after": 0,
                "bytes_delta": -ax["bytes"],
            }
            continue
        ax = a.sections[sname]
        bx = b.sections[sname]
        if ax["bytes"] != bx["bytes"]:
            sec_deltas[sname] = {
                "bytes_before": ax["bytes"],
                "bytes_after": bx["bytes"],
                "bytes_delta": bx["bytes"] - ax["bytes"],
            }

    return Comparison(
        before=before,
        after=after,
        output_deltas=out_deltas,
        section_deltas=sec_deltas,
        added_sections=added,
        removed_sections=removed,
    )


def _load_snap(root: Path, name: str) -> Snapshot:
    path = _bench_dir(root) / name / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"snapshot not found: {name} ({path})")
    data = json.loads(path.read_text(encoding="utf-8"))
    return Snapshot(**data)
