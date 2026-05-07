"""v0.6.0: web-clipping synthesize tests.

Cover the four pieces of work specified for v0.6:

  1. WebClipping schema parsing + KB topic discovery.
  2. `forge monitor` reports unsynthesized clippings as pending attention.
  3. `forge synthesize-clipping <file>` writes capture + inbox(type=
     web-clipping-synthesize) and lists candidate KB topics in the capture.
  4. `forge pr done` (= approve) on a `web-clipping-synthesize` PR stamps
     `synthesized_at` + `synthesized_into` on the source clipping frontmatter,
     and the clipping file itself is never deleted.

End-to-end: a single fixture personalOS root with one clipping and one KB
topic, monitor → synthesize → fill schema → approve → verify clipping
frontmatter was updated.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from forge.cli import main as cli_main
from forge.governance.web_clipping import (
    WebClipping,
    build_synthesize_capture_markdown,
    discover_clippings,
    discover_kb_topic_files,
    format_monitor_lines,
    kb_topic_paths_from_propagation,
    load_clipping,
    mark_synthesized,
    pending_clippings,
    split_frontmatter,
)


# ---------- helpers ----------


def _make_personalos_root(tmp_path: Path) -> Path:
    """Build a minimal personalOS layout with web clipping + KB topic dirs."""
    root = tmp_path / "os"
    (root / "capture" / "import").mkdir(parents=True)
    (root / "capture" / "web clipping").mkdir(parents=True)
    (root / "system" / "inbox").mkdir(parents=True)
    (root / "system" / "pr").mkdir(parents=True)
    (root / "public knowledge base" / "topic").mkdir(parents=True)
    return root


def _write_clipping(
    root: Path,
    slug: str,
    *,
    title: str = "",
    source_url: str = "",
    body: str = "Content of the clipping.",
    synthesized_at: str = "",
    synthesized_into: list[str] | None = None,
    extra_frontmatter: dict | None = None,
) -> Path:
    """Write a clipping under `capture/web clipping/<slug>.md`."""
    path = root / "capture" / "web clipping" / f"{slug}.md"
    fm_lines = ["---"]
    if title:
        fm_lines.append(f'title: "{title}"')
    if source_url:
        fm_lines.append(f'source: "{source_url}"')
    fm_lines.append("created: 2026-04-17")
    if synthesized_at:
        fm_lines.append(f"synthesized_at: {synthesized_at}")
    if synthesized_into:
        fm_lines.append("synthesized_into:")
        for s in synthesized_into:
            fm_lines.append(f"  - {s}")
    if extra_frontmatter:
        for k, v in extra_frontmatter.items():
            fm_lines.append(f"{k}: {v}")
    fm_lines.append("---")
    path.write_text("\n".join(fm_lines) + "\n\n" + body + "\n", encoding="utf-8")
    return path


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate HOME so monitor's _import_updates doesn't see the real
    ~/.claude/CLAUDE.md / ~/.codex/AGENTS.md when the dev box has them."""
    fake = tmp_path / "fakehome"
    fake.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(fake))
    return fake


def _write_kb_topic(root: Path, rel_path: str, body: str = "# Topic\n") -> Path:
    """Write a KB topic at `public knowledge base/topic/<rel_path>`."""
    p = root / "public knowledge base" / "topic" / rel_path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


# ---------- 1. WebClipping schema parsing ----------


