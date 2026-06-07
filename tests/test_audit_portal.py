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


def test_write_portal_outputs_html_and_json(tmp_path: Path) -> None:
    workspace = _audit_workspace(tmp_path)
    html_path, json_path = write_portal(workspace, tmp_path / "audit-out")

    assert html_path.exists()
    assert json_path.exists()
    html = html_path.read_text(encoding="utf-8")
    assert "Forge Context Audit Portal" in html
    assert "Runtime Context 审计地图" in html
    assert "Runtime Audit Overview" in html
    assert "trace-map" in html
    assert "trace-lanes" in html
    assert "trace-board" in html
    assert "trace-row" in html
    assert "trace-card" in html
    assert "trace-section-node" in html
    assert "trace-runtime-card" in html
    assert "Source / Capture / Memory / Project" in html
    assert "Review Gaps" in html
    assert "gap-grid" in html
    assert "gap-table" in html
    assert "declared_without_derive_record" in html
    assert "mapping-table" in html
    assert "line-preview" in html
    assert "section-flow" in html
    assert "Runtime Context Tree" in html
    assert "Owner 审核工作流" in html
    assert "propose" in html
    assert "review" in html
    assert "approve" in html
    assert "rejected" in html
    assert "layout" in html
    assert "nav-tree" in html
    assert "nav-actions" in html
    assert "seg-btn" in html
    assert "portal-page" in html
    assert "runtime-page" in html
    assert "section-page" in html
    assert "source-page" in html
    assert "file-card" in html
    assert "showPageFromHash" in html
    assert "text-overflow: ellipsis" in html
    assert "全部展开" in html
    assert "全部折叠" in html
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
