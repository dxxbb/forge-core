"""Static web UI for inspecting forge audit graphs."""

from __future__ import annotations

import json
from pathlib import Path

from forge.audit.graph import AuditGraph, build_audit_graph


def write_portal(root: Path, output_dir: Path | None = None) -> tuple[Path, Path]:
    """Write ``context-audit-portal.html`` and ``audit-graph.json`` for root."""
    root = Path(root).resolve()
    graph = build_audit_graph(root)
    out_dir = output_dir or (root / ".forge" / "audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "audit-graph.json"
    html_path = out_dir / "context-audit-portal.html"
    payload = graph.to_dict()
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_path.write_text(_render_html(graph), encoding="utf-8")
    return html_path, json_path


def _render_html(graph: AuditGraph) -> str:
    data = json.dumps(graph.to_dict(), ensure_ascii=False)
    safe_data = data.replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__AUDIT_DATA__", safe_data)


_HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Forge Context Audit Portal</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #e4e2dc;
      --panel: #f1efea;
      --panel-2: #dcdad2;
      --text: #2c2a26;
      --muted: #76726a;
      --line: #cfccc4;
      --accent: #5f6470;
      --card-bg: #f1efea;
      --soft-bg: #eae8e2;
      --exact: #0f766e;
      --derived: #7c3aed;
      --declared: #2563eb;
      --uncertain: #b45309;
      --missing: #b91c1c;
      --side-bg: #161a1f;
      --side-panel: #20262d;
      --side-line: #313a45;
      --side-text: #f4f1ea;
      --side-muted: #a8b0bb;
      --radius: 8px;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", sans-serif;
    }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { margin: 0; background: var(--bg); color: var(--text); letter-spacing: 0; }
    a { color: inherit; }
    .layout {
      min-height: 100vh;
      display: grid;
      grid-template-columns: clamp(300px, 21vw, 340px) minmax(0, 1fr);
    }
    aside {
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      border-right: 1px solid var(--side-line);
      background: var(--side-bg);
      color: var(--side-text);
      padding: 22px 18px 24px;
    }
    main { min-width: 0; padding: 28px 34px 56px; }
    .brand h1 { margin: 0 0 8px; font-size: 24px; line-height: 1.2; }
    .brand p { margin: 0 0 18px; color: var(--side-muted); line-height: 1.55; }
    .search {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: var(--radius);
      padding: 11px 12px;
      font-size: 15px;
      margin-bottom: 10px;
      background: var(--side-panel);
      color: var(--side-text);
      border-color: var(--side-line);
    }
    .search::placeholder { color: var(--side-muted); }
    .nav-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
    .nav-actions button, .seg-btn {
      border: 1px solid var(--side-line);
      border-radius: var(--radius);
      background: var(--side-panel);
      color: var(--side-muted);
      cursor: pointer;
      font-size: 12px;
      padding: 7px 8px;
    }
    .nav-actions button:hover, .seg-btn:hover { border-color: var(--side-text); color: var(--side-text); }
    .perspective {
      margin-bottom: 16px;
      padding: 10px;
      border: 1px solid var(--side-line);
      border-radius: var(--radius);
      background: #11161b;
    }
    .seg {
      display: flex;
      gap: 4px;
      background: var(--side-panel);
      border: 1px solid var(--side-line);
      border-radius: var(--radius);
      padding: 3px;
    }
    .seg-btn { flex: 1 1 auto; border: 0; border-radius: 6px; background: transparent; white-space: nowrap; }
    .seg-btn.active { background: #e7e0d2; color: #171b20; }
    .perspective-status { margin: 8px 0 0; font-size: 12px; line-height: 1.5; color: var(--side-muted); }
    .nav-tree { display: grid; gap: 7px; }
    .nav-branch { border-left: 1px solid var(--side-line); padding-left: 9px; }
    .nav-row { display: grid; grid-template-columns: 22px minmax(0, 1fr); gap: 4px; align-items: center; }
    .nav-toggle {
      width: 22px; height: 22px; border: 1px solid var(--line); border-radius: 6px;
      background: var(--side-panel); color: var(--side-muted); cursor: pointer;
      border-color: var(--side-line);
    }
    .nav-branch.collapsed > .nav-children { display: none; }
    .nav-branch.collapsed > .nav-row .nav-toggle::after { content: "+"; }
    .nav-branch:not(.collapsed) > .nav-row .nav-toggle::after { content: "-"; }
    .nav-children { display: grid; gap: 4px; margin: 4px 0 8px 22px; }
    .nav-tree a {
      display: block;
      min-width: 0;
      padding: 5px 7px;
      border-radius: 6px;
      text-decoration: none;
      color: var(--side-muted);
      font-size: 13px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .nav-tree a:hover, .nav-tree a.active { background: var(--side-panel); color: var(--side-text); }
    .nav-tree small { color: var(--side-muted); }
    .hint { color: var(--muted); font-size: 12px; line-height: 1.5; margin-top: 18px; }
    aside .hint { color: var(--side-muted); }
    .hero { border-bottom: 1px solid var(--line); padding-bottom: 22px; margin-bottom: 18px; }
    .hero h2 { margin: 0 0 8px; font-size: 30px; line-height: 1.15; }
    .hero p { color: var(--muted); margin: 0 0 18px; line-height: 1.55; max-width: 920px; overflow-wrap: anywhere; }
    .stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
    .stat { border: 1px solid var(--line); border-radius: var(--radius); background: var(--panel); padding: 12px; }
    .stat strong { display: block; font-size: 22px; line-height: 1.1; }
    .stat span { color: var(--muted); font-size: 12px; }
    .trace-map {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      padding: 16px;
      margin-bottom: 16px;
    }
    .trace-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .trace-head h4 { margin: 0; font-size: 16px; }
    .trace-lanes { display: grid; gap: 10px; }
    .trace-board {
      display: grid;
      gap: 9px;
      margin-top: 10px;
    }
    .trace-row {
      display: grid;
      grid-template-columns: minmax(210px, 1.05fr) 34px minmax(230px, 0.95fr) 34px minmax(230px, 1.05fr);
      gap: 8px;
      align-items: stretch;
    }
    .trace-stack { display: grid; gap: 6px; min-width: 0; }
    .trace-card, .trace-section-node, .trace-runtime-card {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--soft-bg);
      padding: 9px 10px;
      min-width: 0;
      color: inherit;
      text-decoration: none;
    }
    .trace-card {
      border-left: 4px solid var(--declared);
    }
    .trace-card.status-derived { border-left-color: var(--derived); }
    .trace-card.status-declared { border-left-color: var(--declared); }
    .trace-card.status-uncertain { border-left-color: var(--uncertain); border-style: dashed; }
    .trace-card.status-missing { border-left-color: var(--missing); border-style: dashed; }
    .trace-section-node {
      display: grid;
      gap: 5px;
      border-left: 4px solid var(--accent);
      background: #f8f6f0;
    }
    .trace-runtime-card {
      border-left: 4px solid var(--exact);
    }
    .trace-runtime-card.status-uncertain { border-left-color: var(--uncertain); border-style: dashed; }
    .trace-card strong, .trace-section-node strong, .trace-runtime-card strong {
      display: block;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .trace-card em, .trace-section-node em, .trace-runtime-card em {
      display: block;
      font-style: normal;
      color: var(--muted);
      font-size: 11.5px;
      line-height: 1.45;
      overflow-wrap: anywhere;
    }
    .trace-connector {
      display: grid;
      place-items: center;
      color: var(--muted);
      font-weight: 700;
    }
    .trace-connector.status-exact { color: var(--exact); }
    .trace-connector.status-derived { color: var(--derived); }
    .trace-connector.status-declared { color: var(--declared); }
    .trace-connector.status-uncertain { color: var(--uncertain); }
    .lane-title {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
      letter-spacing: 0;
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 12px;
    }
    .legend .badge { color: #fff; }
    .portal-page { display: none; }
    .portal-page.active { display: block; }
    .portal-page:not(.active) { display: none; }
    .page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 14px; }
    .page-head h3 { margin: 0; font-size: 24px; line-height: 1.2; }
    .page-sub { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; margin-top: 4px; }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      color: #fff;
      font-size: 12px;
      line-height: 18px;
      vertical-align: baseline;
      white-space: nowrap;
    }
    .exact { background: var(--exact); }
    .derived { background: var(--derived); }
    .declared { background: var(--declared); }
    .uncertain { background: var(--uncertain); }
    .missing { background: var(--missing); }
    .section-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; align-items: start; }
    .section-flow { display: grid; grid-template-columns: minmax(0, 1fr) 32px minmax(0, 1fr) 32px minmax(0, 1fr); gap: 10px; align-items: start; }
    .flow-col { min-width: 0; }
    .flow-arrow {
      display: grid;
      place-items: center;
      min-height: 220px;
      color: var(--muted);
      font-size: 22px;
      font-weight: 700;
    }
    .file-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .mapping-table, .gap-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12.5px;
      margin-top: 8px;
    }
    .mapping-table th, .mapping-table td,
    .gap-table th, .gap-table td {
      border: 1px solid var(--line);
      padding: 8px 9px;
      text-align: left;
      vertical-align: top;
      line-height: 1.45;
    }
    .mapping-table th, .gap-table th {
      background: var(--panel-2);
      color: var(--text);
      font-weight: 700;
    }
    .mapping-table td, .gap-table td { overflow-wrap: anywhere; }
    .file-card, .panel {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      padding: 14px;
      min-width: 0;
    }
    .file-card h4, .panel h4 { margin: 0 0 8px; font-size: 15px; }
    .meta-grid { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 6px 10px; margin: 8px 0; font-size: 13px; }
    .meta-k { color: var(--muted); }
    .meta-v { overflow-wrap: anywhere; }
    pre {
      margin: 8px 0 0;
      max-height: 48vh;
      overflow: auto;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      background: var(--soft-bg);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
    }
    .line-preview {
      white-space: pre;
      overflow-wrap: normal;
      tab-size: 2;
    }
    .line-preview code { white-space: pre; }
    .unexplained { border: 1px solid #f2c98b; background: #fff8eb; }
    .gap-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
    .workflow {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      align-items: stretch;
      margin-top: 14px;
    }
    .workflow-step {
      border: 1px solid var(--line);
      border-radius: var(--radius);
      background: var(--panel);
      padding: 12px;
    }
    .workflow-step strong { display: block; margin-bottom: 4px; }
    .workflow-step span { color: var(--muted); font-size: 12px; }
    .review-note {
      border: 1px solid #bed3ff;
      background: #eef4ff;
      border-radius: var(--radius);
      padding: 12px;
      margin-top: 12px;
      color: #26334f;
    }
    .empty-state { display: none; color: var(--muted); }
    @media (max-width: 980px) {
      .layout { grid-template-columns: 1fr; }
      aside { position: static; height: auto; border-right: 0; border-bottom: 1px solid var(--line); }
      .section-grid, .section-flow, .file-grid, .stats, .trace-lanes, .trace-row, .gap-grid, .workflow { grid-template-columns: 1fr; }
      .trace-connector, .flow-arrow { min-height: 28px; transform: rotate(90deg); }
    }
  </style>
</head>
<body>
  <div class="layout">
    <aside>
      <div class="brand">
        <h1>Forge Context Audit Portal</h1>
        <p>从 runtime 入口反查 section、source、derive 状态和无法解释的关系。</p>
      </div>
      <input class="search" id="search" type="search" placeholder="搜索 section、runtime、source（按 / 聚焦）" />
      <div class="nav-actions">
        <button type="button" id="expand-all">全部展开</button>
        <button type="button" id="collapse-all">全部折叠</button>
      </div>
      <div class="perspective">
        <div class="seg" role="group" aria-label="审计视角">
          <button type="button" class="seg-btn active" data-perspective="all">全部</button>
          <button type="button" class="seg-btn" data-perspective="runtime">Runtime</button>
          <button type="button" class="seg-btn" data-perspective="relations">关系</button>
          <button type="button" class="seg-btn" data-perspective="unexplained">缺口</button>
        </div>
        <p class="perspective-status" id="perspective-status"></p>
      </div>
      <nav id="nav" class="nav-tree"></nav>
      <p class="hint">Portal 不是事实源。它只展示 forge compiler 的 exact mapping、section frontmatter 声明和显式 uncertain。</p>
    </aside>
    <main>
      <section class="hero">
        <h2>Runtime Context 审计地图</h2>
        <p id="workspace"></p>
        <div class="stats" id="stats"></div>
      </section>
      <p class="empty-state" id="empty-state">没有匹配的审计节点。换一个关键词或清空搜索。</p>
      <div id="pages"></div>
    </main>
  </div>
  <script id="audit-data" type="application/json">__AUDIT_DATA__</script>
  <script>
    const graph = JSON.parse(document.getElementById('audit-data').textContent);
    const byId = new Map();
    [...graph.sources, ...graph.sections, ...graph.runtimes].forEach(n => byId.set(n.id, n));
    const pagesRoot = document.getElementById('pages');
    const navRoot = document.getElementById('nav');
    const emptyState = document.getElementById('empty-state');
    const input = document.getElementById('search');
    let perspective = 'all';
    const escapeHtml = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const badge = (status) => `<span class="badge ${escapeHtml(status)}">${escapeHtml(status)}</span>`;
    const pos = (p) => {
      if (!p) return 'none';
      const lines = p.start_line ? `:${p.start_line}${p.end_line && p.end_line !== p.start_line ? '-' + p.end_line : ''}` : '';
      return `${p.path}${lines}${p.exists === false ? ' (missing)' : ''}`;
    };
    const lineSlice = (text, start, end) => {
      if (!start || !end) return '';
      return String(text || '').split('\n').slice(start - 1, end).join('\n');
    };
    const statusClass = (status) => 'status-' + String(status || 'unknown').replace(/[^a-z0-9_-]/gi, '-');
    const rangeText = (p) => {
      if (!p || !p.start_line) return 'no exact line range';
      return `${p.start_line}${p.end_line && p.end_line !== p.start_line ? '-' + p.end_line : ''}`;
    };
    const numbered = (text, startLine = 1) => String(text || '').split('\n').map((line, idx) => {
      const no = String(startLine + idx).padStart(4, ' ');
      return `${no}  ${line}`;
    }).join('\n');
    const pageId = (id) => 'page-' + id.replace(/[^a-zA-Z0-9_-]+/g, '-');
    const sourceEdgesFor = (section) => graph.edges.filter(e => e.to_id === section.id && e.relation === 'source_to_section');
    const runtimeEdgesFor = (section) => graph.edges.filter(e => e.from_id === section.id && e.relation === 'section_to_runtime');
    const runtimeEdgesForRuntime = (runtime) => graph.edges.filter(e => e.to_id === runtime.id && e.relation === 'section_to_runtime');
    const sectionSortKey = (section) => {
      const ranges = runtimeEdgesFor(section).map(e => e.runtime_range?.start_line).filter(Boolean);
      return ranges.length ? Math.min(...ranges) : 999999;
    };
    const orderedSections = () => [...graph.sections].sort((a, b) => sectionSortKey(a) - sectionSortKey(b) || a.name.localeCompare(b.name));
    const sourceKindLabel = (kind) => ({
      source: 'Source',
      capture: 'Capture',
      memory: 'Memory',
      project: 'Project MD',
    })[kind] || kind || 'Source';
    const sourceStatus = (source, edge) => source?.status === 'missing' ? 'missing' : edge?.status || 'uncertain';
    const compileStatusFor = (section) => {
      const edges = runtimeEdgesFor(section);
      if (!edges.length) return 'uncertain';
      return edges.every(e => e.status === 'exact') ? 'exact' : 'uncertain';
    };

    function branch(title, children, depth = 0, nodeId = title) {
      return `<div class="nav-branch" data-depth="${depth}" data-node-id="${escapeHtml(nodeId)}">
        <div class="nav-row"><button class="nav-toggle" type="button" aria-expanded="true"></button><strong>${escapeHtml(title)}</strong></div>
        <div class="nav-children">${children}</div>
      </div>`;
    }
    function navLink(id, label, sub = '') {
      return `<a href="#${pageId(id)}" data-search="${escapeHtml((label + ' ' + sub).toLowerCase())}">
        <span>${escapeHtml(label)}</span>${sub ? `<small> · ${escapeHtml(sub)}</small>` : ''}
      </a>`;
    }
    function page(id, cls, title, sub, body) {
      return `<section class="portal-page ${cls}" id="${pageId(id)}" data-search="${escapeHtml((title + ' ' + sub + ' ' + body.replace(/<[^>]*>/g, ' ')).toLowerCase())}">
        <div class="page-head"><div><h3>${escapeHtml(title)}</h3><div class="page-sub">${escapeHtml(sub)}</div></div></div>
        ${body}
      </section>`;
    }
    function renderSourceLinksForSection(section, depth) {
      const edges = sourceEdgesFor(section);
      if (!edges.length) return navLink(section.id, '无 source/upstream', 'uncertain');
      return edges.map(e => {
        const source = byId.get(e.from_id);
        return navLink(source.id, source.label, `${sourceKindLabel(source.kind)} · ${e.status}`);
      }).join('');
    }
    function buildOverviewNav() {
      const sourceGroups = ['source', 'capture', 'memory', 'project'].map(kind => {
        const links = graph.sources.filter(s => s.kind === kind).map(s => navLink(s.id, s.label, s.pointer)).join('');
        return links ? branch(sourceKindLabel(kind), links, 1, `source-kind:${kind}`) : '';
      }).join('');
      return [
        branch('Overview', navLink('overview', '审计总览', `${graph.runtimes.length} runtime · ${graph.sections.length} sections · ${graph.unexplained.length} gaps`), 0, 'overview'),
        branch('Runtime MD', graph.runtimes.map(r => navLink(r.id, r.config, `${r.target} · ${r.path}`)).join(''), 0, 'runtime'),
        branch('Sections', orderedSections().map(s => navLink(s.id, s.name, `${s.relation_state} · ${s.type || 'section'}`)).join(''), 0, 'sections'),
        branch('Sources / Capture / Memory / Project', sourceGroups || navLink('overview', '无 source pointer'), 0, 'sources'),
        branch('Unexplained', navLink('issues:overview', '缺口总览', `${graph.unexplained.length} gaps`) + graph.unexplained.map((u, i) => navLink(`issue:${i}`, u.type, u.section || u.config || '')).join(''), 0, 'issues'),
      ].join('');
    }
    function buildRuntimeNav() {
      const runtimeBranches = graph.runtimes.map(r => {
        const sections = runtimeEdgesForRuntime(r).map(e => {
          const section = byId.get(e.from_id);
          return branch(
            `${section.name}`,
            navLink(section.id, 'Section 内容', `${section.relation_state}`) + renderSourceLinksForSection(section, 2),
            1,
            `runtime:${r.id}:${section.id}`,
          );
        }).join('');
        return branch(`${r.config}`, navLink(r.id, 'Agent 实际看到的 Runtime', r.path) + sections, 0, `runtime:${r.id}`);
      }).join('');
      return branch('Runtime Context Tree', navLink('overview', '链路总览', 'Source -> Section -> Runtime') + runtimeBranches, 0, 'runtime-tree');
    }
    function buildRelationNav() {
      const exactRuntime = graph.runtimes.map(r => branch(
        `${r.config} exact mapping`,
        runtimeEdgesForRuntime(r).map(e => {
          const section = byId.get(e.from_id);
          return navLink(section.id, section.name, `${e.status} · lines ${rangeText(e.runtime_range)}`);
        }).join(''),
        1,
        `exact:${r.id}`,
      )).join('');
      const relationGroups = ['derived', 'declared', 'uncertain'].map(status => {
        const links = graph.sections.filter(s => s.relation_state === status).map(s => navLink(s.id, s.name, s.relation_note)).join('');
        return branch(`source -> section: ${status}`, links || navLink('overview', 'none'), 1, `rel:${status}`);
      }).join('');
      return [
        branch('Compiler exact mapping', exactRuntime, 0, 'compiler-exact'),
        branch('Agent declared / derived / uncertain', relationGroups, 0, 'source-relations'),
      ].join('');
    }
    function buildUnexplainedNav() {
      const links = navLink('issues:overview', 'Review Gaps 总览', `${graph.unexplained.length} unresolved`) +
        (graph.unexplained.length ? graph.unexplained.map((u, i) => navLink(`issue:${i}`, u.type, u.section || u.config || '')).join('') : navLink('issues:none', '无缺口'));
      return branch('Unexplained / Review Gaps', links, 0, 'unexplained');
    }
    function buildNav() {
      if (perspective === 'runtime') navRoot.innerHTML = buildRuntimeNav();
      else if (perspective === 'relations') navRoot.innerHTML = buildRelationNav();
      else if (perspective === 'unexplained') navRoot.innerHTML = buildUnexplainedNav();
      else navRoot.innerHTML = buildOverviewNav();
      bindNav();
    }
    function countBy(list, field) {
      return list.reduce((acc, item) => {
        const key = item[field] || 'unknown';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }, {});
    }
    function renderOverviewPage() {
      const sourceKinds = countBy(graph.sources, 'kind');
      const sectionStates = countBy(graph.sections, 'relation_state');
      const edgeStates = countBy(graph.edges, 'status');
      const traceRows = orderedSections().map(section => {
        const sourceEdges = sourceEdgesFor(section);
        const sourceCards = sourceEdges.length ? sourceEdges.map(e => {
          const source = byId.get(e.from_id);
          const state = sourceStatus(source, e);
          return `<a class="trace-card ${statusClass(state)}" href="#${pageId(source.id)}">
            <strong>${escapeHtml(sourceKindLabel(source.kind))}: ${escapeHtml(source.label)}</strong>
            <em>${escapeHtml(source.pointer)}</em>
            ${badge(state)}
          </a>`;
        }).join('') : `<div class="trace-card ${statusClass('uncertain')}">
          <strong>Missing source relation</strong>
          <em>section frontmatter has no source/upstream pointer</em>
          ${badge('uncertain')}
        </div>`;
        const runtimeCards = runtimeEdgesFor(section).map(e => {
          const runtime = byId.get(e.to_id);
          const mirrorCount = (runtime.mirrors || []).length;
          return `<a class="trace-runtime-card ${statusClass(e.status)}" href="#${pageId(runtime.id)}">
            <strong>${escapeHtml(runtime.config)} / ${escapeHtml(runtime.target)}</strong>
            <em>canonical lines ${escapeHtml(rangeText(e.runtime_range))}${mirrorCount ? ` · ${mirrorCount} mirror` : ''}</em>
            ${badge(e.status)}
          </a>`;
        }).join('') || `<div class="trace-runtime-card ${statusClass('uncertain')}"><strong>No runtime mapping</strong>${badge('uncertain')}</div>`;
        return `<div class="trace-row">
          <div class="trace-stack">${sourceCards}</div>
          <div class="trace-connector ${statusClass(section.relation_state)}">-></div>
          <a class="trace-section-node" href="#${pageId(section.id)}">
            <strong>${escapeHtml(section.name)}</strong>
            <em>${escapeHtml(section.type || 'section')} · ${escapeHtml(section.relation_note || '')}</em>
            <span>${badge(section.relation_state)} ${runtimeEdgesFor(section).length} runtime mapping(s)</span>
          </a>
          <div class="trace-connector ${statusClass(compileStatusFor(section))}">-></div>
          <div class="trace-stack">${runtimeCards}</div>
        </div>`;
      }).join('');
      const gapCards = renderGapSummaryCards();
      return page('overview', 'overview-page', 'Runtime Audit Overview', 'source / capture / memory / project -> section -> runtime', `
        <section class="trace-map">
          <div class="trace-head">
            <h4>审计链路总览</h4>
            <span class="page-sub">每一行是一条真实 section lineage，而不是聚合计数</span>
          </div>
          <div class="trace-lanes">
            <div class="trace-row">
              <div class="lane-title">Source / Capture / Memory / Project</div>
              <div></div>
              <div class="lane-title">Canonical Section</div>
              <div></div>
              <div class="lane-title">Runtime MD exact mapping</div>
            </div>
            <div class="trace-board">${traceRows}</div>
          </div>
          <div class="legend">
            ${badge('exact')} ${badge('derived')} ${badge('declared')} ${badge('uncertain')} ${badge('missing')}
          </div>
        </section>
        <section class="panel">
          <h4>Review Gaps</h4>
          <div class="gap-grid">${gapCards}</div>
        </section>
        <section class="panel">
          <h4>数据口径</h4>
          <div class="meta-grid">
            <div class="meta-k">exact</div><div class="meta-v">${edgeStates.exact || 0} compiler-rendered runtime mapping(s)</div>
            <div class="meta-k">derived</div><div class="meta-v">${sectionStates.derived || 0} section(s) with derivation evidence in frontmatter</div>
            <div class="meta-k">declared</div><div class="meta-v">${sectionStates.declared || 0} section(s) with upstream declaration but no exact derive record</div>
            <div class="meta-k">uncertain</div><div class="meta-v">${sectionStates.uncertain || 0} section(s) with missing or unclear source relation</div>
            <div class="meta-k">source kinds</div><div class="meta-v">${Object.entries(sourceKinds).map(([k, v]) => `${sourceKindLabel(k)}=${v}`).join(' · ') || 'none'}</div>
          </div>
        </section>`);
    }
    function renderRuntimePage(r) {
      const mappingRows = runtimeEdgesForRuntime(r).map(e => {
        const s = byId.get(e.from_id);
        const mirrorLines = (r.mirrors || []).map(m => escapeHtml(pos({ path: m.path, start_line: e.runtime_range?.start_line, end_line: e.runtime_range?.end_line, exists: m.exists }))).join('<br>') || 'none';
        return `<tr>
          <td><a href="#${pageId(s.id)}">${escapeHtml(s.name)}</a><br><small>${escapeHtml(s.type || 'section')} · ${badge(s.relation_state)}</small></td>
          <td>${escapeHtml(pos(e.runtime_range))}</td>
          <td>${mirrorLines}</td>
          <td>${escapeHtml(e.evidence)}</td>
          <td>${badge(e.status)}</td>
        </tr>`;
      }).join('');
      return page(r.id, 'runtime-page', r.config, `${r.target} · ${r.path}`, `
        <div class="section-grid">
          <section class="panel">
            <h4>Agent 实际看到的 runtime MD</h4>
            <div class="meta-grid">
              <div class="meta-k">canonical</div><div class="meta-v">${escapeHtml(pos(r.position))}</div>
              <div class="meta-k">mirrors</div><div class="meta-v">${(r.mirrors || []).map(m => escapeHtml(pos(m))).join('<br>') || 'none'}</div>
            </div>
            <pre class="line-preview"><code>${escapeHtml(numbered(r.content, 1))}</code></pre>
          </section>
          <section class="panel">
            <h4>Section -> Runtime exact compile mapping</h4>
            <p class="page-sub">这张表只记录 compiler-rendered section block 在 runtime 文本中的命中位置；source -> section 不在这里伪装成 exact。</p>
            <table class="mapping-table">
              <thead><tr><th>Section</th><th>Canonical 行范围</th><th>Mirror 行范围</th><th>Evidence</th><th>Status</th></tr></thead>
              <tbody>${mappingRows || '<tr><td colspan="5">No runtime section mapping.</td></tr>'}</tbody>
            </table>
          </section>
        </div>`);
    }
    function renderSectionPage(section) {
      const sourceEdges = sourceEdgesFor(section);
      const sourcesHtml = sourceEdges.length ? sourceEdges.map(e => {
        const s = byId.get(e.from_id);
        const preview = s?.content_excerpt ? `<details open><summary>source excerpt</summary><pre class="line-preview"><code>${escapeHtml(numbered(s.content_excerpt, s.position?.start_line || 1))}</code></pre></details>` : '';
        return `<article class="file-card">
          <h4><a href="#${pageId(s.id)}">${escapeHtml(s?.label || s?.pointer || 'source')}</a> ${badge(e.status)}</h4>
          <div class="meta-grid">
            <div class="meta-k">kind</div><div class="meta-v">${escapeHtml(s?.kind || '')} ${s?.status === 'missing' ? badge('missing') : ''}</div>
            <div class="meta-k">pointer</div><div class="meta-v">${escapeHtml(s?.pointer || '')}</div>
            <div class="meta-k">位置</div><div class="meta-v">${escapeHtml(pos(s?.position))}</div>
            <div class="meta-k">evidence</div><div class="meta-v">${escapeHtml(e.evidence)}</div>
          </div>${preview || '<p class="hint">source excerpt not available</p>'}
        </article>`;
      }).join('') : `<article class="file-card">${badge('uncertain')} no source/upstream pointer declared</article>`;
      const runtimeHtml = runtimeEdgesFor(section).map(e => {
        const r = byId.get(e.to_id);
        const excerpt = e.runtime_range ? lineSlice(r.content, e.runtime_range.start_line, e.runtime_range.end_line) : '';
        const mirrors = (r.mirrors || []).map(m => escapeHtml(pos({ path: m.path, start_line: e.runtime_range?.start_line, end_line: e.runtime_range?.end_line, exists: m.exists }))).join('<br>') || 'none';
        return `<article class="file-card">
          <h4><a href="#${pageId(r.id)}">${escapeHtml(r.config)}</a> ${badge(e.status)}</h4>
          <div class="meta-grid">
            <div class="meta-k">canonical</div><div class="meta-v">${escapeHtml(pos(e.runtime_range))}</div>
            <div class="meta-k">mirror</div><div class="meta-v">${mirrors}</div>
            <div class="meta-k">evidence</div><div class="meta-v">${escapeHtml(e.evidence)}</div>
          </div>
          <pre class="line-preview"><code>${escapeHtml(excerpt ? numbered(excerpt, e.runtime_range.start_line || 1) : 'No exact runtime excerpt available.')}</code></pre>
        </article>`;
      }).join('');
      return page(section.id, 'section-page', section.name, `${section.type || 'section'} · ${section.relation_state}`, `
        <div class="section-flow">
          <section class="panel flow-col">
            <h4>Source / Capture / Memory / Project -> Section</h4>
            <p class="page-sub">这是 declared / derived / uncertain 关系，不是 compiler exact mapping。</p>
            <div class="file-grid">${sourcesHtml}</div>
          </section>
          <div class="flow-arrow">-></div>
          <section class="panel flow-col">
            <h4>Canonical Section 内容</h4>
            <div class="meta-grid">
              <div class="meta-k">位置</div><div class="meta-v">${escapeHtml(pos(section.position))}</div>
              <div class="meta-k">relation</div><div class="meta-v">${badge(section.relation_state)} ${escapeHtml(section.relation_note)}</div>
              <div class="meta-k">source 数</div><div class="meta-v">${sourceEdges.length}</div>
              <div class="meta-k">runtime 数</div><div class="meta-v">${runtimeEdgesFor(section).length}</div>
            </div>
            <pre class="line-preview"><code>${escapeHtml(numbered(section.content, section.position?.start_line || 1))}</code></pre>
          </section>
          <div class="flow-arrow">-></div>
          <section class="panel flow-col">
            <h4>Section -> Runtime</h4>
            <p class="page-sub">这里展示 compiler exact mapping：canonical section block 被渲染后在 runtime 中命中的行范围。</p>
            <div class="file-grid">${runtimeHtml}</div>
          </section>
        </div>`);
    }
    function renderSourcePage(s) {
      const inbound = graph.edges.filter(e => e.from_id === s.id && e.relation === 'source_to_section');
      const cards = inbound.map(e => {
        const sec = byId.get(e.to_id);
        return `<article class="file-card">
          <h4><a href="#${pageId(sec.id)}">${escapeHtml(sec.name)}</a> ${badge(e.status)}</h4>
          <div class="meta-grid">
            <div class="meta-k">evidence</div><div class="meta-v">${escapeHtml(e.evidence)}</div>
            <div class="meta-k">section</div><div class="meta-v">${escapeHtml(pos(sec.position))}</div>
          </div>
        </article>`;
      }).join('');
      return page(s.id, 'source-page', s.label, `${s.kind} · ${s.pointer}`, `
        <div class="section-grid">
          <section class="panel">
            <h4>Source 原文位置</h4>
            <div class="meta-grid">
              <div class="meta-k">pointer</div><div class="meta-v">${escapeHtml(s.pointer)}</div>
              <div class="meta-k">位置</div><div class="meta-v">${escapeHtml(pos(s.position))}</div>
              <div class="meta-k">status</div><div class="meta-v">${s.status === 'missing' ? badge('missing') : escapeHtml(s.status)}</div>
            </div>
            <pre class="line-preview"><code>${escapeHtml(s.content_excerpt ? numbered(s.content_excerpt, s.position?.start_line || 1) : 'source excerpt not available')}</code></pre>
          </section>
          <section class="panel">
            <h4>声明进入的 section</h4>
            <div class="file-grid">${cards || '<article class="file-card">No section relation.</article>'}</div>
          </section>
        </div>`);
    }
    function gapItems() {
      const direct = graph.unexplained.map((item, index) => ({
        id: `GAP-${String(index + 1).padStart(3, '0')}`,
        type: item.type,
        object: item.section || item.config || item.source || 'workspace',
        message: item.message || JSON.stringify(item),
        runtime: item.config || affectedRuntimeForSection(item.section),
        status: 'open',
        raw: item,
      }));
      const offset = direct.length;
      const declared = graph.sections.filter(s => s.relation_state === 'declared').map((section, index) => ({
        id: `GAP-${String(offset + index + 1).padStart(3, '0')}`,
        type: 'declared_without_derive_record',
        object: section.name,
        message: section.relation_note || 'section declares upstream pointers, but no exact derive record exists',
        runtime: runtimeEdgesFor(section).map(e => byId.get(e.to_id)?.config).filter(Boolean).join(' / ') || 'none',
        status: 'open',
        raw: { type: 'declared_without_derive_record', section: section.name, message: section.relation_note },
      }));
      return [...direct, ...declared];
    }
    function affectedRuntimeForSection(sectionName) {
      if (!sectionName) return 'none';
      const section = graph.sections.find(s => s.name === sectionName);
      if (!section) return 'none';
      return runtimeEdgesFor(section).map(e => byId.get(e.to_id)?.config).filter(Boolean).join(' / ') || 'none';
    }
    function renderGapTable(rows) {
      return `<table class="gap-table">
        <thead><tr><th>ID</th><th>对象</th><th>问题类型</th><th>描述</th><th>影响 Runtime</th><th>状态</th><th>Owner Action</th></tr></thead>
        <tbody>${rows.map((row, index) => `<tr>
          <td><a href="#${pageId(row.raw && graph.unexplained[index] ? `issue:${index}` : 'issues:overview')}">${escapeHtml(row.id)}</a></td>
          <td>${escapeHtml(row.object)}</td>
          <td>${badge(row.type.includes('missing') ? 'missing' : row.type.includes('uncertain') ? 'uncertain' : 'declared')}</td>
          <td>${escapeHtml(row.message)}</td>
          <td>${escapeHtml(row.runtime || 'none')}</td>
          <td>${escapeHtml(row.status)}</td>
          <td>propose -> review -> approve</td>
        </tr>`).join('') || '<tr><td colspan="7">No unexplained relationships.</td></tr>'}</tbody>
      </table>`;
    }
    function renderGapOverviewPage() {
      const rows = gapItems();
      return page('issues:overview', 'issue-page', 'Unexplained / Review Gaps', `${rows.length} review object(s)`, `
        <section class="panel unexplained">
          <h4>缺口总览</h4>
          <p class="page-sub">Portal 只暴露缺口，不直接修正 canonical source。declared_without_derive_record 表示有 upstream 声明，但没有可审计的 derive record。</p>
          <div class="gap-grid">${renderGapSummaryCards()}</div>
          ${renderGapTable(rows)}
        </section>
        ${renderReviewWorkflow()}`);
    }
    function renderIssuePage(issue, i) {
      return page(`issue:${i}`, 'issue-page', issue.type, issue.section || issue.config || 'unexplained', `
        <section class="panel unexplained">
          <h4>无法解释 / 缺 derive record</h4>
          <pre><code>${escapeHtml(JSON.stringify(issue, null, 2))}</code></pre>
        </section>
        ${renderReviewWorkflow()}`);
    }
    function renderGapSummaryCards() {
      const counts = graph.unexplained.reduce((acc, item) => {
        acc[item.type] = (acc[item.type] || 0) + 1;
        return acc;
      }, {});
      const declaredWithoutDerive = graph.sections.filter(s => s.relation_state === 'declared').length;
      const cards = [
        ['Missing Source', (counts.missing_source_relation || 0) + (counts.unresolved_source_pointer || 0)],
        ['No Derive Record', declaredWithoutDerive],
        ['Uncertain Relation', graph.sections.filter(s => s.relation_state === 'uncertain').length],
        ['Critical', 0],
      ];
      return cards.map(([label, count]) => `<div class="stat"><strong>${count}</strong><span>${escapeHtml(label)}</span></div>`).join('');
    }
    function renderReviewWorkflow() {
      return `<section class="panel">
        <h4>Owner 审核工作流（只读审计，不直接编辑）</h4>
        <div class="workflow">
          <div class="workflow-step"><strong>1 propose</strong><span>Agent 提案补 derive record 或 source pointer</span></div>
          <div class="workflow-step"><strong>2 review</strong><span>Owner 审核 source、section 与 runtime 证据</span></div>
          <div class="workflow-step"><strong>3 approve</strong><span>通过后写入 canonical source / proposal 记录</span></div>
          <div class="workflow-step"><strong>4 rejected</strong><span>驳回，不自动补全历史关系</span></div>
        </div>
        <div class="review-note">所有关系修正必须产生 derive record 或 proposal，不在 Portal 内直接改事实源。</div>
      </section>`;
    }
    function renderPages() {
      pagesRoot.innerHTML = [
        renderOverviewPage(),
        ...graph.runtimes.map(renderRuntimePage),
        ...graph.sections.map(renderSectionPage),
        ...graph.sources.map(renderSourcePage),
        renderGapOverviewPage(),
        ...(graph.unexplained.length ? graph.unexplained.map(renderIssuePage) : [page('issues:none', 'issue-page', '无缺口', 'unexplained', '<section class="panel">No unexplained relationships.</section>')]),
      ].join('');
    }
    function bindNav() {
      document.querySelectorAll('.nav-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
          const branch = btn.closest('.nav-branch');
          const collapsed = branch.classList.toggle('collapsed');
          btn.setAttribute('aria-expanded', String(!collapsed));
        });
      });
    }
    function showPageFromHash() {
      const fallback = 'overview';
      const targetId = location.hash.slice(1) || pageId(fallback);
      const target = document.getElementById(targetId) || document.getElementById(pageId(fallback));
      document.querySelectorAll('.portal-page').forEach(p => p.classList.toggle('active', p === target));
      document.querySelectorAll('.nav-tree a').forEach(a => a.classList.toggle('active', a.getAttribute('href') === '#' + target.id));
    }
    function applySearch() {
      const q = input.value.trim().toLowerCase();
      let visible = 0;
      document.querySelectorAll('.nav-tree a').forEach(a => {
        const ok = !q || a.dataset.search.includes(q);
        a.hidden = !ok;
        if (ok) visible += 1;
      });
      emptyState.style.display = visible ? 'none' : 'block';
    }
    function applyPerspective() {
      const status = {
        all: '全部审计节点：runtime、section、source 和 unexplained。',
        runtime: 'Runtime 视角：左树按 Agent 实际看到的 MD -> section -> source 重组。',
        relations: '关系视角：关注 exact compiler mapping 与 derived/declared/uncertain。',
        unexplained: '缺口视角：只看 missing source、缺 derive record、uncertain relation。',
      };
      document.getElementById('perspective-status').textContent = status[perspective];
      document.querySelectorAll('[data-perspective]').forEach(btn => btn.classList.toggle('active', btn.dataset.perspective === perspective));
      buildNav();
      applySearch();
      showPageFromHash();
    }
    document.getElementById('workspace').textContent = `${graph.workspace_root} · layout=${graph.layout}`;
    document.getElementById('stats').innerHTML = [
      `<div class="stat"><strong>${graph.runtimes.length}</strong><span>runtime MD</span></div>`,
      `<div class="stat"><strong>${graph.sections.length}</strong><span>sections</span></div>`,
      `<div class="stat"><strong>${graph.sources.length}</strong><span>sources</span></div>`,
      `<div class="stat"><strong>${graph.unexplained.length}</strong><span>unexplained</span></div>`,
    ].join('');
    document.getElementById('expand-all').addEventListener('click', () => document.querySelectorAll('.nav-branch').forEach(b => b.classList.remove('collapsed')));
    document.getElementById('collapse-all').addEventListener('click', () => document.querySelectorAll('.nav-branch').forEach(b => b.classList.add('collapsed')));
    document.querySelectorAll('[data-perspective]').forEach(btn => btn.addEventListener('click', () => { perspective = btn.dataset.perspective; applyPerspective(); }));
    document.addEventListener('keydown', event => {
      if (event.key === '/' && document.activeElement !== input) { event.preventDefault(); input.focus(); input.select(); }
      if (event.key === 'Escape' && document.activeElement === input) { input.value = ''; applySearch(); input.blur(); }
    });
    input.addEventListener('input', applySearch);
    window.addEventListener('hashchange', showPageFromHash);
    buildNav();
    renderPages();
    applyPerspective();
    showPageFromHash();
  </script>
</body>
</html>
"""
