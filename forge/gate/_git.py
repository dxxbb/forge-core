"""Subprocess wrapper around git: small, focused, fail-loud.

forge-core v0.2 uses git as the substrate for the review gate (one approve =
one commit). This module is the only place that shells out to git. Keep it
small — if a helper grows complex, push the logic up into actions.py.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Sequence


class GitError(RuntimeError):
    """Wraps a non-zero git exit. `output` includes stderr for context."""

    def __init__(self, cmd: Sequence[str], returncode: int, output: str) -> None:
        super().__init__(f"git {' '.join(cmd)} (exit {returncode}): {output.strip()}")
        self.cmd = cmd
        self.returncode = returncode
        self.output = output


def git(root: Path, args: Sequence[str], *, check: bool = True, allow_empty_output: bool = False) -> str:
    """Run `git <args>` in `root`. Return combined stdout. Raise GitError on non-zero."""
    if shutil.which("git") is None:
        raise RuntimeError("git not found on PATH — forge v0.2 requires git installed")
    proc = subprocess.run(
        ["git", *args],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(args, proc.returncode, proc.stderr or proc.stdout)
    out = proc.stdout
    if not out and proc.stderr and not allow_empty_output:
        # some git commands print informational lines to stderr (e.g. checkout)
        # — we don't return them but they're not failures
        pass
    return out


def is_git_repo(root: Path) -> bool:
    """Is `root` inside a git working tree?"""
    if shutil.which("git") is None:
        return False
    proc = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def git_root(root: Path) -> Path:
    """Return the top-level of the working tree containing `root` (raises if none)."""
    out = git(root, ["rev-parse", "--show-toplevel"]).strip()
    return Path(out)


def head_hash(root: Path, *, short: bool = False) -> str | None:
    """Return HEAD's commit hash, or None if no HEAD yet (empty repo)."""
    if not is_git_repo(root):
        return None
    args = ["git", "rev-parse"]
    if short:
        args.append("--short=12")
    args.append("HEAD")
    proc = subprocess.run(args, cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def init_repo(root: Path, initial_branch: str = "main") -> None:
    """`git init -b main` then ensure user.name/user.email are set."""
    git(root, ["init", "-b", initial_branch])
    # Ensure commits don't fail if user hasn't configured global identity.
    # We set repo-local identity only if not already set globally or locally.
    if not _has_config(root, "user.name"):
        git(root, ["config", "user.name", "forge"])
    if not _has_config(root, "user.email"):
        git(root, ["config", "user.email", "forge@local"])


def _has_config(root: Path, key: str) -> bool:
    proc = subprocess.run(
        ["git", "config", "--get", key],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def add(root: Path, paths: Sequence[str]) -> None:
    """`git add` the given paths (relative to root)."""
    git(root, ["add", "--", *paths])


def commit(
    root: Path,
    message: str,
    *,
    allow_empty: bool = False,
    trailers: dict[str, str] | None = None,
) -> str:
    """Commit staged changes; return the new commit hash."""
    args = ["commit", "-m", message]
    if allow_empty:
        args.insert(1, "--allow-empty")
    if trailers:
        for k, v in trailers.items():
            args.extend(["--trailer", f"{k}: {v}"])
    git(root, args)
    h = head_hash(root)
    assert h is not None, "commit succeeded but HEAD has no hash?"
    return h


def restore_to_head(root: Path, paths: Sequence[str]) -> None:
    """Discard working-tree changes to the given paths, restoring from HEAD."""
    git(root, ["restore", "--source=HEAD", "--staged", "--worktree", "--", *paths])


def diff_paths(root: Path, paths: Sequence[str], *, ref: str = "HEAD") -> str:
    """`git diff <ref> -- <paths>` text. Empty string if no diff."""
    return git(root, ["diff", ref, "--", *paths], allow_empty_output=True)


def untracked_files(root: Path, paths: Sequence[str]) -> list[str]:
    """Return untracked, non-ignored files under the given paths."""
    out = git(
        root,
        ["ls-files", "--others", "--exclude-standard", "--", *paths],
        allow_empty_output=True,
    )
    return [ln for ln in out.splitlines() if ln.strip()]


def show_at_ref(root: Path, ref: str, path: str) -> str:
    """Return the content of `path` at `ref`. Empty string if path didn't exist."""
    proc = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""  # path didn't exist at ref (new file)
    return proc.stdout


def list_files_at_ref(root: Path, ref: str, prefix: str) -> list[str]:
    """List paths starting with `prefix` at `ref` (e.g. 'sp/section/')."""
    proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", ref, "--", prefix],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return []
    return [ln for ln in proc.stdout.splitlines() if ln.strip()]


def has_pending_changes(root: Path, paths: Sequence[str]) -> bool:
    """Is there any uncommitted or untracked change in the given paths vs HEAD?"""
    proc = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *paths],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    # exit 0 = no diff, 1 = has diff, other = error
    if proc.returncode == 1:
        return True
    return bool(untracked_files(root, paths))


def log_for_paths(
    root: Path,
    paths: Sequence[str],
    *,
    fmt: str = "%H%n%h%n%aI%n%s%n%(trailers:key=forge-provenance,valueonly)%n--END--",
    max_count: int | None = None,
) -> list[dict]:
    """Read commit log for the given paths. Return list of {hash, short, at, subject, provenance}."""
    args = ["log", f"--format={fmt}", "--", *paths]
    if max_count is not None:
        args.insert(1, f"-n{max_count}")
    out = git(root, args, allow_empty_output=True)
    entries: list[dict] = []
    chunks = out.split("--END--\n")
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        lines = chunk.splitlines()
        if len(lines) < 4:
            continue
        entries.append({
            "hash": lines[0],
            "short": lines[1],
            "at": lines[2],
            "subject": lines[3],
            "provenance": "\n".join(lines[4:]).strip(),
        })
    return entries


def checkout_paths_at_ref(root: Path, ref: str, paths: Sequence[str]) -> None:
    """Restore paths from a historical ref into the working tree (and stage them)."""
    git(root, ["checkout", ref, "--", *paths])


def is_clean_working_tree(root: Path, paths: Sequence[str] | None = None) -> bool:
    """Is the working tree clean (or, if paths given, clean for those paths)?"""
    args = ["status", "--porcelain"]
    if paths:
        args.extend(["--", *paths])
    out = git(root, args, allow_empty_output=True)
    return not out.strip()
