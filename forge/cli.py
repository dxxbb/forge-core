"""forge CLI — single entrypoint for compiler / gate / bench."""

from __future__ import annotations

import json
import shutil
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
from forge.ingest.classifier import classify, write_sections, IngestError


def _root(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


@click.group()
@click.version_option(__version__, prog_name="forge")
def main() -> None:
    """forge-core: review-gated context compiler."""


# ---------- new / build / init / status ----------

@main.command("new")
@click.argument("path", type=click.Path())
@click.option(
    "--minimal",
    is_flag=True,
    help="Scaffold only one section (about-me) instead of the full 5-section SP schema.",
)
def new_cmd(path: str, minimal: bool) -> None:
    """Scaffold a new forge-core workspace at PATH.

    Default: full 5-section SP schema (about-me, preferences, workspace,
    knowledge-base, skills) + 1 wrapper + 2 configs (claude-code + agents-md).
    Each section has structured TODO placeholders showing what to fill.

    --minimal: just one about-me section + one config. Use when you want to
    start fresh without templates.
    """
    root = Path(path)
    if root.exists():
        click.echo(f"error: {root} already exists", err=True)
        sys.exit(1)
    (root / "sp" / "section").mkdir(parents=True)
    (root / "sp" / "config").mkdir(parents=True)

    if minimal:
        _scaffold_minimal(root)
    else:
        _scaffold_full(root)

    (root / ".gitignore").write_text(".forge/\n", encoding="utf-8")

    click.echo(f"created {root}/")
    click.echo()
    click.echo("Next:")
    click.echo(f"  cd {path}")
    if minimal:
        click.echo(f"  $EDITOR sp/section/about-me.md   # describe yourself")
    else:
        click.echo(f"  ls sp/section/                   # 5 sections + 1 wrapper, all with TODO placeholders")
        click.echo(f"  $EDITOR sp/section/about-me.md   # start with about-me, fill in your identity")
    click.echo(f"  forge init                       # snapshot baseline + compile")
    click.echo(f"  cat output/CLAUDE.md             # see the compiled view (also AGENTS.md if not --minimal)")
    click.echo()
    if not minimal:
        click.echo(
            "Tip: if you already have a CLAUDE.md / .cursorrules, you can pre-fill"
        )
        click.echo("sections by importing it (or ask Claude Code with the forge skill installed):")
        click.echo("  forge ingest --from ~/.claude/CLAUDE.md     # auto-classify into 5 sections")
        click.echo()
    click.echo("Then edit, run `forge diff` to preview, `forge approve` to ship.")
    click.echo(
        "To wire compiled output to live Claude Code: "
        "`forge target install claude-code --to ~/.claude/CLAUDE.md`"
    )


def _scaffold_minimal(root: Path) -> None:
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


def _scaffold_full(root: Path) -> None:
    """Default scaffold: 5 SP sections + 1 wrapper + 2 cross-runtime configs."""
    sec = root / "sp" / "section"
    cfg = root / "sp" / "config"

    (sec / "_preface.md").write_text(_TEMPLATE_PREFACE, encoding="utf-8")
    (sec / "about-me.md").write_text(_TEMPLATE_ABOUT_ME, encoding="utf-8")
    (sec / "preferences.md").write_text(_TEMPLATE_PREFERENCES, encoding="utf-8")
    (sec / "workspace.md").write_text(_TEMPLATE_WORKSPACE, encoding="utf-8")
    (sec / "knowledge-base.md").write_text(_TEMPLATE_KNOWLEDGE_BASE, encoding="utf-8")
    (sec / "skills.md").write_text(_TEMPLATE_SKILLS, encoding="utf-8")

    (cfg / "claude-code.md").write_text(_TEMPLATE_CONFIG_CLAUDE, encoding="utf-8")
    (cfg / "agents-md.md").write_text(_TEMPLATE_CONFIG_AGENTS, encoding="utf-8")


_TEMPLATE_PREFACE = """\
---
name: _preface
type: wrapper
---

This file is the agent's long-term context, compiled by forge-core from
sp/section/. The user owns the source. To change it: edit sp/section/<name>.md,
run `forge diff` to preview, `forge approve` to ship. Do not edit this output
file directly.
"""

_TEMPLATE_ABOUT_ME = """\
---
name: about-me
type: identity
---

[TODO: 删掉方括号内的示例文字, 写成关于你自己的真实描述。]

# 你是谁

写一段 agent 一句话能识别你身份的描述。例子:

- 我是后端工程师, 14 年经验, 之前在字节跳动做 tech leader, 2026 年起独立。
- 我是研究生, 研究方向是分布式系统, 在某某大学。
- 我是产品经理, 专注 B 端 SaaS 产品。

# 工作方式

- 直接、简洁, 不要长 preamble
- 系统思维, 第一性原理
- 中文为主, 代码和技术术语保留英文

# 当前阶段

[TODO: 你正在专注什么, 这段时间的核心问题是什么]
"""

_TEMPLATE_PREFERENCES = """\
---
name: preferences
type: preference
---

[TODO: 写下 agent 应该遵守的规则。这是你跟它磨合出来的"协议"。]

# 工作方式

- 多步任务开工前先说要做什么
- 关键决策或方向转折时同步一次
- 不要伪造引用或数据

# 边界

- 不可逆 / 外部发送 / 生产变更: 先写可审阅方案, 得到明确批准再动手
- 不在没有上下文的情况下猜用户意图
- 不要主动改 git 配置 / 改 main 分支

# 输出风格

- 不要加 emoji 除非明确要求
- 不要长 preamble, 直接进重点
- 长 markdown 输出避免过度结构化 (h1/h2 套娃)
"""

_TEMPLATE_WORKSPACE = """\
---
name: workspace
type: workspace
---

[TODO: 列你当前在做的事 —— project / topic / reading 三类各列几条。]

# Project

- [TODO: project 名] — 一句话说明在做什么 / 当前 phase

# Topic (你长期跟踪的研究方向)

- [TODO: topic 名] — 为什么追

# Reading

- 《[TODO: 书名]》 — 当前进度
"""

_TEMPLATE_KNOWLEDGE_BASE = """\
---
name: knowledge-base
type: knowledge-base
---

[TODO: 列你长期追踪的外部 topic, 一行一个 pointer。这一段是 agent
查 KB 时的索引, 内容压缩成"哪个 topic 在哪、当前关注什么"即可。]

# tech/ai

- claude-code — Claude Code 能力边界 / prompt 实践 / 模型升级行为变化
- codex — Codex 平台演进 / 战略叙事

# tech/[domain]

- [TODO: 你跟踪的 topic]
"""

_TEMPLATE_SKILLS = """\
---
name: skills
type: skill
---

[TODO: 列你常用的 craft / workflow。每个是 one-liner pointer; 详细
procedure 放到独立 skill 文件再引用。]

# craft/

- code-review — 当我说 "review the diff" 时走的流程: ...
- writing — 当我说 "起草一篇" 时默认结构: ...
- [TODO: 你自己的]
"""

_TEMPLATE_CONFIG_CLAUDE = """\
---
name: claude-code
target: claude-code
sections:
  - _preface
  - about-me
  - preferences
  - workspace
  - knowledge-base
  - skills
required_sections:
  - about-me
  - preferences
demote_section_headings: true
---
"""

_TEMPLATE_CONFIG_AGENTS = """\
---
name: agents-md
target: agents-md
sections:
  - _preface
  - about-me
  - preferences
  - workspace
  - knowledge-base
  - skills
required_sections:
  - about-me
  - preferences
demote_section_headings: true
---
"""

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
    for adapter, path in result.targets_synced:
        click.echo(f"  synced → {path} (adapter: {adapter})")


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


# ---------- ingest ----------

@main.command("ingest")
@click.option(
    "--from",
    "source",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to the file to ingest (typically ~/.claude/CLAUDE.md or similar).",
)
@click.option(
    "--from-stdin",
    is_flag=True,
    help="Read input from stdin instead of a file.",
)
@click.option(
    "--no-llm",
    is_flag=True,
    help="Skip Anthropic API call. Dumps everything into sp/section/workspace.md "
    "as one block; you split manually after. Use this if you don't have an API "
    "key or want full control.",
)
@click.option(
    "--root",
    type=click.Path(),
    default=None,
    help="Workspace root (default: cwd). Must already have sp/section/ (run `forge new` first).",
)
@click.option(
    "--overwrite",
    is_flag=True,
    help="Overwrite non-template sections that already have user content.",
)
@click.option(
    "--model",
    default="claude-opus-4-7",
    show_default=True,
    help="Model for LLM classification path.",
)
def ingest(
    source: str | None,
    from_stdin: bool,
    no_llm: bool,
    root: str | None,
    overwrite: bool,
    model: str,
) -> None:
    """Import an existing CLAUDE.md / .cursorrules into 5 SP sections.

    Workflow:
        1. Read input (file or stdin).
        2. Classify into 5 sections (about-me / preferences / workspace /
           knowledge-base / skills) — via Claude API by default, or dump into
           one bucket with --no-llm.
        3. Write each non-empty section to sp/section/<name>.md (working tree).
        4. You then run `forge diff` to review the proposal, edit any section
           that's wrong, and `forge approve` to ship.

    The classification doesn't need to be perfect — that's what the gate is for.
    """
    if source and from_stdin:
        click.echo("error: pass either --from or --from-stdin, not both", err=True)
        sys.exit(1)
    if not source and not from_stdin:
        click.echo("error: must pass --from <file> or --from-stdin", err=True)
        sys.exit(1)

    workspace = _root(root)
    if not (workspace / "sp" / "section").exists():
        click.echo(
            f"error: {workspace} is not a forge workspace. "
            f"Run `forge new {workspace}` first.",
            err=True,
        )
        sys.exit(1)

    # Read input
    if source:
        text = Path(source).read_text(encoding="utf-8")
        source_path: Path | None = Path(source).resolve()
        click.echo(f"reading {source_path} ({len(text)} chars)")
    else:
        text = sys.stdin.read()
        source_path = None
        click.echo(f"read {len(text)} chars from stdin")

    if not text.strip():
        click.echo("error: input is empty", err=True)
        sys.exit(1)

    # Classify
    try:
        if no_llm:
            click.echo("classifying with --no-llm: dumping into one section, no API call")
        else:
            click.echo(f"classifying via {model}, this may take 10-30s...")
        result = classify(text, use_llm=not no_llm, model=model)
        result.source_path = source_path
    except IngestError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)

    # Write
    try:
        written = write_sections(result, workspace, overwrite=overwrite)
    except IngestError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)

    if not written:
        click.echo("(nothing classified — input was empty or all sections were empty)")
        return

    click.echo(f"\nwrote {len(written)} section(s) into {workspace}/sp/section/:")
    for p in written:
        body_size = len(p.read_text("utf-8"))
        click.echo(f"  {p.name}  ({body_size}B)")

    click.echo()
    click.echo("Next:")
    click.echo("  forge diff           # review what was classified, edit any section that's wrong")
    click.echo("  forge approve -m \"import existing context\"")


