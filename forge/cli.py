"""forge CLI — single entrypoint for compiler / gate / bench."""

from __future__ import annotations

import json
import re
import shutil
import sys
import hashlib
from datetime import datetime
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
from forge.layout import detect


def _root(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


@click.group()
@click.version_option(__version__, prog_name="forge")
def main() -> None:
    """forge: review-gated context compiler."""


# ---------- new / build / init / status ----------

@main.command("new")
@click.argument("path", type=click.Path())
@click.option(
    "--minimal",
    is_flag=True,
    help="Scaffold only one section (about-me) instead of the full 5-section SP schema.",
)
def new_cmd(path: str, minimal: bool) -> None:
    """Scaffold a new forge workspace at PATH.

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

    # v0.2: workspace IS a git repo. git init + initial commit so the user has
    # a clean baseline they can diff/approve/rollback against.
    from forge.gate import _git
    from forge.gate import actions as gate

    _git.init_repo(root)
    # Build initial output before the first commit so the workspace is fully
    # populated (5 templates → output/CLAUDE.md + output/AGENTS.md).
    gate.build(root)
    _git.add(root, ["sp", "output", ".gitignore"])
    initial_hash = _git.commit(
        root,
        "forge new: scaffold sp/ + first output/ build",
        trailers={"forge-provenance": "version=0.2.0 source=forge-new"},
    )

    section_count = 1 if minimal else 5
    click.echo(
        f"✓ {root}  (git: {initial_hash[:7]}, {section_count} empty section{'s' if section_count != 1 else ''})"
    )
    click.echo()
    click.echo(f"  Edit a section, then: forge review")
    click.echo(f"  See all commands:     forge --help")


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

This file is the agent's long-term context, compiled by forge from
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
    """Render context source to runtime output (no gate)."""
    written = gate.build(_root(root))
    for p in written:
        click.echo(f"wrote {p}")


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--force", is_flag=True, help="Re-init even if already initialized.")
def init(root: str | None, force: bool) -> None:
    """Initialize the review gate from the current context source."""
    try:
        state = gate.init(_root(root), force=force)
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo(f"initialized .forge at {state.forge_dir}")


@main.command()
@click.option("--root", type=click.Path(), default=None)
def status(root: str | None) -> None:
    """Show initialized state, approved hash, and whether context has drifted."""
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
@click.option("--config", "config_filter", default=None, help="Only show output diff for this config name.")
@click.option("--no-color", is_flag=True, help="Disable colored +/- lines.")
@click.option(
    "--full-provenance",
    is_flag=True,
    help="Show provenance digest/byte lines (folded by default — they're noise on every diff).",
)
@click.option(
    "--no-pager",
    is_flag=True,
    help="Print directly to stdout instead of paging through less.",
)
def diff(
    root: str | None,
    source_only: bool,
    output_only: bool,
    config_filter: str | None,
    no_color: bool,
    full_provenance: bool,
    no_pager: bool,
) -> None:
    """Show what would change on approve.

    Prints a one-line summary, then source diff (your context edits) and output
    diff (each compiled config). Provenance digest/byte lines are folded to
    one collapsed marker — pass --full-provenance to see them.
    """
    try:
        result = gate.diff_summary(_root(root))
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    if not result.changed:
        click.echo("no changes since last approve")
        return

    use_color = (not no_color) and click.get_text_stream("stdout").isatty()
    if no_pager:
        use_color = use_color and not no_color  # only color if tty AND not disabled
    else:
        use_color = not no_color  # paging through less -R supports color

    output = _format_diff(
        result=result,
        source_only=source_only,
        output_only=output_only,
        config_filter=config_filter,
        use_color=use_color,
        full_provenance=full_provenance,
    )

    if no_pager or not click.get_text_stream("stdout").isatty():
        click.echo(output)
    else:
        click.echo_via_pager(output, color=use_color)


def _format_diff(
    result,
    source_only: bool,
    output_only: bool,
    config_filter: str | None,
    use_color: bool,
    full_provenance: bool,
) -> str:
    """Render a DiffResult as a colored, summarized string."""
    out: list[str] = []

    # ---- summary header ----
    summary = _summarize_diff(result)
    out.append(click.style(summary, bold=True) if use_color else summary)
    out.append("")

    if not output_only:
        source_title = f"── source diff ({getattr(result, 'source_label', 'sp')}) ──"
        out.append(click.style(source_title, fg="cyan", bold=True) if use_color else source_title)
        if not result.source_diff_lines:
            out.append("(no source changes)")
        else:
            for line in result.source_diff_lines:
                out.append(_color_diff_line(line, use_color))
        out.append("")

    if not source_only:
        out.append(click.style("── output diff ──", fg="cyan", bold=True) if use_color else "── output diff ──")
        if not result.output_diffs:
            out.append("(no output changes)")
        else:
            shown = 0
            for cname, lines in result.output_diffs.items():
                if config_filter and cname != config_filter:
                    continue
                shown += 1
                header = f"  ▸ {cname}"
                out.append(click.style(header, fg="yellow", bold=True) if use_color else header)
                folded_lines = lines if full_provenance else _fold_provenance_block(lines)
                for line in folded_lines:
                    out.append(_color_diff_line(line, use_color))
                out.append("")
            if config_filter and shown == 0:
                out.append(f"  (no output changes for config `{config_filter}`)")

    return "\n".join(out)


def _summarize_diff(result) -> str:
    """One-line summary: how many sections/config sources changed."""
    section_files = set()
    config_files = set()
    for line in result.source_diff_lines:
        if line.startswith("--- approved/") or line.startswith("+++ current/"):
            path = line.split("/", 1)[1] if "/" in line else line
            if path.startswith("section/"):
                section_files.add(path[len("section/"):])
            elif path.startswith("config/"):
                config_files.add(path[len("config/"):])
            elif path.startswith("context build/sections/"):
                section_files.add(path[len("context build/sections/"):])
            elif path.startswith("context build/config/"):
                config_files.add(path[len("context build/config/"):])
    n_sections = len(section_files)
    n_config_files = len(config_files)
    n_configs = len(result.output_diffs)
    parts: list[str] = []
    if n_sections:
        parts.append(f"{n_sections} {'section' if n_sections == 1 else 'sections'} changed")
        parts.append(f"({', '.join(sorted(section_files))})")
    if n_config_files:
        parts.append(f"{n_config_files} config {'file' if n_config_files == 1 else 'files'} changed")
        parts.append(f"({', '.join(sorted(config_files))})")
    if n_configs:
        parts.append(f"→ {n_configs} {'config' if n_configs == 1 else 'configs'} affected: {', '.join(sorted(result.output_diffs))}")
    if not parts:
        return "no detectable changes"
    return "summary: " + " ".join(parts)


def _color_diff_line(line: str, use_color: bool) -> str:
    if not use_color:
        return line
    if line.startswith("+++") or line.startswith("---"):
        return click.style(line, fg="white", bold=True)
    if line.startswith("@@"):
        return click.style(line, fg="cyan")
    if line.startswith("+"):
        return click.style(line, fg="green")
    if line.startswith("-"):
        return click.style(line, fg="red")
    return line


def _fold_provenance_block(lines: list[str]) -> list[str]:
    """Collapse the per-output provenance digest/byte hunk to a single line.

    Provenance digest changes on every approve (because hashes embed timestamps
    or section bytes) — useful when debugging adapters, pure noise during review.
    Detection: a hunk where every -/+ line either contains 'digest=' or matches
    `>  - <name> · type=<type> · <NNN>B`.
    """
    out: list[str] = []
    i = 0
    n = len(lines)
    PROVENANCE_RE = re.compile(r"^[+-].*(digest=|· type=.*· \d+B$)")
    while i < n:
        line = lines[i]
        if line.startswith("@@"):
            # collect this hunk
            hunk_end = i + 1
            while hunk_end < n and not lines[hunk_end].startswith("@@") and not lines[hunk_end].startswith(("---", "+++")):
                hunk_end += 1
            hunk = lines[i + 1 : hunk_end]
            mod_lines = [ln for ln in hunk if ln.startswith(("+", "-"))]
            if mod_lines and all(PROVENANCE_RE.match(ln) for ln in mod_lines):
                out.append(line)
                out.append(f"  … {len(mod_lines)} provenance lines folded (--full-provenance to expand) …")
                i = hunk_end
                continue
            out.append(line)
            i += 1
        else:
            out.append(line)
            i += 1
    return out


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--note", "-m", default="", help="Short message for changelog.")
def approve(root: str | None, note: str) -> None:
    """Accept current context as the new approved baseline. Rebuilds runtime output."""
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
@click.confirmation_option(prompt="Discard all current context/runtime changes and restore approved?")
def reject(root: str | None) -> None:
    """Discard context/runtime changes and restore from last approved."""
    try:
        gate.reject(_root(root))
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)
    click.echo("restored context from last approved")


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


@inbox.command("done")
@click.argument("path", type=click.Path())
@click.option("--root", type=click.Path(), default=None, help="Workspace root (default: cwd).")
def inbox_done(path: str, root: str | None) -> None:
    """Mark an inbox item as processed by deleting it.

    PATH may be absolute, or relative to the workspace root. Works for both
    legacy `.forge/governance/inbox/` items and personalOS `system/inbox/`
    items — the file is removed; capture/ and system/pr/ keep the audit trail.
    """
    workspace = _root(root)
    target = Path(path).expanduser()
    if not target.is_absolute():
        target = (workspace / target).resolve()
    if not target.exists():
        click.echo(f"error: inbox file not found: {target}", err=True)
        sys.exit(1)
    if target.suffix != ".md":
        click.echo(f"error: not an inbox markdown file: {target}", err=True)
        sys.exit(1)
    target.unlink()
    rel = target.relative_to(workspace).as_posix() if target.is_relative_to(workspace) else str(target)
    click.echo(f"done: removed {rel}")


# (v0.2 forge rollback now lives later in this file, alongside forge migrate
#  and forge changelog — they're a coordinated triad.)


# ---------- personalOS capture/import ----------

@main.command("capture")
@click.option(
    "--from",
    "source",
    type=click.Path(exists=True, dir_okay=False),
    help="Path to a source file to copy into capture/import/.",
)
@click.option("--from-stdin", is_flag=True, help="Read raw import text from stdin.")
@click.option(
    "--from-claude-memory",
    is_flag=True,
    help="Capture Claude Code auto-memory (~/.claude/projects/*/memory/*.md).",
)
@click.option(
    "--claude-project",
    default=None,
    help="With --from-claude-memory, restrict to one project slug.",
)
@click.option("--root", type=click.Path(), default=None, help="personalOS root (default: cwd).")
@click.option("--title", default="import-context", help="Inbox slug/title.")
def capture_cmd(
    source: str | None,
    from_stdin: bool,
    from_claude_memory: bool,
    claude_project: str | None,
    root: str | None,
    title: str,
) -> None:
    """Capture raw evidence into personalOS capture/import/ and create an inbox item.

    This is intentionally pre-review only: it never writes context sections,
    assets, proposals, or runtime output. The next step is human/agent triage
    from system/inbox/ into system/pr/.
    """
    input_modes = [bool(source), from_stdin, from_claude_memory]
    if sum(input_modes) != 1:
        click.echo("error: pick exactly one input mode (--from / --from-stdin / --from-claude-memory)", err=True)
        sys.exit(1)

    workspace = _root(root)
    capture_root = workspace / "capture" / "import"
    inbox_root = workspace / "system" / "inbox"
    if not capture_root.parent.exists() or not inbox_root.parent.exists():
        click.echo(
            f"error: {workspace} does not look like a personalOS workspace "
            "(expected capture/ and system/).",
            err=True,
        )
        sys.exit(1)

    if source:
        source_path = Path(source).resolve()
        text = source_path.read_text(encoding="utf-8")
        stat = source_path.stat()
        source_label = str(source_path)
        raw_name = _safe_capture_name(source_path.stem or "source") + source_path.suffix
        summary = f"{source_path} ({len(text)} chars)"
        source_meta = {
            "source_size": stat.st_size,
            "source_mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            "source_digest": _digest_text(text),
        }
    elif from_claude_memory:
        text, _repr_path, file_count = _read_claude_memory(claude_project)
        if not text.strip():
            click.echo("error: no Claude Code memory files found", err=True)
            sys.exit(1)
        scope = f"project={claude_project}" if claude_project else "all projects"
        source_label = f"claude-code-memory:{scope}"
        raw_name = "claude-memory.md"
        summary = f"Claude Code memory ({scope}, {file_count} files, {len(text)} chars)"
        source_meta = {
            "source_files": file_count,
            "source_digest": _digest_text(text),
        }
    else:
        text = sys.stdin.read()
        source_label = "<stdin>"
        raw_name = "stdin.md"
        summary = f"stdin ({len(text)} chars)"
        source_meta = {
            "source_digest": _digest_text(text),
        }

    if not text.strip():
        click.echo("error: input is empty", err=True)
        sys.exit(1)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    batch_dir = capture_root / ts
    batch_dir.mkdir(parents=True, exist_ok=False)
    raw_path = batch_dir / raw_name
    captured_at = datetime.now().astimezone().isoformat(timespec="seconds")
    meta_lines = "".join(
        f"{k}: {json.dumps(v, ensure_ascii=False)}\n" for k, v in source_meta.items()
    )
    raw_path.write_text(
        "---\n"
        "kind: raw import\n"
        f"source: {json.dumps(source_label, ensure_ascii=False)}\n"
        f"captured_at: {captured_at}\n"
        f"{meta_lines}"
        "status: unreviewed\n"
        "---\n\n"
        f"{text.rstrip()}\n",
        encoding="utf-8",
    )

    inbox_root.mkdir(parents=True, exist_ok=True)
    slug = _safe_capture_name(title).strip("-") or "import-context"
    inbox_path = inbox_root / f"{ts}-{slug}.md"
    rel_batch = batch_dir.relative_to(workspace).as_posix()
    rel_raw = raw_path.relative_to(workspace).as_posix()
    inbox_path.write_text(
        "---\n"
        "kind: inbox\n"
        "type: import-context\n"
        "status: pending\n"
        "source:\n"
        f"  - {rel_batch}/\n"
        "---\n\n"
        "# Import context\n\n"
        "## Source summary\n\n"
        f"- {summary}\n\n"
        "## Requested action\n\n"
        "Extract candidate personalOS assets and context projections.\n\n"
        "## Review requirement\n\n"
        "Do not apply directly. Create a proposal under `system/pr/`.\n",
        encoding="utf-8",
    )

    click.echo(f"captured raw import: {rel_raw}")
    click.echo(f"created inbox item: {inbox_path.relative_to(workspace).as_posix()}")
    click.echo("next: process inbox -> proposal -> review")


def _safe_capture_name(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "source"


def _digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@main.command("monitor")
@click.option("--root", type=click.Path(), default=None, help="personalOS root (default: cwd).")
def monitor(root: str | None) -> None:
    """Report whether a personalOS workspace has anything actionable.

    Checks pending inbox/proposals, context-build drift, and known import source
    digests. Clean means no import/review prompt is needed.
    """
    workspace = _root(root)
    issues: list[str] = []
    actions: list[str] = []

    try:
        report = doctor_run(workspace)
    except Exception as e:  # pragma: no cover - defensive CLI boundary
        click.echo(f"status: error")
        click.echo(f"doctor: {e}")
        sys.exit(1)
    if not report.ok:
        click.echo("status: attention")
        for line in report.format_lines():
            click.echo(line)
        sys.exit(1)

    pending_inbox = _pending_inbox_items(workspace)
    pending_pr = _pending_proposals(workspace)
    context_drift = _context_drift(workspace)
    import_updates = _import_updates(workspace)

    if pending_pr:
        issues.append(f"pending proposals: {len(pending_pr)}")
        actions.append(f"review proposal: {pending_pr[-1].relative_to(workspace).as_posix()}")
    if pending_inbox:
        issues.append(f"pending inbox: {len(pending_inbox)}")
        actions.append("process inbox")
    if context_drift:
        issues.append("context source changed")
        actions.append("build/review runtime")
    if import_updates:
        issues.append(f"import source updates: {len(import_updates)}")
        for item in import_updates[:5]:
            actions.append(f"import update: {item}")

    if not issues:
        click.echo("status: clean")
        click.echo("no pending inbox, proposals, context drift, or known import updates.")
        return

    click.echo("status: attention")
    for issue in issues:
        click.echo(f"- {issue}")
    click.echo()
    click.echo("next:")
    for action in actions[:8]:
        click.echo(f"- {action}")


def _pending_inbox_items(workspace: Path) -> list[Path]:
    inbox_dir = workspace / "system" / "inbox"
    if not inbox_dir.exists():
        return []
    # An inbox file existing == still pending. Processed items are removed by
    # `forge inbox done`; capture/ keeps the audit trail of what was imported.
    return sorted(inbox_dir.glob("*.md"))


def _pending_proposals(workspace: Path) -> list[Path]:
    pr_dir = workspace / "system" / "pr"
    if not pr_dir.exists():
        return []
    out: list[Path] = []
    for p in sorted(pr_dir.glob("*/proposal.md")):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if not re.search(r"^status:\s*(applied|rejected)\s*$", text, re.MULTILINE):
            out.append(p)
    return out


def _context_drift(workspace: Path) -> bool:
    from forge.gate import _git

    if not _git.is_git_repo(workspace):
        return False
    layout = detect(workspace)
    return _git.has_pending_changes(workspace, list(layout.tracked_paths))


def _import_updates(workspace: Path) -> list[str]:
    records = _latest_capture_records(workspace)
    updates: list[str] = []

    for raw_path, label in _FILE_CANDIDATES:
        p = Path(raw_path).expanduser()
        if not p.exists() or not p.is_file():
            continue
        try:
            real = p.resolve(strict=True)
            text = real.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if len(text.encode("utf-8")) < _MIN_BYTES:
            continue
        key = str(real)
        digest = _digest_text(text)
        previous = records.get(key)
        if previous is None:
            updates.append(f"{key} (new, {label})")
        elif previous.get("source_digest") and previous.get("source_digest") != digest:
            updates.append(f"{key} (changed, {label})")

    memory_text, _repr_path, file_count = _read_claude_memory(None)
    if memory_text.strip():
        key = "claude-code-memory:all projects"
        digest = _digest_text(memory_text)
        previous = records.get(key)
        if previous is None:
            updates.append(f"Claude Code memory (new, {file_count} files)")
        elif previous.get("source_digest") and previous.get("source_digest") != digest:
            updates.append(f"Claude Code memory (changed, {file_count} files)")

    return updates


def _latest_capture_records(workspace: Path) -> dict[str, dict[str, str]]:
    capture_dir = workspace / "capture" / "import"
    records: dict[str, dict[str, str]] = {}
    if not capture_dir.exists():
        return records
    for p in sorted(capture_dir.glob("*/*.md")):
        meta = _read_frontmatter(p)
        source = meta.get("source")
        if not source:
            continue
        records[source] = meta
    return records


def _read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = value
        meta[key.strip()] = str(parsed)
    return meta


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
    "--from-claude-memory",
    is_flag=True,
    help="Read Claude Code's auto-memory (~/.claude/projects/*/memory/*.md). "
    "Already-distilled markdown across all projects.",
)
@click.option(
    "--claude-project",
    default=None,
    help="With --from-claude-memory, restrict to one project slug.",
)
@click.option(
    "--detect",
    is_flag=True,
    help="Scan standard locations and print importable candidates. Doesn't read content.",
)
@click.option(
    "--emit",
    is_flag=True,
    help="Print the source text to stdout (with provenance headers) and exit. "
    "Workspace not modified. Use when an agent (you) wants to read the text and "
    "classify into 5 sections in its own context, then Write each section file.",
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
def ingest(
    source: str | None,
    from_stdin: bool,
    from_claude_memory: bool,
    claude_project: str | None,
    detect: bool,
    emit: bool,
    root: str | None,
    overwrite: bool,
) -> None:
    """Read context source(s); either dump into workspace.md or emit for agent classification.

    forge does NOT call an LLM. Two paths:

    \b
    1. Default (CLI-direct, no agent):
       Reads input → dumps everything into sp/section/workspace.md as one
       block. You split manually with $EDITOR, then `forge review`.

    \b
    2. --emit (agent-driven, recommended in skill flow):
       Reads input → prints to stdout with `--- from: <name> ---` provenance
       headers → exits. Workspace untouched. Agent reads stdout, classifies
       into 5 sections in its own context, writes per-section files via Write
       tool, then runs `forge review`.

    Sources: --from <path> | --from-stdin | --from-claude-memory.
    Use --detect first to list candidates without reading.
    """
    if detect:
        _ingest_detect()
        return

    # Mutual exclusion check across input modes
    input_modes = [bool(source), from_stdin, from_claude_memory]
    if sum(input_modes) > 1:
        click.echo("error: pick exactly one input mode (--from / --from-stdin / --from-claude-memory)", err=True)
        sys.exit(1)
    if sum(input_modes) == 0:
        click.echo(
            "error: must pass --from <file> / --from-stdin / --from-claude-memory "
            "(or --detect to list candidates)",
            err=True,
        )
        sys.exit(1)

    # Read input
    if source:
        text = Path(source).read_text(encoding="utf-8")
        source_path: Path | None = Path(source).resolve()
        if not emit:
            click.echo(f"reading {source_path} ({len(text)} chars)", err=True)
    elif from_claude_memory:
        text, source_path, file_count = _read_claude_memory(claude_project)
        if not text.strip():
            click.echo("error: no Claude Code memory files found", err=True)
            sys.exit(1)
        scope = f"project={claude_project}" if claude_project else "all projects"
        if not emit:
            click.echo(f"reading {file_count} Claude memory file(s) ({scope}, {len(text)} chars total)", err=True)
    else:
        text = sys.stdin.read()
        source_path = None
        if not emit:
            click.echo(f"read {len(text)} chars from stdin", err=True)

    if not text.strip():
        click.echo("error: input is empty", err=True)
        sys.exit(1)

    # ---- emit path: print to stdout, no disk write ----
    if emit:
        click.echo(text, nl=False)

        # Record a "pending agent classification" event so review surfaces
        # the source even though no sections written yet
        workspace = _root(root)
        if (workspace / "sp" / "section").exists():
            from forge.gate.origin import record_event
            if from_claude_memory:
                scope = f" (project={claude_project})" if claude_project else " (all projects)"
                summary = f"forge ingest --emit --from-claude-memory{scope} (agent will classify)"
                details = {"source": "claude-code-memory", "claude_project": claude_project,
                           "method": "emit", "input_chars": len(text)}
            elif source_path:
                summary = f"forge ingest --emit --from {source_path} (agent will classify)"
                details = {"source": str(source_path), "method": "emit", "input_chars": len(text)}
            else:
                summary = "forge ingest --emit --from-stdin (agent will classify)"
                details = {"source": "<stdin>", "method": "emit", "input_chars": len(text)}
            record_event(workspace, kind="ingest", summary=summary, details=details)
        return

    # ---- default path: dump everything into workspace.md ----
    workspace = _root(root)
    if not (workspace / "sp" / "section").exists():
        click.echo(
            f"error: {workspace} is not a forge workspace. "
            f"Run `forge new {workspace}` first.",
            err=True,
        )
        sys.exit(1)

    try:
        result = classify(text)
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
        click.echo("(nothing to write — input was empty)")
        return

    click.echo(f"\nwrote {len(written)} section(s) into {workspace}/sp/section/:")
    for p in written:
        body_size = len(p.read_text("utf-8"))
        click.echo(f"  {p.name}  ({body_size}B)")

    # Record origin so `forge review` can show "this came from `forge ingest ...`"
    from forge.gate.origin import record_event

    sections_touched = [p.stem for p in written]
    if from_claude_memory:
        scope = f" (project={claude_project})" if claude_project else " (all projects)"
        summary = f"forge ingest --from-claude-memory{scope} (dump)"
        details = {"source": "claude-code-memory", "claude_project": claude_project,
                   "method": "dump", "input_chars": len(text)}
    elif source_path:
        summary = f"forge ingest --from {source_path} (dump)"
        details = {"source": str(source_path), "method": "dump", "input_chars": len(text)}
    else:
        summary = "forge ingest --from-stdin (dump)"
        details = {"source": "<stdin>", "method": "dump", "input_chars": len(text)}
    record_event(
        workspace,
        kind="ingest",
        summary=summary,
        details=details,
        sections_touched=sections_touched,
    )

    click.echo()
    click.echo("Next:")
    click.echo("  forge review         # see origin + diff + bench")
    click.echo("  $EDITOR sp/section/workspace.md   # split into 5 sections, then approve")


# ---------- ingest detection helper ----------

_FILE_CANDIDATES = [
    ("~/.claude/CLAUDE.md", "Claude Code (global instructions)"),
    ("./CLAUDE.md", "Claude Code (project-local)"),
    ("~/.codex/AGENTS.md", "Codex CLI (global)"),
    ("./AGENTS.md", "AGENTS.md (Codex / OpenCode / project-local)"),
    ("~/.cursorrules", "Cursor (legacy)"),
    ("./.cursorrules", "Cursor (project-local)"),
]

_MIN_BYTES = 200  # files smaller than this are likely placeholders


def _ingest_detect() -> None:
    """List importable context sources. Surfaces files + Claude Code memory + transcripts.

    Output is structured so the agent can paste it verbatim and the user can
    pick a numbered option, paste a path, or skip.
    """
    import os

    file_found: list[tuple[Path, str, int]] = []
    file_skipped: list[tuple[str, str]] = []

    for raw_path, label in _FILE_CANDIDATES:
        p = Path(os.path.expanduser(raw_path))
        if not p.exists():
            try:
                if p.is_symlink():
                    file_skipped.append((raw_path, "broken symlink"))
                else:
                    file_skipped.append((raw_path, "not present"))
            except OSError:
                file_skipped.append((raw_path, "not present"))
            continue
        try:
            real = p.resolve(strict=True)
            size = real.stat().st_size
        except (OSError, FileNotFoundError):
            file_skipped.append((raw_path, "broken symlink"))
            continue
        if size < _MIN_BYTES:
            file_skipped.append((raw_path, f"only {size}B (placeholder?)"))
            continue
        file_found.append((p, label, size))

    # Claude Code auto-memory: ~/.claude/projects/<slug>/memory/*.md
    claude_memory_projects = _scan_claude_memory()

    # Claude Code transcripts (jsonl) — count only, not yet supported as ingest source
    transcripts = _count_claude_transcripts()

    # ---------- output ----------

    n_sources = len(file_found) + (1 if claude_memory_projects else 0)

    if n_sources == 0:
        click.echo("no importable sources found.")
        click.echo()
        if file_skipped:
            click.echo("checked but skipped:")
            for raw_path, reason in file_skipped:
                click.echo(f"  {raw_path}  — {reason}")
            click.echo()
        if transcripts > 0:
            click.echo(f"(found {transcripts} Claude Code transcripts but transcript-distill is v0.4 — too noisy yet)")
            click.echo()
        click.echo("if you have a context file elsewhere, run: forge ingest --from <path>")
        click.echo("or skip import and edit sections directly: $EDITOR sp/section/<name>.md")
        return

    click.echo(f"found {n_sources} importable source{'s' if n_sources != 1 else ''}:")
    click.echo()

    idx = 0
    for p, label, size in file_found:
        idx += 1
        kb = f"{size / 1024:.1f}KB" if size >= 1024 else f"{size}B"
        click.echo(f"  {idx}. {p}  ({kb}, {label})")

    if claude_memory_projects:
        idx += 1
        total_files = sum(n for _, n, _ in claude_memory_projects)
        total_bytes = sum(b for _, _, b in claude_memory_projects)
        kb = f"{total_bytes / 1024:.1f}KB"
        click.echo(
            f"  {idx}. ~/.claude/projects/*/memory/  ({total_files} files, {kb}, "
            f"Claude auto-memory, {len(claude_memory_projects)} projects)"
        )
        for slug, n, _ in claude_memory_projects:
            click.echo(f"       • {slug}  ({n} files)")

    if transcripts > 0:
        click.echo()
        click.echo(
            f"  (also: {transcripts} Claude Code transcripts found but transcript-distill is v0.4 — skipped for now)"
        )

    click.echo()
    click.echo("to ingest:")
    click.echo("  forge ingest --from <path>            # one file (use a path from above)")
    if claude_memory_projects:
        click.echo("  forge ingest --from-claude-memory     # all auto-memory across projects")
        click.echo("  forge ingest --from-claude-memory --claude-project <slug>   # one project")


def _scan_claude_memory() -> list[tuple[str, int, int]]:
    """Return [(project_slug, file_count, total_bytes), ...] sorted by file_count desc."""
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return []
    out: list[tuple[str, int, int]] = []
    for project_dir in base.iterdir():
        if not project_dir.is_dir():
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        files = list(memory_dir.glob("*.md"))
        if not files:
            continue
        total_bytes = sum(f.stat().st_size for f in files if f.is_file())
        out.append((project_dir.name, len(files), total_bytes))
    out.sort(key=lambda t: -t[1])
    return out


def _count_claude_transcripts() -> int:
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return 0
    return sum(1 for _ in base.glob("*/*.jsonl"))


def _read_claude_memory(project_filter: str | None) -> tuple[str, Path | None, int]:
    """Read all Claude Code auto-memory markdown files into one text blob.

    Returns (concatenated_text, representative_source_path, file_count).
    Each file is prefixed with a `--- from: <project>/<file> ---` header so
    the LLM classifier knows provenance.
    """
    base = Path.home() / ".claude" / "projects"
    if not base.exists():
        return "", None, 0
    parts: list[str] = []
    count = 0
    repr_path: Path | None = None
    for project_dir in sorted(base.iterdir()):
        if not project_dir.is_dir():
            continue
        if project_filter and project_dir.name != project_filter:
            continue
        memory_dir = project_dir / "memory"
        if not memory_dir.is_dir():
            continue
        for f in sorted(memory_dir.glob("*.md")):
            try:
                content = f.read_text(encoding="utf-8")
            except OSError:
                continue
            if not content.strip():
                continue
            parts.append(f"--- from: {project_dir.name}/{f.name} ---\n{content}\n")
            count += 1
            if repr_path is None:
                repr_path = f
    return "\n".join(parts), repr_path, count


# ---------- skill install ----------

# ---------- v0.2 migration & changelog (git substrate) ----------

@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--dry-run", is_flag=True, help="Print what would happen, don't change anything.")
def migrate(root: str | None, dry_run: bool) -> None:
    """Migrate a v0.1 workspace to v0.2 git-based layout.

    \b
    Detects:
      - .forge/approved/sp/         (v0.1 parallel snapshot, will be deleted)
      - CHANGELOG.md (root)         (v0.1 audit file, imported into git history)
      - .forge/output/              (already-handled v0.1.0 layout, idempotent)

    Action:
      1. git init the workspace (if not already a git repo)
      2. Replay CHANGELOG.md entries as git commits (best-effort, preserves
         hash + message + timestamp in commit body and trailer)
      3. Make a final 'forge migrate to v0.2' commit covering current sp/+output/
      4. Remove .forge/approved/ and CHANGELOG.md
    """
    from forge.gate import _git
    from forge.gate import actions as gate
    from forge.gate.state import GateState
    import re as _re

    workspace = _root(root)
    state = GateState(workspace)
    state.migrate_layout()  # silent v0.1.0 → v0.1.1 first

    if not state.needs_v02_migration() and _git.is_git_repo(workspace):
        click.echo("already on v0.2 layout — nothing to migrate.")
        return

    click.echo(f"migrating {workspace} to v0.2 git-based layout")
    click.echo()

    # 1. git init if needed
    if not _git.is_git_repo(workspace):
        click.echo(f"  [{'dry-run' if dry_run else 'do'}] git init")
        if not dry_run:
            _git.init_repo(workspace)
        # Make sure .gitignore exists with .forge/
        gi = workspace / ".gitignore"
        if not gi.exists() or ".forge/" not in gi.read_text(encoding="utf-8", errors="ignore"):
            click.echo(f"  [{'dry-run' if dry_run else 'do'}] write .gitignore (.forge/)")
            if not dry_run:
                existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
                gi.write_text(existing.rstrip("\n") + "\n.forge/\n", encoding="utf-8")
    else:
        click.echo(f"  ok: already a git repo (HEAD={(_git.head_hash(workspace) or '<none>')[:12]})")

    # 2. Replay CHANGELOG.md entries (best-effort)
    changelog = state.root_changelog_path
    historical_entries: list[dict] = []
    if changelog.exists():
        click.echo()
        click.echo(f"  reading CHANGELOG.md to replay history...")
        # Format: "- 2026-04-26T01:44:58+00:00 approve (hash=874d403634b4) — message"
        line_re = _re.compile(
            r"^-\s+(?P<at>\S+)\s+(?P<kind>\w+)\s+\(hash=(?P<hash>\w+)\)\s*(?:—\s*(?P<note>.+))?\s*$"
        )
        for line in changelog.read_text(encoding="utf-8").splitlines():
            m = line_re.match(line.strip())
            if not m:
                continue
            historical_entries.append({
                "at": m.group("at"),
                "kind": m.group("kind"),
                "hash": m.group("hash"),
                "note": (m.group("note") or "").strip(),
            })
        click.echo(
            f"  found {len(historical_entries)} historical entries "
            f"(will preserve as commit messages on a single migration commit; "
            f"v0.1's `.forge/approved/` only kept the latest snapshot, so we can't "
            f"replay byte-perfect history)"
        )

    # 3. Final migration commit
    click.echo()
    click.echo(f"  [{'dry-run' if dry_run else 'do'}] rebuild output/ + commit current state")
    if not dry_run:
        gate.build(workspace)
        # Stage sp/ + output/ + .gitignore
        _git.add(workspace, ["sp", "output", ".gitignore"])
        # Build a multi-line message that preserves the v0.1 audit log
        body = ["forge migrate: import v0.1 workspace into git history", ""]
        if historical_entries:
            body.append("Imported v0.1 CHANGELOG.md entries (preserved as audit context):")
            for e in historical_entries:
                body.append(f"  - {e['at']} {e['kind']} ({e['hash'][:12]}) {('— ' + e['note']) if e['note'] else ''}")
        message = "\n".join(body)
        new_hash = _git.commit(
            workspace,
            message,
            trailers={"forge-provenance": "version=0.2.0 source=forge-migrate"},
            allow_empty=True,
        )
        click.echo(f"  → committed {new_hash[:12]}")

    # 4. Remove v0.1 artifacts
    click.echo()
    if state._legacy_approved_sp.exists():
        click.echo(f"  [{'dry-run' if dry_run else 'do'}] rm -rf .forge/approved/")
        if not dry_run:
            shutil.rmtree(state.forge_dir / "approved")
    if changelog.exists():
        click.echo(f"  [{'dry-run' if dry_run else 'do'}] rm CHANGELOG.md (history now lives in git log)")
        if not dry_run:
            changelog.unlink()

    click.echo()
    if dry_run:
        click.echo("dry-run complete. Re-run without --dry-run to apply.")
    else:
        click.echo("migration complete.")
        click.echo("  • approve/reject now use git commit / git restore")
        click.echo("  • `forge changelog` reads from git log")
        click.echo("  • `forge rollback` accepts any commit hash, not just the latest")


@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("-n", "--max-count", type=int, default=20, show_default=True, help="How many entries to show.")
@click.option("--all", "show_all", is_flag=True, help="Show all entries, no limit.")
def changelog(root: str | None, max_count: int, show_all: bool) -> None:
    """Show the audit log (rendered live from git log of sp/ history)."""
    from forge.gate import _git

    workspace = _root(root)
    if not _git.is_git_repo(workspace):
        click.echo(f"error: {workspace} is not a git repo (run `forge migrate` or `forge new`).", err=True)
        sys.exit(1)

    entries = _git.log_for_paths(
        workspace, ["sp"], max_count=None if show_all else max_count
    )
    if not entries:
        click.echo("(no commits touching sp/ yet)")
        return

    click.echo(f"# forge changelog ({workspace})")
    click.echo()
    for e in entries:
        # 2026-04-26T01:44:58+00:00 → 2026-04-26 01:44 UTC
        ts = e["at"].replace("T", " ").rsplit("+", 1)[0]
        line = f"- {ts}  {e['short']}  {e['subject']}"
        click.echo(line)
        if e["provenance"]:
            click.echo(f"    provenance: {e['provenance']}")


@main.command()
@click.argument("hash_prefix", required=False)
@click.option("--root", type=click.Path(), default=None)
def rollback(hash_prefix: str | None, root: str | None) -> None:
    """Roll sp/ + output/ back to a historical commit. No arg = list available."""
    from forge.governance.rollback import rollback as do_rollback

    try:
        result = do_rollback(_root(root), hash_prefix)
    except (RuntimeError, ValueError) as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)

    if hash_prefix is None:
        click.echo(f"current HEAD: {result['current_hash'][:12] if result['current_hash'] else '(none)'}")
        click.echo()
        click.echo(f"available approved hashes (most recent first):")
        for e in result["available"]:
            click.echo(f"  {e['short']}  {e['at'].replace('T', ' ').rsplit('+', 1)[0]}  {e['subject']}")
        click.echo()
        click.echo(f"to roll back: forge rollback <hash-prefix>")
        return

    click.echo(f"rolled sp/ + output/ back to {result['applied_to'][:12]}")
    if result.get("next_step"):
        click.echo()
        click.echo(result["next_step"])


# ---------- review (one-screen story: origin + semantic + affects + bench + diff) ----------

@main.command()
@click.option("--root", type=click.Path(), default=None)
@click.option("--no-color", is_flag=True, help="Disable colored output.")
@click.option(
    "--no-pager",
    is_flag=True,
    help="Print directly to stdout instead of paging through less.",
)
@click.option(
    "--summary-only",
    is_flag=True,
    help="Only show the panels (origin / semantic / affects / bench), skip the raw diff.",
)
@click.option(
    "--compact",
    is_flag=True,
    help="Ultra-compact 4-line view with action menu on line 1. For when you "
    "want quick CLI feedback and don't need an agent to render rich UI.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit structured ReviewSummary as JSON. Designed for an agent to "
    "parse and render as rich markdown (tables, headings) inside chat.",
)
@click.option(
    "--md",
    "as_md",
    is_flag=True,
    help="Write a full markdown review to <workspace>/REVIEW.md (gitignored). "
    "Open in Obsidian / VS Code / any markdown viewer — no folding, no length cap, "
    "annotatable. Recommended when chat folding gets in the way of long diffs.",
)
@click.option(
    "--md-out",
    type=click.Path(),
    default=None,
    help="With --md, override the output path (default: <workspace>/REVIEW.md).",
)
@click.option(
    "--full-provenance",
    is_flag=True,
    help="Don't fold provenance digest/byte hunks in the raw diff.",
)
@click.option(
    "--tui",
    is_flag=True,
    help="Open keyboard-driven TUI (textual): panels + diff + [a]pprove / [r]eject / "
    "[e]dit shortcuts. Requires real terminal — run yourself, not via an agent's Bash.",
)
def review(
    root: str | None,
    no_color: bool,
    no_pager: bool,
    summary_only: bool,
    compact: bool,
    as_json: bool,
    as_md: bool,
    md_out: str | None,
    full_provenance: bool,
    tui: bool,
) -> None:
    """One-screen review: where the change came from, what it does, who reads it,
    how big it is, plus the raw diff. Run before `forge approve`."""
    from forge.gate.review import build_review

    if tui:
        from forge import tui as tui_module
        sys.exit(tui_module.run(_root(root)))

    try:
        rev = build_review(_root(root))
    except RuntimeError as e:
        click.echo(f"error: {e}", err=True)
        sys.exit(1)

    if as_json:
        click.echo(_review_to_json(rev, root=_root(root)))
        return

    if as_md:
        ws = _root(root)
        out_path = Path(md_out).expanduser() if md_out else (ws / "REVIEW.md")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if not rev.has_changes:
            out_path.write_text("# forge review\n\nno changes since last approve\n", encoding="utf-8")
            click.echo(f"wrote {out_path} (no changes)")
            return
        md = _render_review_markdown(rev, ws)
        out_path.write_text(md, encoding="utf-8")
        # Add to .gitignore if not already there (so reviews don't pollute git)
        _ensure_gitignore_entry(ws, "REVIEW.md")
        click.echo(f"wrote {out_path}")
        click.echo()
        click.echo("Open it:")
        click.echo(f"  • Obsidian / VS Code / cat {out_path}")
        click.echo()
        click.echo("Reply (in chat or terminal): a approve · r reject · e <section> edit · q quit")
        return

    if not rev.has_changes:
        click.echo("no changes since last approve")
        return

    use_color = not no_color
    if no_pager:
        use_color = use_color and click.get_text_stream("stdout").isatty()

    if compact:
        text = _format_review_compact(rev, use_color=use_color)
    else:
        text = _format_review(rev, use_color=use_color)
        if not summary_only:
            text += "\n\n" + _format_diff(
                result=rev.diff_result,
                source_only=False,
                output_only=False,
                config_filter=None,
                use_color=use_color,
                full_provenance=full_provenance,
            )
        text += "\n\n" + _format_review_actions(rev, use_color=use_color)

    if no_pager or not click.get_text_stream("stdout").isatty():
        click.echo(text)
    else:
        click.echo_via_pager(text, color=use_color)


def _format_review(rev, use_color: bool) -> str:
    """Render origin / semantic / affects / bench panels."""
    out: list[str] = []

    def style(s: str, **kw):
        return click.style(s, **kw) if use_color else s

    title = "══ forge review · proposed change (not yet approved) ══"
    out.append(style(title, bold=True))
    out.append("")

    # ---- Origin panel ----
    out.append(style("┌─ Source ─────────────────────────────────────────────", fg="cyan", bold=True))
    if rev.origin_events:
        for ev in rev.origin_events:
            out.append(f"│ Origin:  {style(ev.summary, bold=True)}")
            ts = ev.at.replace("T", " ").rsplit("+", 1)[0]
            sects = ", ".join(ev.sections_touched) if ev.sections_touched else "(none recorded)"
            out.append(f"│           at {ts} UTC, touched: {sects}")
            if ev.kind == "ingest" and ev.details.get("method") == "dump":
                out.append(f"│           {style('⚠', fg='yellow')} method=dump: everything in workspace.md, split into 5 sections via $EDITOR")
            elif ev.kind == "ingest" and ev.details.get("method") == "emit":
                out.append(f"│           {style('▸', fg='cyan')} method=emit: agent classifies in own context, then writes per-section files")
    else:
        out.append(f"│ Origin:  hand edit (no recorded ingest/event)")
    n_sections = len(rev.section_changes)
    out.append(f"│ Touched: {n_sections} section{'s' if n_sections != 1 else ''}")
    out.append(style("└──────────────────────────────────────────────────────", fg="cyan"))
    out.append("")

    # ---- What changed (semantic) ----
    out.append(style("┌─ What changed ───────────────────────────────────────", fg="cyan", bold=True))
    if not rev.section_changes:
        out.append("│ (config-only changes, see diff below)")
    for sc in rev.section_changes:
        bytes_arrow = f"{sc.bytes_before}B → {sc.bytes_after}B"
        delta = sc.bytes_delta
        sign = "+" if delta >= 0 else ""
        out.append(f"│ • {style(sc.name + '.md', bold=True)}: {sc.summary}")
        out.append(f"│     {bytes_arrow}  ({sign}{delta}B, +{sc.lines_added}/-{sc.lines_removed} lines)")
    out.append(style("└──────────────────────────────────────────────────────", fg="cyan"))
    out.append("")

    # ---- Affects panel ----
    out.append(style("┌─ Affects ────────────────────────────────────────────", fg="cyan", bold=True))
    if rev.output_changes:
        out.append("│ Outputs that will rebuild on approve:")
        for oc in rev.output_changes:
            sign = "+" if oc.bytes_delta >= 0 else ""
            out.append(
                f"│   • {style('output/' + oc.filename, bold=True)} "
                f"({sign}{oc.bytes_delta}B)  ← {oc.runtime_description}"
            )
    if rev.target_bindings:
        out.append("│")
        out.append("│ External targets (auto-sync on approve):")
        for tb in rev.target_bindings:
            out.append(f"│   • {style(tb.path, bold=True)}  [{tb.mode}]")
    else:
        out.append("│")
        out.append(f"│ {style('No external target bound.', fg='yellow')} `forge approve` will only update output/.")
        out.append("│   Bind one with: forge target install claude-code --to ~/.claude/CLAUDE.md")
    out.append(style("└──────────────────────────────────────────────────────", fg="cyan"))
    out.append("")

    # ---- Bench panel ----
    out.append(style("┌─ Bench ──────────────────────────────────────────────", fg="cyan", bold=True))
    growths: list[str] = []
    for sc in rev.section_changes:
        sign = "+" if sc.bytes_delta >= 0 else ""
        line = f"│ {sc.name:18} {sign}{sc.bytes_delta:>5}B  ({sc.bytes_before} → {sc.bytes_after})"
        if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
            line += f"  {style(f'⚠ {sc.growth_pct:+.0f}%', fg='yellow', bold=True)}"
            growths.append(sc.name)
        out.append(line)
    if not rev.section_changes:
        out.append("│ (no section-level changes)")
    out.append(style("└──────────────────────────────────────────────────────", fg="cyan"))

    return "\n".join(out)


def _render_review_markdown(rev, root: Path) -> str:
    """Render a ReviewSummary as a long-form markdown document.

    Unlike --json (data for agent rendering) or --compact (4-line CLI), this
    produces the actual document the user reads in Obsidian / VS Code. Includes
    summary table, per-section diff, outputs, action menu.
    """
    from forge.gate import _git as _git_mod

    parts: list[str] = []
    parts.append(f"# Review · `{root}`")
    parts.append("")

    # Origin
    if rev.origin_events:
        parts.append("## Origin")
        parts.append("")
        for ev in rev.origin_events:
            ts = ev.at.replace("T", " ").rsplit("+", 1)[0] + " UTC"
            parts.append(f"- `{ev.summary}` _{ts}_")
        parts.append("")
    else:
        parts.append("## Origin")
        parts.append("")
        parts.append("- hand edit (no recorded ingest/event)")
        parts.append("")

    # Summary table
    if rev.section_changes:
        parts.append("## Summary")
        parts.append("")
        parts.append("| Section | Δ bytes | Lines | Note |")
        parts.append("|---|---|---|---|")
        for sc in rev.section_changes:
            sign = "+" if sc.bytes_delta >= 0 else ""
            cell = f"{sign}{sc.bytes_delta}B"
            if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
                cell = f"**{cell}** ⚠ {sc.growth_pct:+.0f}%"
            parts.append(
                f"| `{sc.name}` | {cell} | +{sc.lines_added} / -{sc.lines_removed} | {sc.summary} |"
            )
        parts.append("")

    # Per-section diffs
    if rev.section_changes and _git_mod.is_git_repo(root):
        parts.append("## Detailed changes")
        parts.append("")
        for sc in rev.section_changes:
            sign = "+" if sc.bytes_delta >= 0 else ""
            label = f"{sign}{sc.bytes_delta}B"
            if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
                label = f"**{label}** ⚠ {sc.growth_pct:+.0f}%"
            parts.append(f"### `{sc.name}.md` ({label})")
            parts.append("")
            try:
                diff_text = _git_mod.diff_paths(root, [f"sp/section/{sc.name}.md"])
                diff_text = _strip_git_diff_header(diff_text)
            except Exception:
                diff_text = "(diff unavailable)"
            parts.append("```diff")
            parts.append(diff_text.rstrip())
            parts.append("```")
            parts.append("")

    # Outputs
    if rev.output_changes:
        parts.append("## Outputs (rebuild on approve)")
        parts.append("")
        for oc in rev.output_changes:
            sign = "+" if oc.bytes_delta >= 0 else ""
            parts.append(
                f"- `output/{oc.filename}` **{sign}{oc.bytes_delta}B** ← {oc.runtime_description}"
            )
        parts.append("")

    # Targets
    if rev.target_bindings:
        parts.append("## Sync targets (auto-pushed on approve)")
        parts.append("")
        for tb in rev.target_bindings:
            parts.append(f"- `{tb.path}` `[{tb.mode}]` ← {tb.adapter}")
        parts.append("")
    else:
        parts.append(
            "> **No external target bound.** `forge approve` only updates `output/`. "
            "Bind one with `forge target install claude-code --to ~/.claude/CLAUDE.md "
            "--mode symlink` for auto-sync."
        )
        parts.append("")

    # Action footer
    parts.append("---")
    parts.append("")
    parts.append("**Reply** (in chat or terminal):")
    parts.append("")
    parts.append("- `a` or `forge approve -m \"<msg>\"` — ship this change")
    parts.append("- `r` or `forge reject` — discard, restore HEAD")
    parts.append("- `e <section>` — edit a section (then re-run `forge review --md`)")
    parts.append("- `q` — leave as-is, decide later")
    parts.append("")
    parts.append("_Generated by `forge review --md`. Auto-cleared on approve / reject._")

    return "\n".join(parts) + "\n"


def _ensure_gitignore_entry(root: Path, entry: str) -> None:
    """Append `entry` to <root>/.gitignore if not already there."""
    gi = root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = [ln.strip() for ln in existing.splitlines()]
    if entry in lines:
        return
    new = existing
    if new and not new.endswith("\n"):
        new += "\n"
    new += entry + "\n"
    gi.write_text(new, encoding="utf-8")


def _review_to_json(rev, root: Path | None = None) -> str:
    """Emit ReviewSummary as JSON for agent rendering. Includes per-section
    diff text (so agent can render actual changed lines, not just byte deltas)."""
    from forge.gate import _git as _git_mod

    section_diffs: dict[str, str] = {}
    if root is not None and _git_mod.is_git_repo(root):
        for sc in (rev.section_changes or []):
            try:
                d = _git_mod.diff_paths(root, [f"sp/section/{sc.name}.md"])
                section_diffs[sc.name] = _strip_git_diff_header(d)
            except Exception:
                section_diffs[sc.name] = ""

    payload = {
        "has_changes": rev.has_changes,
        "origin": [
            {
                "kind": ev.kind,
                "summary": ev.summary,
                "at": ev.at,
                "details": ev.details,
                "sections_touched": ev.sections_touched,
            }
            for ev in (rev.origin_events or [])
        ],
        "section_changes": [
            {
                "name": sc.name,
                "summary": sc.summary,
                "bytes_before": sc.bytes_before,
                "bytes_after": sc.bytes_after,
                "bytes_delta": sc.bytes_delta,
                "lines_added": sc.lines_added,
                "lines_removed": sc.lines_removed,
                "growth_pct": round(sc.growth_pct, 1) if sc.bytes_before > 0 else None,
                "warn": abs(sc.growth_pct) >= 50 and sc.bytes_before > 0,
                "diff": section_diffs.get(sc.name, ""),
            }
            for sc in (rev.section_changes or [])
        ],
        "output_changes": [
            {
                "config_name": oc.config_name,
                "adapter": oc.adapter,
                "filename": oc.filename,
                "bytes_before": oc.bytes_before,
                "bytes_after": oc.bytes_after,
                "bytes_delta": oc.bytes_delta,
                "runtime": oc.runtime_description,
            }
            for oc in (rev.output_changes or [])
        ],
        "targets": [
            {"adapter": tb.adapter, "path": tb.path, "mode": tb.mode}
            for tb in (rev.target_bindings or [])
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _strip_git_diff_header(diff_text: str) -> str:
    """Drop git's diff header lines (`diff --git ...`, `index ...`) but keep
    the unified diff body (---, +++, @@, content). Easier to render as a
    `diff` code block in markdown."""
    if not diff_text:
        return ""
    lines = diff_text.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("diff --git ") or line.startswith("index "):
            continue
        out.append(line)
    return "\n".join(out)


def _format_review_compact(rev, use_color: bool) -> str:
    """Ultra-compact review (4 lines). Action menu on LINE 1 so it's visible
    even when chat tools (Claude Code Bash output) fold to a preview.

    Layout:
        Line 1: summary + action menu  ← always visible even when folded
        Line 2: per-section deltas (one-liners, ⚠ for ≥50% change)
        Line 3: outputs deltas
        Line 4: origin (where this came from)
    """
    def style(s: str, **kw):
        return click.style(s, **kw) if use_color else s

    out: list[str] = []

    # Line 1: counts + ACTION MENU (this is what survives folding)
    n = len(rev.section_changes)
    n_warn = sum(
        1 for sc in rev.section_changes
        if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0
    )
    warn_marker = style(f" ⚠ {n_warn}", fg="yellow", bold=True) if (n_warn and use_color) else (f" ⚠ {n_warn}" if n_warn else "")

    a = style("[a]", fg="green", bold=True) if use_color else "[a]"
    r = style("[r]", fg="red", bold=True) if use_color else "[r]"
    e = style("[e]", fg="cyan", bold=True) if use_color else "[e]"
    d = style("[d]", fg="white", bold=True) if use_color else "[d]"
    q = style("[q]", fg="white") if use_color else "[q]"
    menu = f"{a}pprove {r}eject {e}dit {d}iff {q}uit"

    out.append(
        style(f"forge review · {n} changed{warn_marker}", bold=True)
        + f"  ·  reply {menu}"
    )

    # Line 2: per-section deltas, separated by " · "
    if rev.section_changes:
        parts = []
        for sc in rev.section_changes:
            sign = "+" if sc.bytes_delta >= 0 else ""
            warn = ""
            if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
                w = "⚠"
                warn = style(w, fg="yellow", bold=True) if use_color else w
            parts.append(f"{sc.name} {sign}{sc.bytes_delta}B{warn}")
        out.append("  " + " · ".join(parts))

    # Line 3: outputs
    if rev.output_changes:
        outputs_str = ", ".join(
            f"{oc.filename} {('+' if oc.bytes_delta >= 0 else '')}{oc.bytes_delta}B"
            for oc in rev.output_changes
        )
        line = f"  outputs: {outputs_str}"
        if rev.target_bindings:
            tb = rev.target_bindings[0]
            line += f"  →  {tb.path}"
        out.append(line)

    # Line 4: origin (truncate to keep one-line)
    if rev.origin_events:
        ev = rev.origin_events[0]
        origin_short = ev.summary.replace(" (agent will classify)", "")
        if len(origin_short) > 80:
            origin_short = origin_short[:77] + "..."
        out.append(f"  from: {origin_short}")
    else:
        out.append("  from: hand edit")

    return "\n".join(out)


def _format_review_actions(rev, use_color: bool) -> str:
    """Action menu footer — single-letter shortcuts.

    Designed so an agent can paste this verbatim, then interpret a one-letter
    user reply (a / r / e / d / q) as the chosen action without parsing
    free-form text.
    """
    def style(s: str, **kw):
        return click.style(s, **kw) if use_color else s

    a = style("[a]", fg="green", bold=True) if use_color else "[a]"
    r = style("[r]", fg="red", bold=True) if use_color else "[r]"
    e = style("[e]", fg="cyan", bold=True) if use_color else "[e]"
    d = style("[d]", fg="white", bold=True) if use_color else "[d]"
    q = style("[q]", fg="white") if use_color else "[q]"

    section_names = sorted({sc.name for sc in rev.section_changes})
    sections_hint = ""
    if section_names:
        sections_hint = " (" + ", ".join(section_names[:3]) + (", ..." if len(section_names) > 3 else "") + ")"

    lines = [
        style("══ Reply with a single letter ══", bold=True),
        f"  {a} approve     ship this change (will prompt for commit message)",
        f"  {r} reject      discard, restore HEAD",
        f"  {e} edit        pick a section to edit{sections_hint}",
        f"  {d} diff        show full unified diff (skipped above if --summary-only)",
        f"  {q} quit        do nothing, exit",
    ]
    if not rev.target_bindings:
        lines.append("")
        lines.append(
            f"  (no external target bound — `forge target install claude-code "
            f"--to ~/.claude/CLAUDE.md --mode symlink` if you want "
            f"approve to auto-sync to live Claude Code)"
        )
    lines.append("")
    lines.append(style("Tip: ", bold=True) + "for a real keyboard-driven TUI in your own terminal: forge review --tui")
    return "\n".join(lines)


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


@main.command("self-install")
@click.option("--dry-run", is_flag=True, help="Report what would happen without writing files.")
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite even files without a managed-by marker (clobbers user-owned content).",
)
@click.option(
    "--runtime",
    "runtime_names",
    multiple=True,
    help="Restrict to specific runtime(s). Default: every detected runtime.",
)
def self_install_cmd(dry_run: bool, force: bool, runtime_names: tuple[str, ...]) -> None:
    """Bind forge-as-skill into every detected agent runtime (idempotent).

    Currently supports: claude-code (~/.claude/skills/forge/SKILL.md).

    Re-run safely after `forge update` — files with the managed-by marker are
    refreshed; unmanaged files report a conflict and are not touched.
    """
    from forge.self_install import self_install, format_summary

    actions = self_install(
        dry_run=dry_run,
        force=force,
        only=list(runtime_names) if runtime_names else None,
    )
    click.echo(format_summary(actions))

    conflicts = [a for a in actions if a.status == "conflict"]
    if conflicts:
        click.echo(
            f"\n{len(conflicts)} conflict(s). Re-run with --force to overwrite, "
            "or remove the offending file(s) and re-run.",
            err=True,
        )
        sys.exit(1)

    detected = [a for a in actions if a.status not in ("skipped", "conflict")]
    if detected and not dry_run:
        click.echo("\nTriggers in Claude Code (any of):")
        click.echo("  'approve my changes' / 'review my context' / '过一下' / '审一下'")
        click.echo("  'forge approve' / 'forge diff' / 'forge reject'")


@main.command("update")
@click.option("--dry-run", is_flag=True, help="Report what would happen without running pipx/uv or writing files.")
def update_cmd(dry_run: bool) -> None:
    """Upgrade the forge CLI (when possible) and refresh self-install bindings.

    Picks the right strategy based on how forge was installed:
      pipx     → pipx upgrade context-forge
      uv tool  → uv tool upgrade context-forge
      editable → skipped (you control the source — git pull yourself)
      system   → printed instructions, not auto-run

    Always re-runs self-install at the end so skills track the current version.
    """
    from forge.update import run_update

    action = run_update(dry_run=dry_run)
    click.echo(f"install kind: {action.kind}")
    if action.upgrade_cmd:
        click.echo(f"upgrade cmd:  {' '.join(action.upgrade_cmd)}  [{action.upgrade_status}]")
    else:
        click.echo(f"upgrade:      {action.upgrade_status}")
    if action.upgrade_output:
        for line in action.upgrade_output.splitlines():
            click.echo(f"  {line}")
    click.echo()
    click.echo("self-install:")
    click.echo(action.self_install_summary)
    if action.upgrade_status == "failed":
        sys.exit(1)


@main.command("install-skill", hidden=True)
@click.option("--force", is_flag=True, help="Deprecated; passed through to self-install.")
@click.pass_context
def install_skill(ctx: click.Context, force: bool) -> None:
    """[deprecated] Use `forge self-install`."""
    click.echo(
        "warning: `forge install-skill` is deprecated. Use `forge self-install`.",
        err=True,
    )
    ctx.invoke(self_install_cmd, dry_run=False, force=force, runtime_names=())


if __name__ == "__main__":
    main()
