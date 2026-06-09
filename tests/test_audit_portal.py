from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from forge.audit import build_audit_graph, write_portal
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

    # The three provenance lanes are the backbone of the layered graph view,
    # and source/section lanes group by architectural layer.
    assert "Canonical Source · 按架构层" in html
    assert "Canonical Section · 按架构层" in html
    assert "Runtime（Agent 实际读到）" in html
    assert 'id="hover-card"' in html
    assert "Hover 一屏预览关键内容；Enter/单击固定到右侧完整详情" in html
    assert "preview-compare" in html
    assert "method " in html
    assert "moveKeyboardFocus" in html
    assert "ArrowRight" in html

    # The review-gate framing is part of the product contract, not decoration:
    # the portal exposes gaps and an owner workflow, it does not edit truth.
    assert "Review Gaps" in html
    assert "declared_without_derive_record" in html
    assert "Owner 审核工作流" in html
    for step in ("propose", "review", "approve", "rejected"):
        assert step in html

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