# ---------- skill install ----------

# ---------- target sync (output → external paths) ----------

@main.group()
def target() -> None:
    """Bind a compiled output to an external path (e.g. ~/.claude/CLAUDE.md).

    Once bound, every `forge approve` automatically refreshes the external
    file. No manual `cp` or `ln -sf` after each approve.
    """


@target.command("install")
@click.argument("adapter")
@click.option("--to", "to", type=click.Path(), required=True, help="Path to install at (e.g. ~/.claude/CLAUDE.md).")
@click.option(
    "--mode",
    type=click.Choice(["copy", "symlink"]),
    default="copy",
    help="copy = write a fresh copy on each approve. symlink = always live (recommended for personal use).",
)
@click.option("--force", is_flag=True, help="Overwrite if target file already exists.")
@click.option("--root", type=click.Path(), default=None)
def target_install(adapter: str, to: str, mode: str, force: bool, root: str | None) -> None:
    """Install an adapter's output to an external path (one-time).

    \b
    forge target install claude-code --to ~/.claude/CLAUDE.md
    forge target install claude-code --to ~/.claude/CLAUDE.md --mode symlink
    """
    from forge.gate.sync import install_target, TargetError

    try:
        binding = install_target(
            _root(root), adapter, Path(to).expanduser(), mode=mode, force=force
        )
    except TargetError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(f"installed: {binding['adapter']} → {binding['path']} ({binding['mode']})")
    click.echo("future `forge approve` will refresh this target automatically.")


