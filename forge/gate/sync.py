"""External target sync: bind a compiled output to a path outside the workspace.

The use case: `~/.claude/CLAUDE.md` is what Claude Code reads at session start,
but `forge approve` writes to `<workspace>/output/CLAUDE.md`. Without bridging,
the user has to `cp` or `ln -sf` after every approve. `forge target install`
records the binding in manifest.json; `forge approve` then pushes automatically.

Bindings live in manifest.json under `targets`:
    {
      "targets": [
        {"adapter": "claude-code", "path": "/Users/x/.claude/CLAUDE.md", "mode": "copy"}
      ]
    }
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from forge.compiler.loader import load_all_configs
from forge.gate.state import GateState
from forge.targets import get_adapter


class TargetError(Exception):
    """Raised when a target operation fails (collision, missing output, etc.)."""


def install_target(
    root: Path,
    adapter: str,
    to: Path,
    mode: str = "copy",
    force: bool = False,
) -> dict:
    """Record a binding from `<output>/<adapter-filename>` to an external path.

    On success, also pushes the current output to the target so the user sees
    the effect immediately (no waiting for next approve).
    """
    if mode not in ("copy", "symlink"):
        raise TargetError(f"unknown mode `{mode}`. Use copy or symlink.")
    state = GateState(root)
    if not state.initialized():
        raise TargetError(
            f"forge not initialized at {root}. Run `forge init` first."
        )
    state.migrate_layout()

    output_path = _output_path_for_adapter(state, adapter)
    if not output_path.exists():
        raise TargetError(
            f"no compiled output for adapter `{adapter}`. "
            f"Configure a config with `target: {adapter}` and run `forge approve`."
        )

    # Expand ~ and make absolute, but DON'T resolve symlinks — if the target
    # is already a symlink to our output, resolve() would follow it back to
    # the output and we'd try to overwrite our own file.
    to = to.expanduser()
    if not to.is_absolute():
        to = to.absolute()

    if to.exists() or to.is_symlink():
        if not _is_already_pointing_here(to, output_path) and not force:
            raise TargetError(
                f"{to} already exists.\n"
                f"  use --force to overwrite (will not back up — back it up yourself first).\n"
                f"  or remove the existing file before installing."
            )

    to.parent.mkdir(parents=True, exist_ok=True)

    # remove existing target so symlink/copy works cleanly
    if to.is_symlink() or to.is_file():
        to.unlink()
    elif to.exists():
        raise TargetError(f"refusing to overwrite directory at {to}")

    if mode == "symlink":
        to.symlink_to(output_path.resolve())
    else:
        shutil.copy2(output_path, to)

    # record in manifest
    manifest = state.read_manifest()
    targets = list(manifest.get("targets", []))
    targets = [t for t in targets if t.get("adapter") != adapter]  # replace existing
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    binding = {
        "adapter": adapter,
        "path": str(to),
        "mode": mode,
        "installed_at": now,
    }
    targets.append(binding)
    manifest["targets"] = targets
    state.write_manifest(manifest)

    return binding


def remove_target(root: Path, adapter: str, delete_file: bool = False) -> dict | None:
    """Remove an adapter's binding from manifest. Optionally delete the target file."""
    state = GateState(root)
    if not state.initialized():
        raise TargetError(f"forge not initialized at {root}")
    manifest = state.read_manifest()
    targets = list(manifest.get("targets", []))
    removed: dict | None = None
    kept = []
    for t in targets:
        if t.get("adapter") == adapter and removed is None:
            removed = t
        else:
            kept.append(t)
    manifest["targets"] = kept
    state.write_manifest(manifest)

    if removed and delete_file:
        path = Path(removed["path"])
        if path.is_symlink() or path.is_file():
            path.unlink()

    return removed


def list_targets(root: Path) -> list[dict]:
    state = GateState(root)
    if not state.initialized():
        return []
    manifest = state.read_manifest()
    return list(manifest.get("targets", []))


def sync_targets(state: GateState) -> list[tuple[str, Path]]:
    """Push current output/ to all configured external targets.

    Called from `gate.approve`. Symlink-mode targets need no work (they
    already point at output/); copy-mode targets get refreshed.

    Returns [(adapter, path), ...] of synced targets.
    """
    manifest = state.read_manifest()
    targets = manifest.get("targets") or []
    synced: list[tuple[str, Path]] = []
    for binding in targets:
        adapter = binding["adapter"]
        path = Path(binding["path"])
        mode = binding.get("mode", "copy")
        try:
            output_path = _output_path_for_adapter(state, adapter)
        except TargetError:
            # config no longer references this adapter — skip silently
            continue
        if not output_path.exists():
            continue
        if mode == "symlink":
            # symlink already points at output/; nothing to do unless broken
            if not path.is_symlink():
                # was a copy-style file before, or got replaced — re-link
                if path.exists():
                    path.unlink()
                path.parent.mkdir(parents=True, exist_ok=True)
                path.symlink_to(output_path.resolve())
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.is_symlink():
                path.unlink()
            shutil.copy2(output_path, path)
        synced.append((adapter, path))
    return synced


# ---------- internal ----------

def _output_path_for_adapter(state: GateState, adapter_name: str) -> Path:
    """Find the compiled output file for the given adapter name."""
    configs = load_all_configs(state.root)
    for cname, cfg in configs.items():
        if cfg.target == adapter_name:
            adapter = get_adapter(adapter_name)
            return state.output_dir / adapter.filename(cfg)
    raise TargetError(
        f"no config in sp/config/ has `target: {adapter_name}`. "
        f"Add a config first or pick a different adapter."
    )


def _is_already_pointing_here(target: Path, output: Path) -> bool:
    """Is `target` already a symlink or copy of `output`? Used to skip overwrite prompt."""
    if target.is_symlink():
        try:
            return target.resolve() == output.resolve()
        except OSError:
            return False
    return False
