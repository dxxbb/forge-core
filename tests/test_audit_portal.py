from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from click.testing import CliRunner

from forge.audit import build_audit_diff, build_audit_graph, write_portal
from forge.cli import main
from forge.compiler.loader import load_all_configs, load_sections
from forge.compiler.renderer import render


def test_audit_graph_records_source_section_and_runtime_mapping(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    graph = build_audit_graph(workspace)
    data = graph.to_dict()

    alpha = next(s for s in data["sections"] if s["name"] == "alpha")
    assert alpha["relation_state"] == "derived"
    assert alpha["source_pointers"] == [
        "source/alpha-source.md",
        "workbench/project/demo/onepage.md",
    ]
    source = next(s for s in data["sources"] if s["pointer"] == "source/alpha-source.md")
    assert source["content_excerpt"] == "Alpha canonical source.\n"
    project_source = next(
        s for s in data["sources"] if s["pointer"] == "workbench/project/demo/onepage.md"
    )
    assert project_source["kind"] == "project"

    source_edge = next(
        e
        for e in data["edges"]
        if e["relation"] == "source_to_section" and e["to_id"] == "section:alpha"
    )
    assert source_edge["status"] == "derived"

    runtime_edge = next(
        e
        for e in data["edges"]
        if e["relation"] == "section_to_runtime" and e["from_id"] == "section:alpha"
    )
    assert runtime_edge["status"] == "exact"
    assert runtime_edge["confidence"] == "compiler-exact"
    assert runtime_edge["runtime_range"]["start_line"] is not None
    runtime = next(r for r in data["runtimes"] if r["id"] == runtime_edge["to_id"])
    assert runtime["mirrors"][0]["path"] == "runtime-build/openclaw/demo/AGENTS.md"


def test_audit_graph_marks_missing_source_and_uncertain_section(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    graph = build_audit_graph(workspace).to_dict()

    beta = next(s for s in graph["sections"] if s["name"] == "beta")
    assert beta["relation_state"] == "uncertain"

    missing = next(s for s in graph["sections"] if s["name"] == "missing")
    assert missing["relation_state"] == "declared"

    missing_edge = next(
        e
        for e in graph["edges"]
        if e["relation"] == "source_to_section" and e["to_id"] == "section:missing"
    )
    missing_source = next(s for s in graph["sources"] if s["id"] == missing_edge["from_id"])
    assert missing_source["status"] == "missing"
    assert any(item["type"] == "missing_source_relation" for item in graph["unexplained"])
    assert any(item["type"] == "unresolved_source_pointer" for item in graph["unexplained"])


def test_external_input_nodes_from_capture_frontmatter(tmp_path: Path) -> None:
    root = tmp_path
    sd = root / "context build" / "sections"
    cd = root / "context build" / "config"
    cap = root / "capture" / "codex-memory"
    for d in (sd, cd, cap):
        d.mkdir(parents=True)
    (cap / "task-group.md").write_text(
        "---\nsource: Codex memory\n---\n\n# Task group\n\ndistilled.\n", encoding="utf-8"
    )
    (sd / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled.\n", encoding="utf-8"
    )
    (sd / "kb.md").write_text(
        "---\nname: kb\nupstream:\n  - capture/codex-memory/task-group.md\n---\n\nbody\n",
        encoding="utf-8",
    )
    (cd / "agents.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n  - _preface\n  - kb\n---\n",
        encoding="utf-8",
    )

    graph = build_audit_graph(root).to_dict()
    ext = next(e for e in graph["externals"] if e["label"] == "Codex memory")
    assert ext["kind"] == "external"
    assert ext["file_count"] == 1
    # An import edge connects the external origin to the capture source it landed in.
    imp = next(e for e in graph["edges"] if e["relation"] == "external_to_source")
    assert imp["from_id"] == ext["id"]
    assert imp["status"] == "imported"


def test_audit_graph_extracts_memory_import_workbench(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    capture = workspace / "capture" / "import" / "20260609-212343" / "codex-memory-history.md"
    capture.parent.mkdir(parents=True)
    capture.write_text(
        "# Imported codex memory\n\npreamble line\n\n"
        "## anchor-geo-market-viability\n\nGEO evidence line one.\nGEO evidence line two.\n",
        encoding="utf-8",
    )
    workbench = workspace / "system" / "pr" / "20260609-212428-memory-import" / "workbench.md"
    workbench.parent.mkdir(parents=True)
    workbench.write_text(
        "---\n"
        "kind: memory-import-workbench\n"
        "status: batch-A-user-review-required\n"
        "workbench_id: 20260609-212428-memory-import\n"
        "inbox_sources:\n"
        "  - system/inbox/20260609-212343-import-context.md\n"
        "capture_sources:\n"
        "  - capture/import/20260609-212343/codex-memory-history.md\n"
        "current_batch: A\n"
        "final_pr_ready: false\n"
        "---\n\n"
        "# Memory import workbench\n\n"
        "## Step 1: Information Items\n\n"
        "| id | item | initial domain | batch | status |\n"
        "|---:|---|---|---|---|\n"
        "| 01 | forge-core audit portal design | forge workflow | A | triaged-awaiting-user |\n"
        "| 02 | spare untriaged item | misc | B | untriaged |\n\n"
        "## Batch A Triage\n\n"
        "### Item 01: forge-core audit portal design\n\n"
        "- source_evidence: `capture/import/20260609-212343/codex-memory-history.md` "
        "lines around `anchor-geo-market-viability`\n"
        "- existing_canonical_sink: workbench/project/demo/onepage.md\n"
        "- canonical_sink_status: missing / stale\n"
        "- proposed_disposition: NEEDS-LIVE-VERIFY, then APPLY\n"
        "- apply_scope: canonical-source\n"
        "- proposed_change: update Forge onepage with Context Audit Portal as the review UI.\n"
        "- proposed_patch_target: workbench/project/demo/onepage.md\n"
        "- proposed_patch_anchor: Demo project source.\n"
        "- proposed_patch_text:\n"
        "  Demo project source.\n"
        "  Context Audit Portal is the review UI.\n"
        "- propagation_chain: forge onepage -> workspace section -> runtime AGENTS.\n"
        "- self_check: do not update repo numbers without fresh test output.\n",
        encoding="utf-8",
    )
    empty_wb = workspace / "system" / "pr" / "20260610-000000-drifted" / "workbench.md"
    empty_wb.parent.mkdir(parents=True)
    empty_wb.write_text(
        "---\nkind: memory-import-workbench\nworkbench_id: 20260610-000000-drifted\n---\n\n"
        "# Items live in a renamed heading the parser does not know\n",
        encoding="utf-8",
    )

    graph = build_audit_graph(workspace).to_dict()
    wb = graph["workbenches"][0]
    item = wb["items"][0]

    assert wb["id"] == "20260609-212428-memory-import"
    assert wb["current_batch"] == "A"
    assert wb["final_pr_ready"] is False
    assert item["id"] == "01"
    assert item["initial_domain"] == "forge workflow"
    assert item["fields"]["proposed_disposition"] == "NEEDS-LIVE-VERIFY, then APPLY"
    assert "Context Audit Portal" in item["fields"]["proposed_change"]

    # Free-text fields are resolved to graph node ids: the ingest-review
    # surface links into the provenance graph instead of dead-ending.
    onepage = next(
        s for s in graph["sources"] if s["pointer"] == "workbench/project/demo/onepage.md"
    )
    linked_ids = {link["node_id"] for link in item["links"]}
    assert onepage["id"] in linked_ids
    assert "runtime:AGENTS" in linked_ids

    # The reviewer judges against the imported corpus itself: source_evidence
    # resolves to an excerpt around the anchor, not just a path.
    evidence = item["evidence"][0]
    assert evidence["found"] is True
    assert evidence["anchor"] == "anchor-geo-market-viability"
    assert "GEO evidence line one." in evidence["excerpt"]
    assert evidence["start_line"] is not None and evidence["start_line"] >= 1

    # The claimed canonical sink is reality-checked against disk.
    sink = item["sinks"][0]
    assert sink["path"] == "workbench/project/demo/onepage.md"
    assert sink["exists"] is True
    assert "Demo project source." in sink["excerpt"]

    # Untriaged items stay in the data but are grouped out of the review flow.
    untriaged = next(i for i in wb["items"] if i["id"] == "02")
    assert untriaged["status"] == "untriaged"
    assert untriaged["fields"] == {}

    # proposed_patch_* resolves to a concrete before -> after diff source:
    # the anchored block as it exists on disk vs the proposed replacement.
    patch = item["patch"]
    assert patch["mode"] == "replace"
    assert patch["anchor_found"] is True
    assert patch["start_line"] == 1
    assert patch["current_text"] == "Demo project source."
    assert "Context Audit Portal is the review UI." in patch["proposed_text"]
    assert untriaged["patch"] is None

    # A workbench that parses to zero items surfaces as a gap, not a blank view.
    assert any(u["type"] == "workbench_parse_empty" for u in graph["unexplained"])
    drift_gap = next(g for g in graph["gaps"] if g["type"] == "workbench_parse_empty")
    assert drift_gap["object"] == "20260610-000000-drifted"
    assert drift_gap["severity"] == "med"

    html_path, _ = write_portal(workspace, tmp_path / "audit")
    html = html_path.read_text(encoding="utf-8")
    assert "Workbench Review" in html
    assert "mode-workbench" in html
    assert "staged memory item" in html
    assert "forge-core audit portal design" in html
    # Bidirectional jump: workbench card -> graph node, node -> workbench card.
    assert "data-graph-goto" in html
    assert "Workbench 关联" in html
    # The card is a decision unit: evidence, change, blast radius, decision.
    assert "证据原文" in html
    assert "GEO evidence line one." in html
    assert "影响链" in html
    assert "wb-decide" in html
    assert "未分诊" in html
    # A concrete patch renders as before -> after, not prose.
    assert "before → after" in html
    # Workbench mode must actually hide the graph lanes.
    assert ".lanes[hidden]" in html


def test_gap_audits_and_extraction_classification_live_in_graph_data(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    (workspace / "source" / "gamma-source.md").write_text(
        "intro line.\n\nGamma canonical line one.\nGamma line two longer.\n",
        encoding="utf-8",
    )
    (workspace / "context build" / "sections" / "gamma.md").write_text(
        "---\nname: gamma\ntype: test\nupstream:\n  - source/gamma-source.md\n---\n\n"
        "Gamma canonical line one.\nGamma line two longer.\n",
        encoding="utf-8",
    )

    graph = build_audit_graph(workspace).to_dict()

    # Extraction classification is computed at build time and carried on the edge.
    gamma_edge = next(
        e
        for e in graph["edges"]
        if e["relation"] == "source_to_section" and e["to_id"] == "section:gamma"
    )
    assert gamma_edge["extraction"]["kind"] == "verbatim"
    alpha_source = next(s for s in graph["sources"] if s["pointer"] == "source/alpha-source.md")
    alpha_edge = next(
        e
        for e in graph["edges"]
        if e["relation"] == "source_to_section"
        and e["to_id"] == "section:alpha"
        and e["from_id"] == alpha_source["id"]
    )
    assert alpha_edge["extraction"]["kind"] == "paraphrase"

    # Gaps are severity-ranked with stable, content-derived ids.
    gaps = graph["gaps"]
    severities = [g["severity"] for g in gaps]
    assert severities == sorted(severities, key={"high": 0, "med": 1, "low": 2}.get)
    gamma_gap = next(g for g in gaps if g["type"] == "declared_without_derive_record")
    assert gamma_gap["object"] == "gamma"
    assert gamma_gap["target_id"] == "section:gamma"
    rebuilt = build_audit_graph(workspace).to_dict()
    assert [g["id"] for g in rebuilt["gaps"]] == [g["id"] for g in gaps]


def test_portal_has_external_import_edge_inspector_copy(tmp_path: Path) -> None:
    root = tmp_path
    sd = root / "context build" / "sections"
    cd = root / "context build" / "config"
    cap = root / "capture" / "codex-memory"
    for d in (sd, cd, cap):
        d.mkdir(parents=True)
    (cap / "task-group.md").write_text(
        "---\nsource: Codex memory\n---\n\n# Task group\n\ndistilled.\n", encoding="utf-8"
    )
    (sd / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled.\n", encoding="utf-8"
    )
    (sd / "kb.md").write_text(
        "---\nname: kb\nupstream:\n  - capture/codex-memory/task-group.md\n---\n\nbody\n",
        encoding="utf-8",
    )
    (cd / "agents.md").write_text(
        "---\nname: AGENTS\ntarget: agents-md\nsections:\n  - _preface\n  - kb\n---\n",
        encoding="utf-8",
    )

    html_path, _ = write_portal(root, tmp_path / "audit")
    html = html_path.read_text(encoding="utf-8")

    assert "External Input → Capture" in html
    assert "Portal 不直接读取外部语料原文" in html
    assert "导入产物（Capture）" in html


def test_audit_diff_includes_unlinked_review_file_changes(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    clipping = workspace / "capture" / "web clipping" / "codex-note.md"
    clipping.parent.mkdir(parents=True)
    clipping.write_text(
        "---\nsource: web clipping\n---\n\n# Codex note\n\nclipped input\n",
        encoding="utf-8",
    )
    kb = workspace / "public knowledge base" / "topic" / "tech" / "ai" / "codex.md"
    kb.parent.mkdir(parents=True)
    kb.write_text(
        "---\nsources:\n  - capture/web clipping/codex-note.md\n---\n\n# Codex\n\nold\n",
        encoding="utf-8",
    )
    _git(workspace, "init")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "base")

    kb.write_text(
        "---\nsources:\n  - capture/web clipping/codex-note.md\n---\n\n# Codex\n\nnew\n",
        encoding="utf-8",
    )

    graph = build_audit_diff(workspace, "HEAD")
    source = next(s for s in graph["sources"] if s["pointer"] == "public knowledge base/topic/tech/ai/codex.md")
    assert source["kind"] == "unlinked-change"
    assert source["change"] == "modified"
    assert source["prev_content"].endswith("# Codex\n\nold\n")
    capture = next(s for s in graph["sources"] if s["pointer"] == "capture/web clipping/codex-note.md")
    assert capture["change"] == "unchanged"
    edge = next(e for e in graph["edges"] if e["relation"] == "input_to_source")
    assert edge["from_id"] == capture["id"]
    assert edge["to_id"] == source["id"]
    assert graph["diff"]["modified"] >= 1


def test_wrapper_section_is_not_flagged_as_missing_source(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    graph = build_audit_graph(workspace).to_dict()

    preface = next(s for s in graph["sections"] if s["name"] == "_preface")
    assert preface["type"] == "wrapper"
    # A wrapper is compiled boilerplate with no upstream source by design, so it
    # must not be reported as a missing-source gap (that would be a false positive).
    assert preface["relation_state"] == "wrapper"
    assert not any(
        item.get("section") == "_preface"
        and item["type"] == "missing_source_relation"
        for item in graph["unexplained"]
    )
    # A non-wrapper section without a pointer is still flagged.
    assert any(
        item.get("section") == "beta" and item["type"] == "missing_source_relation"
        for item in graph["unexplained"]
    )


def test_audit_graph_derives_architectural_layers(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    graph = build_audit_graph(workspace).to_dict()

    # In-workspace pointers group by their top-level directory.
    alpha_src = next(s for s in graph["sources"] if s["pointer"] == "source/alpha-source.md")
    assert alpha_src["layer"] == "source"
    onepage = next(
        s for s in graph["sources"] if s["pointer"] == "workbench/project/demo/onepage.md"
    )
    assert onepage["layer"] == "workbench"

    # A section inherits the layer of the canonical source it draws from.
    alpha = next(s for s in graph["sections"] if s["name"] == "alpha")
    assert alpha["layer"] == "source"
    # A wrapper / source-less section falls back to the core layer.
    preface = next(s for s in graph["sections"] if s["name"] == "_preface")
    assert preface["layer"] == "core"


def test_layer_for_pointer_names_cross_repo_projects() -> None:
    from forge.audit.graph import _layer_for_pointer

    root = Path("/work/project-alpha")
    cross = "/Users/dev/workspace/projects/project-beta/foundry/current-state.md"
    assert _layer_for_pointer(root, cross) == "project-beta"
    stray = "/etc/somewhere/file.md"
    assert _layer_for_pointer(root, stray) == "external"


def _git_init_commit(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=a@b.c", "-c", "user.name=t", "commit", "-qm", "base"],
        cwd=root,
        check=True,
    )


def test_audit_diff_detects_modified_section_and_runtime(tmp_path: Path) -> None:
    from forge.audit.diff import build_audit_diff

    ws = _audit_workspace(tmp_path)
    _git_init_commit(ws)
    alpha = ws / "context build" / "sections" / "alpha.md"
    alpha.write_text(
        alpha.read_text(encoding="utf-8").replace("Alpha body.", "Alpha body, revised."),
        encoding="utf-8",
    )

    g = build_audit_diff(ws)
    assert g["diff"]["available"] is True
    assert g["diff"]["modified"] >= 1

    a = next(s for s in g["sections"] if s["name"] == "alpha")
    assert a["change"] == "modified"
    assert "Alpha body." in a["prev_content"]
    # The recompiled runtime is flagged too — that is the blast radius.
    assert any(r["change"] == "modified" for r in g["runtimes"])
    # An untouched section stays unchanged.
    beta = next(s for s in g["sections"] if s["name"] == "beta")
    assert beta["change"] == "unchanged"


def test_audit_diff_without_git_is_unavailable(tmp_path: Path) -> None:
    from forge.audit.diff import build_audit_diff

    ws = _audit_workspace(tmp_path)
    g = build_audit_diff(ws)
    assert g["diff"]["available"] is False
    assert all(s["change"] == "unchanged" for s in g["sections"])


def test_write_portal_outputs_html_and_json(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    html_path, json_path = write_portal(workspace, tmp_path / "audit-out")

    assert html_path.exists()
    assert json_path.exists()
    html = html_path.read_text(encoding="utf-8")

    # It is a single self-contained HTML document.
    assert html.lstrip().startswith("<!doctype html>")
    assert "Forge Context Audit" in html

    # The provenance lanes are dynamic: capture/clipping inputs sit to the
    # left of canonical sources instead of being forced into a fixed 3-column
    # layout.
    assert "Capture / Clipping · 输入" in html
    assert "Canonical Source · 按架构层" in html
    assert "Canonical Section · 按架构层" in html
    assert "Runtime（Agent 实际读到）" in html
    assert "--lane-count" in html
    assert "diff hunk" in html
    assert "已定位到第 " in html
    assert "input_to_source" in html
    assert 'id="graph-empty"' in html
    assert "refreshFilteredLanes" in html
    assert 'id="hover-card"' in html
    assert "Hover 一屏预览关键内容；Enter/单击固定到右侧完整详情" in html
    assert "preview-compare" in html
    assert "method " in html
    assert "moveKeyboardFocus" in html
    assert "ArrowRight" in html

    # The review-gate framing is part of the product contract, not decoration:
    # the portal exposes gaps and an owner workflow, it does not edit truth.
    assert "Review Gaps" in html
    assert "Owner 审核工作流" in html
    for step in ("propose", "review", "approve", "rejected"):
        assert step in html
    # Review is a linear task: the portal walks changes/gaps as a queue.
    assert "queue-bar" in html
    assert "queueStep" in html

    # Provenance content rides in the embedded JSON, not in escaped markup, so
    # source/runtime text appears verbatim (not double-escaped).
    assert "runtime-build/openclaw/demo/AGENTS.md" in html
    assert "Alpha canonical source." in html
    assert "> quoted runtime marker" in html
    assert "&gt; quoted runtime marker" not in html

    embedded = re.search(
        r'<script id="audit-data" type="application/json">(.*?)</script>',
        html,
        flags=re.S,
    )
    assert embedded is not None
    parsed = json.loads(embedded.group(1))
    assert parsed["schema_version"] == "forge.audit.v1"
    assert {n["name"] for n in parsed["sections"]} >= {"alpha", "beta", "missing"}
    # Gaps ride in the data with stable ids, not synthesized per page load.
    assert parsed["gaps"]
    assert all(g["id"].startswith("GAP-") for g in parsed["gaps"])
    assert {g["type"] for g in parsed["gaps"]} >= {
        "missing_source_relation",
        "unresolved_source_pointer",
    }
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "forge.audit.v1"


def test_audit_portal_cli(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "audit",
            "portal",
            "--root",
            str(workspace),
            "--output-dir",
            str(tmp_path / "cli-out"),
        ],
    )

    assert result.exit_code == 0
    assert "context-audit-portal.html" in result.output
    assert (tmp_path / "cli-out" / "audit-graph.json").exists()


def test_audit_serve_cli_is_exposed() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["audit", "serve", "--help"])
    assert result.exit_code == 0
    assert "Serve the audit portal as a local web UI" in result.output


def _audit_workspace(root: Path) -> Path:
    section_dir = root / "context build" / "sections"
    config_dir = root / "context build" / "config"
    source_dir = root / "source"
    project_dir = root / "workbench" / "project" / "demo"
    section_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True)
    source_dir.mkdir()
    project_dir.mkdir(parents=True)

    (source_dir / "alpha-source.md").write_text("Alpha canonical source.\n", encoding="utf-8")
    (project_dir / "onepage.md").write_text("Demo project source.\n", encoding="utf-8")
    (section_dir / "_preface.md").write_text(
        "---\nname: _preface\ntype: wrapper\n---\n\nCompiled context.\n",
        encoding="utf-8",
    )
    (section_dir / "alpha.md").write_text(
        "---\n"
        "name: alpha\n"
        "type: test\n"
        "kind: derived\n"
        "upstream:\n"
        "  - source/alpha-source.md\n"
        "  - workbench/project/demo/onepage.md\n"
        "generated_by: test\n"
        "---\n\n"
        "# Alpha\n\nAlpha body.\n\n> quoted runtime marker\n",
        encoding="utf-8",
    )
    (section_dir / "beta.md").write_text(
        "---\nname: beta\ntype: test\n---\n\nBeta body.\n",
        encoding="utf-8",
    )
    (section_dir / "missing.md").write_text(
        "---\nname: missing\ntype: test\nupstream:\n  - source/missing.md\n---\n\nMissing source body.\n",
        encoding="utf-8",
    )
    (config_dir / "agents-md.md").write_text(
        "---\n"
        "name: AGENTS\n"
        "target: agents-md\n"
        "sections:\n"
        "  - _preface\n"
        "  - alpha\n"
        "  - beta\n"
        "  - missing\n"
        "demote_section_headings: true\n"
        "---\n",
        encoding="utf-8",
    )
    mirror_dir = root / "runtime-build" / "openclaw" / "demo"
    mirror_dir.mkdir(parents=True)
    sections = load_sections(root)
    config = load_all_configs(root)["AGENTS"]
    (mirror_dir / "AGENTS.md").write_text(render(sections, config), encoding="utf-8")
    return root


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    if args and args[0] == "init":
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Test User"], check=True)
    else:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result