@target.command("list")
@click.option("--root", type=click.Path(), default=None)
def target_list(root: str | None) -> None:
    """Show all configured target bindings."""
    from forge.gate.sync import list_targets

    bindings = list_targets(_root(root))
    if not bindings:
        click.echo("no targets configured.")
        click.echo("  install one: forge target install <adapter> --to <path>")
        return
    for b in bindings:
        click.echo(f"  {b['adapter']:15} → {b['path']:60} [{b['mode']}]")


@target.command("remove")
@click.argument("adapter")
@click.option("--delete-file", is_flag=True, help="Also delete the target file (default: leave it in place).")
@click.option("--root", type=click.Path(), default=None)
def target_remove(adapter: str, delete_file: bool, root: str | None) -> None:
    """Remove a target binding from manifest."""
    from forge.gate.sync import remove_target, TargetError

    try:
        removed = remove_target(_root(root), adapter, delete_file=delete_file)
    except TargetError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    if removed is None:
        click.echo(f"no binding for adapter `{adapter}`")
        sys.exit(1)
    suffix = " (file deleted)" if delete_file else " (file left in place)"
    click.echo(f"removed: {adapter} → {removed['path']}{suffix}")


@main.command("install-skill")
@click.option(
    "--symlink",
    is_flag=True,
    help="Symlink instead of copy. Always reflects forge-core's source — good for dev / staying current. Requires forge-core source to stay in place.",
)
@click.option("--force", is_flag=True, help="Overwrite existing installation without prompting.")
@click.option(
    "--target",
    type=click.Path(),
    default=None,
    help="Override target dir (default: ~/.claude/skills/forge).",
)
def install_skill(symlink: bool, force: bool, target: str | None) -> None:
    """Install or update the Claude Code skill (forge) into ~/.claude/skills/forge.

    Re-run with --force to update after upgrading forge-core.
    """
    src = Path(__file__).parent.parent / "examples" / "skills" / "forge"
    if not src.exists():
        click.echo(f"error: skill source not found at {src}", err=True)
        click.echo(
            "  forge-core may have been installed without the examples/ dir. "
            "Try installing from source: pip install -e <forge-core-repo>.",
            err=True,
        )
        sys.exit(1)

    dest = Path(target).expanduser() if target else Path.home() / ".claude" / "skills" / "forge"
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() or dest.is_symlink():
        if not force:
            click.echo(
                f"{dest} already exists.\n"
                f"  use --force to overwrite (re-install / update).",
                err=True,
            )
            sys.exit(1)
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)

    if symlink:
        dest.symlink_to(src.resolve())
        click.echo(f"linked {dest} -> {src.resolve()}")
        click.echo("future updates to forge-core's skill source picked up automatically.")
    else:
        shutil.copytree(src, dest)
        click.echo(f"copied skill to {dest}")
        click.echo("to update later: `forge install-skill --force`")

    click.echo()
    click.echo("Triggers in Claude Code (any of):")
    click.echo("  'approve my changes' / 'review my context' / '过一下' / '审一下'")
    click.echo("  'forge approve' / 'forge diff' / 'forge reject'")


if __name__ == "__main__":
    main()