def test_load_clipping_with_full_frontmatter(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    p = _write_clipping(
        root,
        "thread-by-bcherny",
        title="Thread by @bcherny",
        source_url="https://x.com/bcherny/status/1",
    )
    loaded = load_clipping(p)
    assert loaded is not None
    assert loaded.slug == "thread-by-bcherny"
    assert loaded.title == "Thread by @bcherny"
    assert loaded.source_url == "https://x.com/bcherny/status/1"
    assert loaded.synthesized_at == ""
    assert loaded.synthesized_into == []
    assert loaded.is_synthesized is False


def test_load_clipping_with_synthesized_marker(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    p = _write_clipping(
        root,
        "synthesized",
        title="X",
        synthesized_at="2026-05-07T10:00:00+00:00",
        synthesized_into=[
            "public knowledge base/topic/tech/ai/claude-code.md",
        ],
    )
    loaded = load_clipping(p)
    assert loaded is not None
    assert loaded.is_synthesized is True
    assert loaded.synthesized_at == "2026-05-07T10:00:00+00:00"
    assert loaded.synthesized_into == [
        "public knowledge base/topic/tech/ai/claude-code.md",
    ]


def test_discover_clippings_skips_files_without_frontmatter(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_clipping(root, "good", title="Good")
    # File without frontmatter — should be silently skipped.
    bad = root / "capture" / "web clipping" / "no-frontmatter.md"
    bad.write_text("# Just plain markdown\n", encoding="utf-8")

    found = discover_clippings(root)
    slugs = [c.slug for c in found]
    assert slugs == ["good"]


def test_pending_clippings_excludes_synthesized(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_clipping(root, "alpha", title="A")
    _write_clipping(
        root, "beta", title="B",
        synthesized_at="2026-05-07T00:00:00+00:00",
        synthesized_into=["public knowledge base/topic/x.md"],
    )
    pending = pending_clippings(root)
    assert [c.slug for c in pending] == ["alpha"]


def test_split_frontmatter_handles_missing(tmp_path: Path) -> None:
    fm, body = split_frontmatter("plain text\nno frontmatter")
    assert fm is None
    assert body == "plain text\nno frontmatter"


# ---------- 2. KB topic discovery ----------


def test_discover_kb_topic_files_excludes_index_and_log(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    topic_root = root / "public knowledge base" / "topic"
    (topic_root / "index.md").write_text("# Index\n", encoding="utf-8")
    (topic_root / "log.md").write_text("# Log\n", encoding="utf-8")
    _write_kb_topic(root, "tech/ai/claude-code.md")
    _write_kb_topic(root, "tech/ai/codex.md")
    _write_kb_topic(root, "personal/ikigai.md")

    found = discover_kb_topic_files(root)
    rel = [f.relative_to(topic_root).as_posix() for f in found]
    assert "index.md" not in rel
    assert "log.md" not in rel
    assert sorted(rel) == [
        "personal/ikigai.md",
        "tech/ai/claude-code.md",
        "tech/ai/codex.md",
    ]


def test_discover_kb_topic_files_returns_empty_when_dir_missing(tmp_path: Path) -> None:
    root = tmp_path / "no-personalos"
    root.mkdir()
    assert discover_kb_topic_files(root) == []


# ---------- 3. monitor extension ----------


def test_format_monitor_lines_clean_when_no_clippings(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    issues, actions = format_monitor_lines(root)
    assert issues == []
    assert actions == []


def test_format_monitor_lines_reports_pending(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_clipping(root, "x", title="x")
    _write_clipping(root, "y", title="y")
    issues, actions = format_monitor_lines(root)
    assert len(issues) == 1
    assert "web-clipping pending synthesize: 2" in issues[0]
    assert len(actions) == 2
    assert all("forge synthesize-clipping" in a for a in actions)
    # paths quoted because `web clipping/` has a space
    assert all('"capture/web clipping/' in a for a in actions)


def test_monitor_cli_reports_pending_clipping(tmp_path: Path, isolated_home: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_clipping(root, "thread-by-bcherny", title="Thread")

    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    # monitor uses exit 0 for `status: attention` (only doctor failures exit 1).
    assert result.exit_code == 0, result.output
    assert "status: attention" in result.output
    assert "web-clipping pending synthesize: 1" in result.output
    assert "forge synthesize-clipping" in result.output


def test_monitor_cli_silent_when_clipping_synthesized(tmp_path: Path, isolated_home: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_clipping(
        root, "done", title="done",
        synthesized_at="2026-05-07T10:00:00+00:00",
        synthesized_into=["public knowledge base/topic/tech/ai/claude-code.md"],
    )

    runner = CliRunner()
    result = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert result.exit_code == 0, result.output
    assert "web-clipping pending synthesize" not in result.output
    assert "status: clean" in result.output


# ---------- 4. synthesize-clipping CLI ----------


def test_synthesize_clipping_creates_capture_and_inbox(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_kb_topic(root, "tech/ai/claude-code.md")
    _write_kb_topic(root, "tech/ai/codex.md")
    clip = _write_clipping(
        root, "thread-by-bcherny",
        title="Thread by @bcherny",
        source_url="https://x.com/bcherny/status/1",
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        [
            "synthesize-clipping",
            str(clip.relative_to(root)),
            "--root", str(root),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "captured web-clipping-synthesize" in result.output
    assert "candidate KB topics: 2" in result.output

    # Capture file landed under capture/import/<batch>/
    capture_files = list((root / "capture" / "import").rglob("synthesize-clipping-*.md"))
    assert len(capture_files) == 1
    capture_text = capture_files[0].read_text(encoding="utf-8")
    # capture frontmatter has type=web-clipping-synthesize and the clipping path
    assert "type: web-clipping-synthesize" in capture_text
    assert "web_clipping: capture/web clipping/thread-by-bcherny.md" in capture_text
    assert "Thread by @bcherny" in capture_text
    # KB topic candidates listed in body
    assert "public knowledge base/topic/tech/ai/claude-code.md" in capture_text
    assert "public knowledge base/topic/tech/ai/codex.md" in capture_text

    # Inbox item was created with the right type
    inbox_items = list((root / "system" / "inbox").glob("*.md"))
    assert len(inbox_items) == 1
    inbox_text = inbox_items[0].read_text(encoding="utf-8")
    assert "type: web-clipping-synthesize" in inbox_text
    assert "web_clipping: capture/web clipping/thread-by-bcherny.md" in inbox_text


def test_synthesize_clipping_accepts_bare_filename(tmp_path: Path) -> None:
    """`forge synthesize-clipping foo.md` resolves under `capture/web clipping/`."""
    root = _make_personalos_root(tmp_path)
    _write_clipping(root, "alpha", title="A")

    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["synthesize-clipping", "alpha.md", "--root", str(root)],
    )
    assert result.exit_code == 0, result.output

    inbox_items = list((root / "system" / "inbox").glob("*.md"))
    assert len(inbox_items) == 1


def test_synthesize_clipping_rejects_nonexistent(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_main, ["synthesize-clipping", "missing.md", "--root", str(root)],
    )
    assert result.exit_code == 1
    assert "clipping not found" in result.output


def test_synthesize_clipping_rejects_no_frontmatter(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    bad = root / "capture" / "web clipping" / "bad.md"
    bad.write_text("# No frontmatter\n", encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli_main,
        ["synthesize-clipping", str(bad), "--root", str(root)],
    )
    assert result.exit_code == 1
    assert "frontmatter" in result.output


def test_synthesize_clipping_multiple_independent(tmp_path: Path) -> None:
    """Two clippings can each be synthesized independently — separate captures
    + inbox items, each preserving its own clipping reference."""
    root = _make_personalos_root(tmp_path)
    _write_kb_topic(root, "tech/ai/claude-code.md")
    _write_clipping(root, "alpha", title="A")
    _write_clipping(root, "beta", title="B")

    runner = CliRunner()
    r1 = runner.invoke(cli_main, ["synthesize-clipping", "alpha.md", "--root", str(root)])
    assert r1.exit_code == 0, r1.output
    r2 = runner.invoke(cli_main, ["synthesize-clipping", "beta.md", "--root", str(root)])
    assert r2.exit_code == 0, r2.output

    inbox_items = sorted((root / "system" / "inbox").glob("*.md"))
    assert len(inbox_items) == 2
    inbox_texts = [p.read_text(encoding="utf-8") for p in inbox_items]
    inbox_blob = "\n".join(inbox_texts)
    assert "capture/web clipping/alpha.md" in inbox_blob
    assert "capture/web clipping/beta.md" in inbox_blob


# ---------- build_synthesize_capture_markdown ----------


def test_build_synthesize_capture_markdown_lists_candidates(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    t1 = _write_kb_topic(root, "tech/ai/claude-code.md")
    t2 = _write_kb_topic(root, "tech/ai/codex.md")
    clip_path = _write_clipping(root, "x", title="X clip", source_url="https://example/x")
    clipping = load_clipping(clip_path)
    assert clipping is not None

    text = build_synthesize_capture_markdown(
        clipping, [t1, t2], root, "2026-05-07T12:00:00+00:00"
    )
    assert "type: web-clipping-synthesize" in text
    assert "captured_at: 2026-05-07T12:00:00+00:00" in text
    assert "X clip" in text
    assert "public knowledge base/topic/tech/ai/claude-code.md" in text
    assert "public knowledge base/topic/tech/ai/codex.md" in text


def test_build_synthesize_capture_markdown_no_topics_yet(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    clip_path = _write_clipping(root, "x", title="X")
    clipping = load_clipping(clip_path)
    assert clipping is not None
    text = build_synthesize_capture_markdown(
        clipping, [], root, "2026-05-07T12:00:00+00:00"
    )
    assert "no `public knowledge base/topic/" in text


# ---------- mark_synthesized helper ----------


def test_mark_synthesized_writes_frontmatter(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    p = _write_clipping(root, "x", title="X")
    ok = mark_synthesized(
        p,
        into=["public knowledge base/topic/tech/ai/claude-code.md"],
        at="2026-05-07T12:00:00+00:00",
    )
    assert ok is True
    text = p.read_text(encoding="utf-8")
    assert "synthesized_at: '2026-05-07T12:00:00+00:00'" in text or \
           "synthesized_at: 2026-05-07T12:00:00+00:00" in text
    assert "public knowledge base/topic/tech/ai/claude-code.md" in text
    # body preserved
    assert "Content of the clipping." in text


def test_mark_synthesized_unions_existing_entries(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    p = _write_clipping(
        root, "x", title="X",
        synthesized_at="2026-05-01T00:00:00+00:00",
        synthesized_into=["public knowledge base/topic/old.md"],
    )
    ok = mark_synthesized(
        p,
        into=[
            "public knowledge base/topic/old.md",  # duplicate
            "public knowledge base/topic/new.md",
        ],
        at="2026-05-07T00:00:00+00:00",
    )
    assert ok is True
    loaded = load_clipping(p)
    assert loaded is not None
    assert loaded.synthesized_into == [
        "public knowledge base/topic/old.md",
        "public knowledge base/topic/new.md",
    ]


# ---------- propagation parsing ----------


def test_kb_topic_paths_from_propagation_extracts_nested(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    propagation = [
        {
            "branch": "a",
            "node": {
                "path": "system/inbox/0001-x.md",
                "label": "monitor",
                "children": [
                    {
                        "branch": "a1",
                        "node": {
                            "path": "public knowledge base/topic/tech/ai/claude-code.md",
                            "label": "kb topic update",
                        },
                    },
                ],
            },
        },
        {
            "branch": "b",
            "node": {
                "path": "public knowledge base/topic/tech/ai/codex.md",
                "label": "kb topic update",
            },
        },
    ]
    found = kb_topic_paths_from_propagation(root, propagation)
    assert found == [
        "public knowledge base/topic/tech/ai/claude-code.md",
        "public knowledge base/topic/tech/ai/codex.md",
    ]


def test_kb_topic_paths_from_propagation_ignores_non_topic_paths(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    propagation = [
        {
            "branch": "a",
            "node": {
                "path": "system/inbox/x.md",
                "children": [
                    {
                        "branch": "a1",
                        "node": {"path": "capture/import/2026/x.md"},
                    },
                ],
            },
        },
    ]
    found = kb_topic_paths_from_propagation(root, propagation)
    assert found == []


# ---------- 5. approve write-back ----------


def test_pr_done_marks_clipping_synthesized(tmp_path: Path) -> None:
    """End-to-end: build a fake `web-clipping-synthesize` PR with KB topic
    paths in propagation, run `forge pr done`, and verify the clipping
    frontmatter gets stamped.
    """
    root = _make_personalos_root(tmp_path)
    _write_kb_topic(root, "tech/ai/claude-code.md")
    clip = _write_clipping(root, "alpha", title="A")

    # Run synthesize-clipping to produce a real inbox + capture
    runner = CliRunner()
    r1 = runner.invoke(cli_main, ["synthesize-clipping", "alpha.md", "--root", str(root)])
    assert r1.exit_code == 0, r1.output

    # Find the generated inbox file
    inbox_items = list((root / "system" / "inbox").glob("*.md"))
    assert len(inbox_items) == 1
    inbox_rel = inbox_items[0].relative_to(root).as_posix()

    # Hand-craft a proposal.md that mimics what `forge proposal new` would
    # scaffold + the agent would fill in. Schema-wise we need:
    #   - frontmatter: kind: pr, type: web-clipping-synthesize, inbox_sources,
    #     items[].propagation pointing at the KB topic.
    pr_id = "20260507-100000-synthesize-alpha"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    proposal = pr_dir / "proposal.md"
    proposal.write_text(
        "---\n"
        "kind: pr\n"
        "type: web-clipping-synthesize\n"
        "status: pending\n"
        "created_at: 2026-05-07T10:00:00+00:00\n"
        "revised_at: 2026-05-07T10:00:00+00:00\n"
        "inbox_sources:\n"
        f"  - {inbox_rel}\n"
        "items:\n"
        "  - id: '1'\n"
        "    monitor_info: synthesize alpha\n"
        "    disposition: APPLY\n"
        "    rationale: clip on claude code\n"
        "    propagation:\n"
        "      - branch: a\n"
        "        node:\n"
        "          path: capture/web clipping/alpha.md\n"
        "          label: clipping\n"
        "          children:\n"
        "            - branch: a1\n"
        "              node:\n"
        "                path: public knowledge base/topic/tech/ai/claude-code.md\n"
        "                label: kb topic update\n"
        "                modification: add new tip from clipping\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )

    # Run pr done
    result = runner.invoke(
        cli_main,
        ["pr", "done", pr_id, "--root", str(root), "-m", "approved"],
    )
    assert result.exit_code == 0, result.output
    assert "synthesized:" in result.output
    assert "alpha.md" in result.output

    # Clipping frontmatter now has synthesized_at + synthesized_into
    text = clip.read_text(encoding="utf-8")
    assert "synthesized_at:" in text
    assert "public knowledge base/topic/tech/ai/claude-code.md" in text

    # Reload + check schema is right
    reloaded = load_clipping(clip)
    assert reloaded is not None
    assert reloaded.is_synthesized is True
    assert reloaded.synthesized_into == [
        "public knowledge base/topic/tech/ai/claude-code.md",
    ]


def test_pr_done_reject_does_not_mark_clipping_synthesized(tmp_path: Path) -> None:
    root = _make_personalos_root(tmp_path)
    _write_kb_topic(root, "tech/ai/claude-code.md")
    clip = _write_clipping(root, "alpha", title="A")

    runner = CliRunner()
    r1 = runner.invoke(cli_main, ["synthesize-clipping", "alpha.md", "--root", str(root)])
    assert r1.exit_code == 0, r1.output

    inbox_items = list((root / "system" / "inbox").glob("*.md"))
    inbox_rel = inbox_items[0].relative_to(root).as_posix()

    pr_id = "20260507-100100-synthesize-alpha"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    (pr_dir / "proposal.md").write_text(
        "---\n"
        "kind: pr\n"
        "type: web-clipping-synthesize\n"
        "status: pending\n"
        "inbox_sources:\n"
        f"  - {inbox_rel}\n"
        "items:\n"
        "  - id: '1'\n"
        "    monitor_info: x\n"
        "    disposition: APPLY\n"
        "    rationale: x\n"
        "    propagation:\n"
        "      - branch: a\n"
        "        node:\n"
        "          path: public knowledge base/topic/tech/ai/claude-code.md\n"
        "          label: kb topic update\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )

    result = runner.invoke(
        cli_main,
        ["pr", "done", pr_id, "--root", str(root), "--reject", "-m", "no"],
    )
    assert result.exit_code == 0, result.output
    # No synthesized line on reject
    assert "synthesized:" not in result.output
    # Clipping frontmatter unchanged (no synthesized_at)
    text = clip.read_text(encoding="utf-8")
    assert "synthesized_at" not in text


# ---------- 6. headline e2e ----------


def test_e2e_clip_monitor_synthesize_approve_marks_clipping(
    tmp_path: Path, isolated_home: Path
) -> None:
    """Full v0.6 acceptance loop:

      1. Drop a clipping under capture/web clipping/.
      2. `forge monitor` → reports pending synthesize + suggests command.
      3. `forge synthesize-clipping <file>` → creates capture + inbox.
      4. (Hand-craft a filled proposal that points at a KB topic.)
      5. `forge pr done` → KB topic paths are recorded in the clipping
         frontmatter as `synthesized_into`.
      6. `forge monitor` again → no longer reports the clipping.
      7. The clipping FILE itself was never deleted (lifecycle: archive,
         not delete).
    """
    root = _make_personalos_root(tmp_path)
    _write_kb_topic(root, "tech/ai/claude-code.md", body="# claude-code\n\n- existing fact\n")
    clip = _write_clipping(
        root, "thread-by-bcherny",
        title="Thread by @bcherny",
        source_url="https://x.com/bcherny/status/1",
        body="key tip: use Auto mode for long-running tasks.",
    )

    runner = CliRunner()

    # 2. monitor reports
    m1 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert m1.exit_code == 0, m1.output
    assert "status: attention" in m1.output
    assert "web-clipping pending synthesize: 1" in m1.output

    # 3. synthesize-clipping
    s = runner.invoke(
        cli_main,
        ["synthesize-clipping", "thread-by-bcherny.md", "--root", str(root)],
    )
    assert s.exit_code == 0, s.output

    inbox_items = list((root / "system" / "inbox").glob("*.md"))
    assert len(inbox_items) == 1
    inbox_rel = inbox_items[0].relative_to(root).as_posix()

    # 4. simulate filled proposal
    pr_id = "20260507-110000-synthesize-bcherny"
    pr_dir = root / "system" / "pr" / pr_id
    pr_dir.mkdir(parents=True)
    (pr_dir / "proposal.md").write_text(
        "---\n"
        "kind: pr\n"
        "type: web-clipping-synthesize\n"
        "status: pending\n"
        f"inbox_sources:\n  - {inbox_rel}\n"
        "items:\n"
        "  - id: '1'\n"
        "    monitor_info: synth bcherny\n"
        "    disposition: APPLY\n"
        "    rationale: 4.7 tips fit claude-code topic page\n"
        "    propagation:\n"
        "      - branch: a\n"
        "        node:\n"
        "          path: public knowledge base/topic/tech/ai/claude-code.md\n"
        "          label: kb topic update\n"
        "          modification: add Auto-mode tip\n"
        "---\n\nbody\n",
        encoding="utf-8",
    )
    # Simulate the agent ALSO editing the KB topic (proposal would touch it)
    kb_path = root / "public knowledge base" / "topic" / "tech" / "ai" / "claude-code.md"
    kb_path.write_text(
        "# claude-code\n\n- existing fact\n- Auto mode is good for long tasks (from bcherny)\n",
        encoding="utf-8",
    )

    # 5. forge pr done
    done = runner.invoke(
        cli_main,
        ["pr", "done", pr_id, "--root", str(root), "-m", "synthesized into claude-code"],
    )
    assert done.exit_code == 0, done.output
    assert "synthesized:" in done.output
    assert "claude-code.md" in done.output

    # 6. clipping frontmatter stamped
    reloaded = load_clipping(clip)
    assert reloaded is not None
    assert reloaded.is_synthesized is True
    assert "public knowledge base/topic/tech/ai/claude-code.md" in reloaded.synthesized_into

    # Clipping body untouched
    assert "key tip: use Auto mode" in clip.read_text(encoding="utf-8")

    # Clipping file still exists (lifecycle: synthesized, not deleted)
    assert clip.exists()

    # 7. monitor no longer reports the clipping
    m2 = runner.invoke(cli_main, ["monitor", "--root", str(root)])
    assert "web-clipping pending synthesize" not in m2.output
