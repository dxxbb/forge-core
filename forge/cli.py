"""forge CLI — single entrypoint for compiler / gate / bench."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from forge import __version__
from forge.gate import actions as gate
from forge.gate.doctor import run as doctor_run
from forge.bench import harness as bench_harness
from forge.governance.inbox import Inbox
from forge.governance.watcher import scan_git
from forge.governance.rollback import rollback as rollback_fn


def _root(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


@click.group()
@click.version_option(__version__, prog_name="forge")
def main() -> None:
    """forge-core: review-gated context compiler."""


# ---------- new / build / init / status ----------

@main.command("new")
@click.argument("path", type=click.Path())
def new_cmd(path: str) -> None:
    """Scaffold a new forge-core workspace at PATH with template section + config."""
    root = Path(path)
    if root.exists():
        click.echo(f"error: {root} already exists", err=True)
        sys.exit(1)
    (root / "sp" / "section").mkdir(parents=True)
    (root / "sp" / "config").mkdir(parents=True)

    (root / "sp" / "section" / "about-me.md").write_text(
        "---\nname: about-me\ntype: identity\n---\n\n"
        "Replace this body with a short, honest description of yourself —\n"
        "what you work on, how you prefer to collaborate, what you keep\n"
        "having to re-explain to agents.\n\n"
        "Agents will read this section every session.\n",
        encoding="utf-8",
    )
    (root / "sp" / "config" / "personal.md").write_text(
        "---\nname: personal\ntarget: claude-code\nsections:\n  - about-me\n---\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(".forge/\n", encoding="utf-8")

    click.echo(f"created {root}/")
    click.echo()
    click.echo("Next:")
    click.echo(f"  cd {path}")
    click.echo(f"  $EDITOR sp/section/about-me.md   # describe yourself")
    click.echo(f"  forge init                       # snapshot baseline + compile")
    click.echo(f"  cat .forge/output/CLAUDE.md      # see the compiled view")
    click.echo()
    click.echo("Then edit the section, run `forge diff` to preview, `forge approve` to ship.")

@main.command()
@click.option("--root", type=click.Path(), default=None, help="Workspace root (default: cwd).")
def build(root: str | None) -> None:
    """Render sp/ to output/ (no gate, always uses current sp/)."""
    written = gate.build(_root(root))
    for p in written:
        click.echo(f"wrote {p}")


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--force", is_flag=True, help="Re-init even if already initialized.")
def init(root: str | None, force: bool) -> None:
    """Bootstrap .forge/ by snapshotting current sp/ as baseline."""
    try:
        state = gate.init(_root(root), force=force)
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(f"initialized .forge at {state.forge_dir}")


@main.command()
@click.option("--root", type=click.Path(), default=None)
def status(root: str | None) -> None:
    """Show initialized state, approved hash, and whether sp/ has drifted."""
    info = gate.status(_root(root))
    click.echo(json.dumps(info, indent=2, ensure_ascii=False))


@main.command()
@click.option("--root", type=click.Path(), default=None)
def doctor(root: str | None) -> None:
    """Health check: validate configs, section references, provenance, adapters."""
    report = doctor_run(_root(root))
    for line in report.format_lines():
        click.echo(line)
    if not report.ok:
        sys.exit(1)


# ---------- review gate ----------

@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--source-only", is_flag=True, help="Only show source diff, not output diff.")
@click.option("--output-only", is_flag=True, help="Only show output diff.")
def diff(root: str | None, source_only: bool, output_only: bool) -> None:
    """Show what would change on approve (source diff + compiled preview)."""
    try:
        result = gate.diff_summary(_root(root))
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    if not result.changed:
        click.echo("no changes since last approve")
        return
    if not output_only:
        click.echo("=" * 8 + " source diff (sp/) " + "=" * 8)
        for line in result.source_diff_lines:
            click.echo(line)
        if not result.source_diff_lines:
            click.echo("(no source changes)")
    if not source_only:
        click.echo()
        click.echo("=" * 8 + " output diff " + "=" * 8)
        if not result.output_diffs:
            click.echo("(no output changes)")
        for cname, lines in result.output_diffs.items():
            click.echo(f"--- {cname} ---")
            for line in lines:
                click.echo(line)


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--note", "-m", default="", help="Short message for changelog.")
def approve(root: str | None, note: str) -> None:
    """Accept current sp/ as the new approved baseline. Rebuilds output/."""
    try:
        result = gate.approve(_root(root), note=note)
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(f"approved hash={result.approved_hash[:12]} at {result.approved_at}")
    for p in result.outputs_written:
        click.echo(f"  wrote {p}")


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.confirmation_option(prompt="Discard all current changes to sp/ and restore approved?")
def reject(root: str | None) -> None:
    """Discard changes to sp/; restore from last approved."""
    try:
        gate.reject(_root(root))
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo("restored sp/ from last approved")


# ---------- bench ----------

@main.group()
def bench() -> None:
    """Structural before/after bench for compiled outputs."""


@bench.command("snapshot")
@click.argument("name")
@click.option("--root", type=click.Path(), default=None)
def bench_snapshot(name: str, root: str | None) -> None:
    """Capture a named snapshot of current compiled outputs."""
    try:
        snap = bench_harness.snapshot(_root(root), name)
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(f"snapshot `{name}` created at {snap.created_at}")
    click.echo(f"  outputs: {sorted(snap.outputs)}")
    click.echo(f"  sections: {len(snap.sections)}")


@bench.command("list")
@click.option("--root", type=click.Path(), default=None)
def bench_list(root: str | None) -> None:
    """List all snapshots."""
    names = bench_harness.list_snapshots(_root(root))
    if not names:
        click.echo("(no snapshots)")
        return
    for n in names:
        click.echo(n)


@bench.command("compare")
@click.argument("before")
@click.argument("after")
@click.option("--root", type=click.Path(), default=None)
@click.option("--json", "as_json", is_flag=True, help="Output raw JSON.")
def bench_compare(before: str, after: str, root: str | None, as_json: bool) -> None:
    """Structural diff between two snapshots."""
    try:
        cmp = bench_harness.compare(_root(root), before, after)
    except FileNotFoundError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    if as_json:
        from dataclasses import asdict
        click.echo(json.dumps(asdict(cmp), indent=2, ensure_ascii=False))
        return
    click.echo(f"compare {before} -> {after}")
    click.echo()
    click.echo("# outputs")
    for fname, d in cmp.output_deltas.items():
        sign = "+" if d["bytes_delta"] >= 0 else ""
        click.echo(
            f"  {fname}: {d['bytes_before']}B -> {d['bytes_after']}B "
            f"({sign}{d['bytes_delta']}B, {sign}{d['lines_delta']}L)"
        )
    click.echo()
    if cmp.added_sections:
        click.echo(f"# added sections: {cmp.added_sections}")
    if cmp.removed_sections:
        click.echo(f"# removed sections: {cmp.removed_sections}")
    if cmp.section_deltas:
        click.echo("# section size deltas")
        for sname, d in cmp.section_deltas.items():
            sign = "+" if d["bytes_delta"] >= 0 else ""
            click.echo(
                f"  {sname}: {d['bytes_before']}B -> {d['bytes_after']}B ({sign}{d['bytes_delta']}B)"
            )


# ---------- governance (v0.1 stub) ----------

@main.command()
@click.option("--root", type=click.Path(), default=None)
def watch(root: str | None) -> None:
    """Scan new git commits, enqueue proposed changes to .forge/governance/inbox/."""
    changes = scan_git(_root(root))
    click.echo(f"scanned: {len(changes)} proposed change(s)")
    for c in changes[:20]:
        click.echo(f"  {c.commit_sha[:8]} {c.event_type.value:<18} {c.path}")
    if len(changes) > 20:
        click.echo(f"  ... and {len(changes) - 20} more")


@main.group()
def inbox() -> None:
    """Inbox of proposed changes pending triage."""


@inbox.command("list")
@click.option("--root", type=click.Path(), default=None)
def inbox_list(root: str | None) -> None:
    items = Inbox(_root(root)).list()
    if not items:
        click.echo("(inbox is empty)")
        return
    for t in items:
        click.echo(f"  {t.id:04d}  {t.event_type:<18} {t.path}")


@inbox.command("skip")
@click.argument("todo_id", type=int)
@click.option("--reason", "-m", required=True)
@click.option("--root", type=click.Path(), default=None)
def inbox_skip(todo_id: int, reason: str, root: str | None) -> None:
    Inbox(_root(root)).skip(todo_id, reason=reason)
    click.echo(f"skipped inbox/{todo_id:04d}")


@main.command()
@click.argument("hash_prefix", required=False)
@click.option("--root", type=click.Path(), default=None)
def rollback(hash_prefix: str | None, root: str | None) -> None:
    """Roll back sp/ to an earlier approved state (v0.1: latest approved only)."""
    try:
        result = rollback_fn(_root(root), hash_prefix)
    except (RuntimeError, ValueError) as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    if not hash_prefix:
        click.echo(f"current approved: {result['current_hash'][:12]}")
        click.echo("available in changelog:")
        for e in result["available"]:
            click.echo(f"  {e['hash'][:12]}  {e['line']}")
        return
    if result["applied_to"]:
        click.echo(f"rolled back to {result['applied_to'][:12]}")
    else:
        click.echo(result.get("diagnostic", "no-op"))


if __name__ == "__main__":
    main()
