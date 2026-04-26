"""Gate actions: init / diff / approve / reject / build / status."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.compiler.renderer import render
from forge.gate.diff import source_diff, output_diff
from forge.gate.state import GateState, hash_sp
from forge.gate.sync import sync_targets
from forge.targets import get_adapter


@dataclass
class DiffResult:
    source_diff_lines: list[str]
    output_diffs: dict[str, list[str]]  # config_name -> unified diff lines
    changed: bool


@dataclass
class ApproveResult:
    approved_hash: str
    approved_at: str
    outputs_written: list[Path]
    targets_synced: list[tuple[str, Path]] = field(default_factory=list)


def init(root: Path, force: bool = False) -> GateState:
    """Initialize .forge/ by snapshotting current sp/ as the first approved baseline."""
    state = GateState(root)
    if state.initialized() and not force:
        raise RuntimeError(
            f".forge/ already initialized at {state.forge_dir}. Use force=True to re-init."
        )
    state.forge_dir.mkdir(exist_ok=True)
    state.migrate_layout()
    if state.approved_sp.exists():
        shutil.rmtree(state.approved_sp)
    if state.current_sp.exists():
        shutil.copytree(state.current_sp, state.approved_sp)
    else:
        state.approved_sp.mkdir(parents=True, exist_ok=True)
    state.output_dir.mkdir(exist_ok=True)
    h = hash_sp(state.approved_sp)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state.write_manifest({"approved_hash": h, "approved_at": now, "version": "0.1.0"})
    if not state.changelog_path.exists():
        state.changelog_path.write_text(
            f"# forge-core changelog\n\n- {now} init (hash={h[:12]})\n", encoding="utf-8"
        )
    _rebuild_outputs(state)
    return state


def diff_summary(root: Path) -> DiffResult:
    """Return a full diff: source-level + per-config output-level."""
    state = GateState(root)
    _require_initialized(state)
    state.migrate_layout()
    src_diff = source_diff(state.approved_sp, state.current_sp)

    approved_sections = load_sections(state.approved_sp.parent)
    approved_configs = load_all_configs(state.approved_sp.parent)
    current_sections = load_sections(state.root)
    current_configs = load_all_configs(state.root)

    out_diffs: dict[str, list[str]] = {}
    all_config_names = sorted(set(approved_configs) | set(current_configs))
    for cname in all_config_names:
        a_text = ""
        b_text = ""
        if cname in approved_configs:
            a_text = render(approved_sections, approved_configs[cname])
        if cname in current_configs:
            b_text = render(current_sections, current_configs[cname])
        od = output_diff(a_text, b_text, label=cname)
        if od:
            out_diffs[cname] = od

    changed = bool(src_diff or out_diffs)
    return DiffResult(source_diff_lines=src_diff, output_diffs=out_diffs, changed=changed)


def approve(root: Path, note: str = "") -> ApproveResult:
    """Promote current sp/ to approved/, rebuild outputs, log, sync targets."""
    state = GateState(root)
    _require_initialized(state)
    state.migrate_layout()

    # 1. compute hash of proposed state
    new_hash = hash_sp(state.current_sp)

    # 2. replace approved/ with current sp/
    if state.approved_sp.exists():
        shutil.rmtree(state.approved_sp)
    shutil.copytree(state.current_sp, state.approved_sp)

    # 3. render outputs
    written = _rebuild_outputs(state)

    # 4. update manifest
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = state.read_manifest()
    manifest.update({"approved_hash": new_hash, "approved_at": now})
    state.write_manifest(manifest)

    # 5. changelog
    line = f"- {now} approve (hash={new_hash[:12]})"
    if note:
        line += f" — {note}"
    if not state.changelog_path.exists():
        state.changelog_path.write_text(
            f"# forge-core changelog\n\n", encoding="utf-8"
        )
    with state.changelog_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

    # 6. push to configured external targets (e.g. ~/.claude/CLAUDE.md)
    synced = sync_targets(state)

    return ApproveResult(
        approved_hash=new_hash,
        approved_at=now,
        outputs_written=written,
        targets_synced=synced,
    )


def reject(root: Path) -> None:
    """Discard current sp/ changes, restore from approved/."""
    state = GateState(root)
    _require_initialized(state)
    if state.current_sp.exists():
        shutil.rmtree(state.current_sp)
    shutil.copytree(state.approved_sp, state.current_sp)


def build(root: Path) -> list[Path]:
    """Render output/ from current sp/ WITHOUT going through the gate.

    Use this in CI, fresh clones, or when you just want to regenerate outputs
    from approved state (it reads `sp/` not `.forge/approved/sp/`).
    """
    state = GateState(root)
    state.migrate_layout()
    if not state.output_dir.exists():
        state.output_dir.mkdir(parents=True, exist_ok=True)
    return _rebuild_outputs(state)


def status(root: Path) -> dict:
    state = GateState(root)
    info: dict = {"initialized": state.initialized()}
    if state.initialized():
        info["manifest"] = state.read_manifest()
        info["current_hash"] = hash_sp(state.current_sp)
        info["drifted"] = info["current_hash"] != info["manifest"].get("approved_hash")
    return info


# ----- internal -----

def _require_initialized(state: GateState) -> None:
    if not state.initialized():
        raise RuntimeError(
            f"forge not initialized at {state.root}. Run `forge init` first."
        )


def _rebuild_outputs(state: GateState) -> list[Path]:
    """Render all configs under sp/ (current) and write to output/."""
    sections = load_sections(state.root)
    configs = load_all_configs(state.root)
    state.output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    # clear stale outputs
    for p in state.output_dir.glob("*.md"):
        p.unlink()
    for cname, cfg in configs.items():
        adapter = get_adapter(cfg.target)
        text = render(sections, cfg)
        filename = adapter.filename(cfg)
        path = state.output_dir / filename
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written
