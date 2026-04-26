"""Gate actions: init / diff / approve / reject / build / status.

v0.2: git is the substrate. approve = git commit, reject = git restore from HEAD,
      diff = git diff HEAD + output rebuild preview, hash = HEAD commit hash.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from forge.compiler.loader import load_sections, load_all_configs
from forge.compiler.renderer import render
from forge.gate import _git
from forge.gate.diff import source_diff_via_git, output_diff
from forge.gate.origin import clear as clear_origin
from forge.gate.state import GateState
from forge.gate.sync import sync_targets
from forge.targets import get_adapter


@dataclass
class DiffResult:
    source_diff_lines: list[str]
    output_diffs: dict[str, list[str]]
    changed: bool


@dataclass
class ApproveResult:
    approved_hash: str  # git commit hash (full)
    approved_at: str  # ISO timestamp
    outputs_written: list[Path]
    targets_synced: list[tuple[str, Path]] = field(default_factory=list)


def init(root: Path, force: bool = False) -> GateState:
    """Bring a v0.1 workspace into v0.2 (or no-op if already v0.2).

    v0.2 doesn't have a separate `forge init` step — `forge new` already
    git-inits and makes the first commit. This function exists for backward
    compatibility: it's still called by some tests/flows that scaffold then
    init separately.

    What it does:
      1. Run silent v0.1.0→v0.1.1 layout migration (.forge/output/ → output/).
      2. If not yet a git repo: git init, write .gitignore, make initial commit
         covering sp/ + output/.
      3. Otherwise: no-op (workspace already initialized).
    """
    state = GateState(root)
    state.migrate_layout()
    if state.initialized() and not force:
        # already v0.2-ready
        _ensure_manifest(state)
        return state

    # Need to initialize git
    if not _git.is_git_repo(root):
        _git.init_repo(root)

    _ensure_gitignore(root)

    # Build output once before initial commit so the commit is complete
    state.output_dir.mkdir(parents=True, exist_ok=True)
    _rebuild_outputs(state)

    # Initial commit (or follow-up commit if user already had one)
    _git.add(root, ["sp", "output", ".gitignore"])
    if _git.has_pending_changes(root, ["sp", "output", ".gitignore"]) or not _git.head_hash(root):
        _git.commit(
            root,
            "forge init: scaffold sp/ and first output/ build",
            allow_empty=not _git.head_hash(root),
        )

    _ensure_manifest(state)
    return state


def diff_summary(root: Path) -> DiffResult:
    """Return a full diff: source-level (vs HEAD) + per-config output-level."""
    state = GateState(root)
    _require_initialized(state)
    state.migrate_layout()

    # Source diff: git diff HEAD -- sp/
    src_diff = source_diff_via_git(root)

    # Output diff: render approved (HEAD's sp/) and current sp/, compare per config
    approved_sections = _load_sections_at_head(state)
    approved_configs = _load_configs_at_head(state)
    current_sections = load_sections(root)
    current_configs = load_all_configs(root)

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
    """Rebuild output/ → stage sp/ + output/ → git commit (with provenance trailer)
    → clear pending → sync external targets."""
    state = GateState(root)
    _require_initialized(state)
    state.migrate_layout()

    # 1. rebuild output/ from current sp/
    written = _rebuild_outputs(state)

    # 2. stage sp/ + output/ (only what changed)
    paths_to_stage = ["sp", "output"]
    _git.add(root, paths_to_stage)

    # 3. nothing actually changed? bail with clear error
    if not _git.has_pending_changes(root, paths_to_stage):
        # Could be the rebuild produced identical output AND sp/ was unchanged.
        # Reset stage and complain.
        raise RuntimeError(
            "no changes to approve — sp/ matches HEAD and rebuilt output is identical"
        )

    # 4. commit
    commit_message = note.strip() or "forge approve"
    new_hash = _git.commit(
        root,
        commit_message,
        trailers={"forge-provenance": f"version=0.2.0 source=forge-approve"},
    )

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # 5. update manifest (just for target bindings + last-known hash convenience)
    manifest = state.read_manifest()
    manifest.update({"approved_hash": new_hash, "approved_at": now, "version": "0.2.0"})
    state.write_manifest(manifest)

    # 6. push to configured external targets
    synced = sync_targets(state)

    # 7. clear pending-change log + stale REVIEW.md
    clear_origin(root)
    _clear_review_md(root)

    return ApproveResult(
        approved_hash=new_hash,
        approved_at=now,
        outputs_written=written,
        targets_synced=synced,
    )


def reject(root: Path) -> None:
    """Discard working-tree changes to sp/ + output/, restore from HEAD."""
    state = GateState(root)
    _require_initialized(state)
    state.migrate_layout()
    _git.restore_to_head(root, ["sp", "output"])
    clear_origin(root)
    _clear_review_md(root)


def _clear_review_md(root: Path) -> None:
    """Delete REVIEW.md (the agent-rendered review doc) — it's stale once
    approve/reject runs. The .gitignore entry stays so future writes don't
    pollute git either."""
    p = root / "REVIEW.md"
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def build(root: Path) -> list[Path]:
    """Render output/ from current sp/ WITHOUT going through the gate.

    Use this in CI / fresh clones / regenerating output when the file got
    deleted but you don't want to commit a no-op.
    """
    state = GateState(root)
    state.migrate_layout()
    state.output_dir.mkdir(parents=True, exist_ok=True)
    return _rebuild_outputs(state)


def status(root: Path) -> dict:
    state = GateState(root)
    info: dict = {"initialized": state.initialized()}
    if state.initialized():
        head = _git.head_hash(root)
        info["manifest"] = state.read_manifest()
        info["approved_hash"] = head  # = HEAD
        info["drifted"] = _git.has_pending_changes(root, ["sp", "output"])
        info["needs_v02_migration"] = state.needs_v02_migration()
    return info


# ----- internal -----

def _require_initialized(state: GateState) -> None:
    if not state.initialized():
        raise RuntimeError(
            f"forge not initialized at {state.root}. "
            f"Workspace must be a git repo with sp/. Run `forge init` or "
            f"`forge new <path>` to scaffold one."
        )


def _ensure_gitignore(root: Path) -> None:
    gi = root / ".gitignore"
    line = ".forge/\n"
    if gi.exists():
        existing = gi.read_text(encoding="utf-8")
        if ".forge/" not in existing:
            gi.write_text(existing.rstrip("\n") + "\n" + line, encoding="utf-8")
    else:
        gi.write_text(line, encoding="utf-8")


def _ensure_manifest(state: GateState) -> None:
    if not state.manifest_path.exists():
        head = _git.head_hash(state.root)
        manifest = {
            "version": "0.2.0",
            "approved_hash": head,
            "approved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        state.write_manifest(manifest)


def _rebuild_outputs(state: GateState) -> list[Path]:
    """Render all configs under sp/ (current) and write to output/."""
    sections = load_sections(state.root)
    configs = load_all_configs(state.root)
    state.output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
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


# ---------- read approved state from git HEAD ----------

def _load_sections_at_head(state: GateState):
    """Load sections from git HEAD (the approved baseline) into the same shape
    `load_sections` returns. Implementation: write HEAD's sp/section/ files into
    a temp dir, load from there, throw away."""
    return _load_at_head(state, "sp/section", load_sections)


def _load_configs_at_head(state: GateState):
    return _load_at_head(state, "sp/config", load_all_configs)


def _load_at_head(state: GateState, prefix: str, loader_fn):
    """Generic: materialize HEAD's files under <prefix>/ into a temp tree, run
    loader_fn over that tree's parent dir."""
    import tempfile

    head = _git.head_hash(state.root)
    if head is None:
        # No HEAD yet — empty approved baseline
        return loader_fn(_empty_workspace())

    files = _git.list_files_at_ref(state.root, head, prefix + "/")
    with tempfile.TemporaryDirectory(prefix="forge-head-") as tmpdir:
        tmp = Path(tmpdir)
        for relpath in files:
            content = _git.show_at_ref(state.root, head, relpath)
            target = tmp / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        # loader expects to see <root>/sp/section/* — so pass tmp as the workspace root
        return loader_fn(tmp)


_EMPTY_WORKSPACE_CACHE: Path | None = None


def _empty_workspace() -> Path:
    """Path to a stable empty workspace (used when no HEAD yet)."""
    global _EMPTY_WORKSPACE_CACHE
    if _EMPTY_WORKSPACE_CACHE and _EMPTY_WORKSPACE_CACHE.exists():
        return _EMPTY_WORKSPACE_CACHE
    import tempfile

    p = Path(tempfile.mkdtemp(prefix="forge-empty-"))
    (p / "sp" / "section").mkdir(parents=True)
    (p / "sp" / "config").mkdir(parents=True)
    _EMPTY_WORKSPACE_CACHE = p
    return p
