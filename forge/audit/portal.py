"""Static web UI for inspecting forge audit graphs.

The portal renders the audit graph as a layered provenance graph
(source -> section -> runtime) with an inspector panel. It is a single
self-contained HTML file with no external dependencies, so it works from
``file://`` or behind ``forge audit serve``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from forge.audit.diff import build_audit_diff
from forge.audit.graph import build_audit_graph


def write_portal(
    root: Path,
    output_dir: Path | None = None,
    *,
    diff: bool = False,
    base_ref: str = "HEAD",
) -> tuple[Path, Path]:
    """Write ``context-audit-portal.html`` and ``audit-graph.json`` for root.

    With ``diff=True`` the portal opens in change-review mode, annotating the
    graph against ``base_ref`` (added / modified / removed / unchanged).
    """
    root = Path(root).resolve()
    payload = build_audit_diff(root, base_ref) if diff else build_audit_graph(root).to_dict()
    out_dir = output_dir or (root / ".forge" / "audit")
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "audit-graph.json"
    html_path = out_dir / "context-audit-portal.html"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    html_path.write_text(_render_html(payload), encoding="utf-8")
    return html_path, json_path


def _render_html(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False)
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
      /* Neutral review palette: mid-light, low-saturation, with semantic colors
         muted enough for long desktop review sessions. */
      --bg: #f1f0ec;
      --canvas-dot: #ddd9d1;
      --panel: #fbfaf7;
      --panel-soft: #f6f4ef;
      --surface-3: #ece9e2;
      --ink: #202329;
      --ink-soft: #5f6670;
      --muted: #858b93;
      --muted-2: #a3a7ad;
      --line: #e2ded6;
      --line-2: #d5d0c7;
      --border-strong: #beb8ad;
      --line-soft: #ebe7df;
      --accent: #566579;
      --accent-2: #47586d;
      --accent-soft: #e7ebee;
      --accent-ring: rgba(86, 101, 121, 0.28);
      --exact: #9ca0a6;
      --exact-soft: #ece9e2;
      --derived: #5c7189;
      --derived-soft: #e7ecf0;
      --declared: #73677d;
      --declared-soft: #eee9f0;
      --uncertain: #9a7448;
      --uncertain-soft: #f1e8dc;
      --missing: #a86464;
      --missing-soft: #f1e4e2;
      --wrapper: #92969c;
      --added: #5d8065;
      --added-soft: #e4ece5;
      --modified: #9a7448;
      --modified-soft: #f1e8dc;
      --removed: #a86464;
      --removed-soft: #f1e4e2;
      --diff-add-bg: #e4ece5;
      --diff-add-mark: #4f7658;
      --diff-del-bg: #f1e4e2;
      --diff-del-mark: #965858;
      --shadow-sm: 0 1px 2px rgba(32, 35, 41, .05), 0 1px 1px rgba(32, 35, 41, .03);
      --shadow-md: 0 4px 16px rgba(32, 35, 41, .08), 0 1px 3px rgba(32, 35, 41, .05);
      --shadow-lg: 0 12px 40px rgba(32, 35, 41, .13), 0 2px 8px rgba(32, 35, 41, .06);
      --r-lg: 12px;
      --r-md: 9px;
      --r-sm: 6px;
      --font: "Geist", "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", sans-serif;
      --mono: "Geist Mono", "JetBrains Mono", ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, monospace;
    }
    * { box-sizing: border-box; }
    html, body { height: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: var(--font);
      font-size: 14px;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
    }
    button { font-family: inherit; cursor: pointer; }
    .app { display: flex; flex-direction: column; height: 100vh; min-height: 0; }

    /* ---------- top bar ---------- */
    header.bar {
      flex: 0 0 auto;
      display: flex;
      align-items: center;
      gap: 18px;
      padding: 14px 22px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
    }
    .brand { display: flex; align-items: center; gap: 9px; min-width: 0; flex: 0 0 auto; }
    .brand .mark {
      width: 26px; height: 26px; border-radius: 7px; flex: 0 0 auto;
      background: #2f343b; display: grid; place-items: center; color: #fff;
      font-weight: 700; font-size: 14px; font-family: var(--mono);
    }
    .brand .app-name { font-size: 14px; font-weight: 650; letter-spacing: -.01em; white-space: nowrap; }
    .crumbs { display: flex; align-items: center; gap: 8px; min-width: 0; color: var(--muted); font-size: 12.5px; overflow: hidden; }
    .crumbs .sep { color: var(--muted-2); }
    .crumbs .repo { color: var(--ink-soft); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .crumbs .branch { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-soft); color: var(--ink-soft); font-family: var(--mono); font-size: 11.5px; white-space: nowrap; }
    .bar-right { display: flex; align-items: center; gap: 10px; margin-left: auto; flex: 0 0 auto; }
    .seg { display: inline-flex; padding: 2px; gap: 2px; background: var(--surface-3); border: 1px solid var(--line); border-radius: var(--r-md); }
    .seg-btn { border: 0; background: transparent; color: var(--muted); border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 550; }
    .seg-btn.active { background: var(--panel); color: var(--ink); box-shadow: var(--shadow-sm); }
    .seg-btn:disabled { opacity: .4; cursor: not-allowed; }
    .search-wrap { position: relative; }
    .search {
      width: 230px; border: 1px solid var(--line); border-radius: var(--r-md);
      padding: 9px 12px 9px 32px; font-size: 13px; background: var(--panel-soft); color: var(--ink);
      transition: border-color .15s, box-shadow .15s, background .15s;
    }
    .search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); background: var(--panel); }
    .search::placeholder { color: var(--muted); }
    .search-wrap svg { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: var(--muted); pointer-events: none; }

    /* ---------- toolbar ---------- */
    .toolbar {
      flex: 0 0 auto;
      display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
      padding: 9px 22px; background: var(--panel-soft); border-bottom: 1px solid var(--line);
    }
    .toolbar .lbl { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-right: 4px; }
    .leg {
      display: inline-flex; align-items: center; gap: 7px;
      border: 0; background: transparent; color: var(--ink-soft);
      padding: 4px 6px; font-size: 12px; user-select: none; border-radius: 6px;
      transition: opacity .12s, background .12s;
    }
    .leg .sw { width: 16px; height: 0; border-top: 2px solid var(--muted-2); flex: 0 0 auto; }
    .leg[data-status="exact"] .sw { border-top-color: var(--exact); }
    .leg[data-status="derived"] .sw { border-top-color: var(--derived); }
    .leg[data-status="declared"] .sw { border-top-color: var(--declared); }
    .leg[data-status="uncertain"] .sw { border-top-color: var(--uncertain); }
    .leg[data-status="missing"] .sw { border-top-color: var(--missing); }
    .leg.dashed .sw { border-top-style: dashed; }
    .leg[aria-pressed="false"] { opacity: .35; }
    .leg:hover { background: var(--surface-3); }
    .bar-sep { width: 1px; height: 18px; background: var(--line); margin: 0 4px; }
    .chip {
      display: inline-flex; align-items: center; gap: 6px;
      border: 1px solid var(--line); background: var(--panel); color: var(--ink-soft);
      border-radius: 999px; padding: 5px 11px; font-size: 12px; user-select: none;
      transition: background .12s, border-color .12s, color .12s, opacity .12s;
    }
    .chip[aria-pressed="false"] { opacity: .5; }
    .chip:hover { border-color: var(--accent); }
    .chip.toggle[aria-pressed="true"] { background: var(--accent); color: #fff; border-color: var(--accent); }
    .counts { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--ink-soft); margin-right: 4px; }
    .counts .ct { display: inline-flex; align-items: center; gap: 5px; }
    .counts .ct b { font-weight: 650; color: var(--ink); }
    .counts .ct.warn b { color: var(--missing); }
    .spacer { margin-left: auto; }
    .ghost-btn {
      border: 1px solid var(--line); background: var(--panel); color: var(--ink-soft);
      border-radius: var(--r-sm); padding: 6px 11px; font-size: 12px;
    }
    .ghost-btn:hover { border-color: var(--accent); color: var(--accent); }

    /* ---------- body: full-bleed graph + floating detail drawer ---------- */
    .split { position: relative; flex: 1 1 auto; min-height: 0; overflow: hidden; --insp-w: min(60vw, 900px); }
    .canvas-wrap { position: absolute; inset: 0; overflow: auto; padding: 28px 36px 72px; background-color: var(--bg); background-image: radial-gradient(var(--canvas-dot) 1px, transparent 1.4px); background-size: 18px 18px; }
    .divider {
      position: absolute; top: 0; bottom: 0; right: var(--insp-w); width: 9px;
      transform: translateX(50%); z-index: 31; cursor: col-resize; display: none;
    }
    .split.panel-open .divider { display: block; }
    .split.maxed .divider { display: none; }
    .divider::before { content: ""; position: absolute; inset: 0; }
    .divider::after { content: ""; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 4px; height: 40px; border-radius: 3px; background: var(--line-2); transition: background .12s; }
    .divider:hover::after, .divider.drag::after { background: var(--accent); }
    body.dragging { cursor: col-resize; user-select: none; }
    .lanes {
      --lane-gap: clamp(56px, 5.2vw, 104px);
      position: relative; display: grid;
      grid-template-columns: repeat(var(--lane-count, 3), minmax(292px, 1fr));
      justify-content: stretch; gap: var(--lane-gap); width: 100%;
      min-width: var(--lane-min-width, 100%);
    }
    .links-svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: visible; }
    .edge-chips { position: absolute; inset: 0; pointer-events: none; z-index: 2; }
    .edge-chip {
      position: absolute; transform: translate(-50%, -50%); pointer-events: auto; cursor: pointer;
      display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px;
      background: var(--panel); border: 1px solid var(--line); font-size: 10px; color: var(--ink-soft);
      box-shadow: var(--shadow-sm); white-space: nowrap; transition: border-color .14s, color .14s, box-shadow .14s, transform .14s, opacity .14s;
    }
    .edge-chip .d { width: 6px; height: 6px; border-radius: 50%; flex: 0 0 auto; }
    .edge-chip:hover, .edge-chip.on { border-color: var(--accent); color: var(--accent); box-shadow: var(--shadow-md); transform: translate(-50%, -50%) scale(1.08); z-index: 3; }
    .edge-chip.dim { opacity: .22; }
    .graph-empty {
      position: absolute; left: 50%; top: 36%; transform: translate(-50%, -50%);
      z-index: 4; width: min(420px, calc(100vw - 48px)); text-align: center;
      border: 1px solid var(--line); border-radius: var(--r-md); background: rgba(251,250,247,.96);
      box-shadow: var(--shadow-md); padding: 18px 20px; color: var(--ink-soft);
    }
    .graph-empty[hidden] { display: none; }
    .graph-empty b { display: block; color: var(--ink); font-size: 14px; margin-bottom: 5px; }
    .graph-empty span { font-size: 12px; line-height: 1.45; }
    /* ---------- motion / polish ---------- */
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
    @keyframes panelIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @keyframes dashmove { to { stroke-dashoffset: -26; } }
    .links-svg path[data-edge] { transition: stroke .16s ease, stroke-width .16s ease, opacity .16s ease; }
    .links-svg path.flow { animation: dashmove .5s linear infinite; }
    #insp-body.anim { animation: panelIn .2s cubic-bezier(.4, 0, .2, 1); }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .001ms !important; transition-duration: .001ms !important; } }
    .lane { position: relative; z-index: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
    .lane[hidden] { display: none; }
    .lane.filtered-empty { display: none; }
    .lane-head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding-bottom: 2px; }
    .lane-head h2 { margin: 0; font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .07em; color: var(--ink-soft); }
    .lane-head .count { font-size: 11px; color: var(--muted); }
    .lane-group-label { font-size: 10.5px; color: var(--ink-soft); font-weight: 700; text-transform: uppercase; letter-spacing: .06em; margin: 14px 0 0; display: flex; align-items: center; gap: 8px; }
    .lane-group-label::before { content: ""; width: 6px; height: 6px; border-radius: 2px; background: var(--accent); flex: 0 0 auto; }
    .lane-group-label:first-child { margin-top: 2px; }
    .grp-count { margin-left: auto; font-weight: 600; color: var(--muted); background: var(--line-soft); border-radius: 999px; padding: 1px 7px; }

    .node {
      position: relative; z-index: 1; text-align: left; width: 100%;
      border: 1px solid var(--line); border-radius: var(--r-md); background: var(--panel);
      padding: 10px 12px; box-shadow: var(--shadow-sm);
      transition: box-shadow .16s ease, border-color .16s ease, transform .14s cubic-bezier(.4,0,.2,1), opacity .16s ease;
      display: grid; gap: 5px; animation: fadeIn .22s ease both;
    }
    .node:hover { border-color: var(--border-strong); transform: translateY(-1px); box-shadow: var(--shadow-md); }
    .node:active { transform: translateY(0); }
    .node .chg { position: absolute; top: -8px; right: -8px; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 999px; display: grid; place-items: center; font-size: 12px; font-weight: 800; color: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.25); z-index: 2; }
    .chg-added { background: var(--added); }
    .chg-modified { background: var(--modified); }
    .chg-removed { background: var(--removed); }
    .node.ch-removed { opacity: .6; }
    .node.ch-removed .name { text-decoration: line-through; }
    .node.ch-added { border-color: #9cb5a1; }
    .node.ch-modified { border-color: #c6aa82; }
    body.audit-view .chg { display: none; }
    body.audit-view .node.ch-added, body.audit-view .node.ch-modified, body.audit-view .node.ch-removed { border-color: var(--line); }
    body.audit-view #changed-only { display: none; }
    .tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--line); margin: 2px 0 16px; }
    .tab { border: 0; background: transparent; color: var(--muted); padding: 8px 12px; font-size: 12.5px; font-weight: 550; border-bottom: 2px solid transparent; margin-bottom: -1px; }
    .tab:hover { color: var(--ink); }
    .tab.active { color: var(--ink); border-bottom-color: var(--accent); }
    .tab .n { color: var(--muted); font-weight: 600; margin-left: 5px; }
    .tabpane[hidden] { display: none; }
    .code-line.d-add { background: var(--diff-add-bg); }
    .code-line.d-add .ln { background: #d8e4da; color: var(--diff-add-mark); }
    .code-line.d-del { background: var(--diff-del-bg); }
    .code-line.d-del .ln { background: #ead2cf; color: var(--diff-del-mark); }
    .diff-banner { display: flex; align-items: center; gap: 8px; border-radius: var(--r-md); padding: 9px 12px; font-size: 12.5px; margin-bottom: 14px; font-weight: 600; }
    .diff-banner.added { background: var(--added-soft); color: #47684f; }
    .diff-banner.modified { background: var(--modified-soft); color: #765735; }
    .diff-banner.removed { background: var(--removed-soft); color: #81504f; }
    .diff-pill { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 999px; padding: 5px 11px; font-size: 12px; color: var(--ink-soft); background: var(--panel); }
    .diff-pill b { font-weight: 700; }
    .node .row { display: flex; align-items: center; gap: 8px; min-width: 0; }
    .node .kind-ic { width: 26px; height: 26px; border-radius: 7px; flex: 0 0 auto; display: grid; place-items: center; }
    .node .name { font-weight: 650; font-size: 13.5px; letter-spacing: -.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; }
    .node .ptr { font-size: 11.5px; color: var(--muted); font-family: var(--mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .node .tags { display: flex; flex-wrap: wrap; gap: 5px; }
    .node .submeta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--muted); }
    .node .submeta .meta-mark { font-weight: 600; }
    .node .submeta .dotsep { color: var(--muted-2); }
    .node .sdot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 0 0 3px rgba(0,0,0,.03); }
    .node.sel { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft), var(--shadow-md); }
    .node.kbd { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
    .node.dim { display: none; }
    .node.hit { border-color: var(--accent); }

    .hover-card {
      position: absolute; z-index: 24; width: min(720px, calc(100vw - 32px)); max-height: min(76vh, 620px); overflow: hidden;
      padding: 12px 14px 13px; border: 1px solid var(--line-2); border-radius: var(--r-md);
      background: rgba(251,250,247,.99); box-shadow: var(--shadow-lg); pointer-events: auto;
      animation: panelIn .14s cubic-bezier(.4, 0, .2, 1);
    }
    .hover-card[hidden] { display: none; }
    .preview-head { display: grid; gap: 3px; }
    .preview-eyebrow { margin: 0; display: flex; align-items: center; gap: 7px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
    .preview-title { margin: 0; font-size: 14.5px; line-height: 1.22; font-weight: 750; overflow-wrap: anywhere; }
    .preview-sub { margin: 0; font-size: 11.5px; color: var(--muted); font-family: var(--mono); overflow-wrap: anywhere; }
    .preview-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .preview-chip { display: inline-flex; align-items: center; gap: 5px; max-width: 100%; padding: 2px 7px; border: 1px solid var(--line); border-radius: 999px; background: var(--panel-soft); color: var(--ink-soft); font-size: 10.5px; line-height: 1.35; }
    .preview-chip b { font-weight: 700; color: var(--ink); }
    .preview-grid { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 7px 13px; margin-top: 8px; }
    .preview-row { display: grid; grid-template-columns: 54px minmax(0,1fr); gap: 7px; align-items: baseline; font-size: 11.5px; }
    .preview-k { color: var(--muted); }
    .preview-v { color: var(--ink-soft); overflow-wrap: anywhere; }
    .preview-flow { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .preview-section { margin-top: 8px; }
    .preview-section h4 { margin: 0 0 5px; font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-soft); }
    .preview-compare { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr); gap: 9px; margin-top: 9px; }
    .preview-pane { min-width: 0; }
    .preview-pane-title { margin: 0 0 5px; display: flex; justify-content: space-between; gap: 8px; color: var(--ink-soft); font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em; }
    .preview-pane-title span:last-child { color: var(--muted); font-family: var(--mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-transform: none; letter-spacing: 0; }
    .preview-code { border: 1px solid var(--line); border-radius: var(--r-sm); overflow: hidden; background: var(--panel-soft); }
    .preview-code .preview-cap { padding: 5px 9px; border-bottom: 1px solid var(--line-soft); font-size: 10.5px; color: var(--muted); background: var(--panel); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .preview-code .preview-line { display: grid; grid-template-columns: 30px minmax(0,1fr); font-family: var(--mono); font-size: 10.6px; line-height: 1.3; }
    .preview-code .ln { color: var(--muted-2); text-align: right; padding: 0 6px; border-right: 1px solid var(--line-soft); background: #f4f1e9; }
    .preview-code .lc { padding: 0 7px; white-space: pre-wrap; overflow-wrap: anywhere; }
    .preview-compare .preview-code .lc { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .preview-diff .lc { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .preview-code .d-add { background: var(--diff-add-bg); }
    .preview-code .d-del { background: var(--diff-del-bg); }
    .preview-more { padding: 3px 7px; border-top: 1px solid var(--line-soft); color: var(--muted); font-size: 10.5px; }
    .hover-card .hover-hint { margin: 9px 0 0; padding-top: 8px; border-top: 1px solid var(--line-soft); font-size: 10.8px; color: var(--muted); }

    .tag {
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
      background: var(--line-soft); color: var(--ink-soft);
    }
    .tag .d { width: 7px; height: 7px; border-radius: 50%; }
    .tag.mono { font-family: var(--mono); font-weight: 500; }

    /* ---------- inspector ---------- */
    .inspector {
      position: absolute; top: 0; right: 0; bottom: 0; width: var(--insp-w);
      background: var(--panel); border-left: 1px solid var(--line); overflow: auto;
      z-index: 30; box-shadow: var(--shadow-lg);
      transform: translateX(101%); transition: transform .26s cubic-bezier(.4, 0, .2, 1), width .18s ease;
    }
    .split.panel-open .inspector { transform: none; }
    .split.maxed .inspector { width: min(88vw, 1320px); }
    .insp-toolbar { position: sticky; top: 0; z-index: 3; display: flex; justify-content: flex-end; gap: 6px; padding: 9px 12px; background: linear-gradient(var(--panel), var(--panel) 72%, transparent); }
    .icon-btn { width: 30px; height: 30px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-soft); color: var(--ink-soft); font-size: 14px; line-height: 1; display: grid; place-items: center; }
    .icon-btn:hover { border-color: var(--accent); color: var(--accent); }
    .insp-pad { padding: 2px 22px 48px; }
    .insp-backdrop { position: absolute; inset: 0; background: rgba(24, 21, 16, .28); z-index: 29; }
    .split.maxed .insp-pad { padding: 2px 32px 56px; }
    .split.maxed .code-scroll { max-height: 70vh; }
    /* In the expanded view a section reads as a full lineage, three columns. */
    .trace3 { display: grid; grid-template-columns: minmax(0,0.9fr) minmax(0,1.1fr) minmax(0,1.1fr); gap: 18px; align-items: start; }
    .trace3 .col > h4 { margin: 0 0 9px; font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-soft); }
    .trace3 .col .code { margin-bottom: 12px; }
    .trace3 .arrow { display: none; }
    @media (max-width: 1280px) { .trace3 { grid-template-columns: 1fr; } }
    .insp-eyebrow { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin: 0 0 6px; display: flex; align-items: center; gap: 8px; }
    .insp-title { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -.015em; overflow-wrap: anywhere; }
    .insp-sub { color: var(--muted); font-size: 12.5px; margin: 4px 0 0; overflow-wrap: anywhere; font-family: var(--mono); }
    .insp-section { margin-top: 20px; }
    .insp-section > h4 { margin: 0 0 9px; font-size: 11.5px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-soft); }
    .kv { display: grid; grid-template-columns: 84px minmax(0,1fr); gap: 5px 12px; font-size: 12.5px; align-items: start; }
    .kv .k { color: var(--muted); }
    .kv .v { overflow-wrap: anywhere; }
    .lineage { display: flex; flex-direction: column; gap: 7px; }
    .lin-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
    .lin-arrow { color: var(--muted); }
    .nodelink {
      display: inline-flex; align-items: center; gap: 6px; max-width: 100%;
      border: 1px solid var(--line); background: var(--panel-soft); border-radius: 999px;
      padding: 4px 10px; font-size: 12px; color: var(--ink-soft); transition: border-color .12s, background .12s;
    }
    .nodelink:hover { border-color: var(--accent); background: var(--panel); color: var(--accent); }
    .nodelink .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .nodelink .d { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; }

    .code {
      margin: 0; border: 1px solid var(--line); border-radius: var(--r-md); overflow: hidden;
      background: var(--panel-soft);
    }
    .code-scroll { max-height: 46vh; overflow: auto; }
    .code-line { display: grid; grid-template-columns: 42px minmax(0,1fr); font-family: var(--mono); font-size: 11.5px; line-height: 1.55; }
    .code-line .ln { color: #aaa49a; text-align: right; padding: 0 9px; user-select: none; border-right: 1px solid var(--line-soft); background: #f4f1e9; }
    .code-line .lc { padding: 0 11px; white-space: pre; overflow-wrap: normal; }
    .code-line.hl { background: #f3ead7; }
    .code-line.hl .ln { background: #eadbbf; color: #765735; }
    .code-cap { display: flex; justify-content: space-between; align-items: center; padding: 7px 11px; border-bottom: 1px solid var(--line); font-size: 11px; color: var(--muted); background: var(--panel); }

    .gap-list { display: flex; flex-direction: column; gap: 8px; }
    .gap {
      text-align: left; width: 100%; border: 1px solid var(--line); border-left-width: 3px;
      border-radius: var(--r-sm); background: var(--panel-soft); padding: 10px 12px;
      display: grid; gap: 3px; transition: border-color .12s, background .12s, transform .1s;
    }
    .gap:hover { background: var(--panel); transform: translateX(2px); }
    .gap .gh { display: flex; align-items: center; gap: 8px; }
    .gap .gid { font-family: var(--mono); font-size: 10.5px; color: var(--muted); }
    .gap .gobj { font-weight: 650; font-size: 13px; }
    .gap .gmsg { font-size: 12px; color: var(--ink-soft); line-height: 1.45; }
    .gap.sev-high { border-left-color: var(--missing); }
    .gap.sev-med { border-left-color: var(--uncertain); }
    .gap.sev-low { border-left-color: var(--declared); }

    .health-bars { display: flex; flex-direction: column; gap: 12px; }
    .hbar .hbar-top { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 5px; }
    .hbar .hbar-top .label { font-size: 12.5px; color: var(--ink-soft); }
    .hbar .hbar-top .pct { font-size: 13px; font-weight: 700; }
    .track { height: 7px; border-radius: 999px; background: var(--line-soft); overflow: hidden; }
    .track > i { display: block; height: 100%; border-radius: 999px; }
    .distro { display: flex; height: 8px; border-radius: 999px; overflow: hidden; border: 1px solid var(--line); }
    .distro > i { height: 100%; }
    .distro-legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 9px; font-size: 11.5px; color: var(--ink-soft); }
    .distro-legend .li { display: inline-flex; align-items: center; gap: 5px; }
    .distro-legend .d { width: 8px; height: 8px; border-radius: 2px; }

    .empty { color: var(--muted); font-size: 13px; padding: 8px 0; }
    .note { font-size: 11.5px; color: var(--muted); line-height: 1.5; border-top: 1px solid var(--line-soft); margin-top: 22px; padding-top: 14px; }
    .workflow { display: grid; gap: 7px; }
    .wf-step { display: flex; gap: 9px; align-items: baseline; font-size: 12px; color: var(--ink-soft); }
    .wf-step b { color: var(--ink); }
    .wf-num { width: 18px; height: 18px; border-radius: 50%; background: var(--accent-soft); color: var(--accent); font-size: 11px; font-weight: 700; display: grid; place-items: center; flex: 0 0 auto; }

    @media (max-width: 1080px) {
      .split { --insp-w: 100vw; }
      .split.maxed .inspector { width: 100vw; }
      .canvas-wrap { padding: 20px 18px 56px; }
      .lanes { grid-template-columns: 1fr; gap: 22px; min-width: 100%; }
      .links-svg { display: none; }
      .counts { display: none; }
      .crumbs { display: none; }
    }
  </style>
</head>
<body>
  <div class="app">
    <header class="bar">
      <div class="brand">
        <div class="mark">f</div>
        <strong class="app-name">Context Audit</strong>
      </div>
      <nav class="crumbs" id="crumbs"></nav>
      <div class="bar-right">
        <div class="search-wrap">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>
          <input class="search" id="search" type="search" placeholder="搜索节点（按 / 聚焦）" />
        </div>
        <div class="seg" id="mode-seg" role="group" aria-label="视图模式">
          <button class="seg-btn" data-mode="audit" type="button">Audit</button>
          <button class="seg-btn" data-mode="review" id="mode-review" type="button">Review</button>
        </div>
      </div>
    </header>

    <div class="toolbar">
      <span class="lbl">Edge status</span>
      <button class="leg filter" data-status="exact" aria-pressed="true"><span class="sw"></span>Exact</button>
      <button class="leg filter" data-status="derived" aria-pressed="true"><span class="sw"></span>Derived</button>
      <button class="leg filter" data-status="declared" aria-pressed="true"><span class="sw"></span>Declared</button>
      <button class="leg filter dashed" data-status="uncertain" aria-pressed="true"><span class="sw"></span>Uncertain</button>
      <button class="leg filter dashed" data-status="missing" aria-pressed="true"><span class="sw"></span>Missing</button>
      <span class="bar-sep"></span>
      <button class="chip toggle" id="gaps-only" aria-pressed="false">只看缺口</button>
      <button class="chip toggle" id="changed-only" aria-pressed="false" hidden>只看改动</button>
      <div class="spacer"></div>
      <div class="counts" id="counts"></div>
      <button class="ghost-btn" id="overview-btn" title="审计总览 / 健康度">总览</button>
      <button class="ghost-btn" id="reset-view">重置</button>
    </div>

    <div class="split" id="split">
      <div class="canvas-wrap" id="canvas">
        <div class="lanes" id="lanes">
          <svg class="links-svg" id="links"></svg>
          <div class="edge-chips" id="edge-chips"></div>
          <div class="hover-card" id="hover-card" hidden></div>
          <div class="graph-empty" id="graph-empty" hidden><b>没有匹配节点</b><span>调整 Edge Status，或关闭“只看改动 / 只看缺口”。</span></div>
          <section class="lane" id="lane-external" hidden>
            <div class="lane-head"><h2>External Input · 导入</h2><span class="count" id="cnt-external"></span></div>
          </section>
          <section class="lane" id="lane-captures" hidden>
            <div class="lane-head"><h2>Capture / Clipping · 输入</h2><span class="count" id="cnt-captures"></span></div>
          </section>
          <section class="lane" id="lane-sources">
            <div class="lane-head"><h2>Canonical Source · 按架构层</h2><span class="count" id="cnt-sources"></span></div>
          </section>
          <section class="lane" id="lane-sections">
            <div class="lane-head"><h2>Canonical Section · 按架构层</h2><span class="count" id="cnt-sections"></span></div>
          </section>
          <section class="lane" id="lane-runtimes">
            <div class="lane-head"><h2>Runtime（Agent 实际读到）</h2><span class="count" id="cnt-runtimes"></span></div>
          </section>
        </div>
      </div>
      <div class="insp-backdrop" id="insp-backdrop" hidden></div>
      <div class="divider" id="divider" title="拖拽调整宽度（双击复位）"></div>
      <aside class="inspector" id="inspector">
        <div class="insp-toolbar">
          <button class="icon-btn" id="insp-expand" title="最大化（E）" aria-label="最大化">⤢</button>
          <button class="icon-btn" id="insp-close" title="收起（Esc）" aria-label="收起">✕</button>
        </div>
        <div class="insp-pad" id="insp-body"></div>
      </aside>
    </div>
  </div>

  <script id="audit-data" type="application/json">__AUDIT_DATA__</script>
  <script>
  (function () {
    "use strict";
    const graph = JSON.parse(document.getElementById("audit-data").textContent);
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

    const STATUS_COLOR = {
      exact: "var(--exact)", derived: "var(--derived)", declared: "var(--declared)",
      uncertain: "var(--uncertain)", missing: "var(--missing)", wrapper: "var(--wrapper)",
      imported: "var(--exact)", pending: "var(--uncertain)",
    };
    const KIND_COLOR = { source: "#5f7d7a", capture: "#9a7448", memory: "#73677d", project: "#5c7189", "unlinked-change": "#8a6f5a" };
    const KIND_LABEL = { source: "Source", capture: "Capture", memory: "Memory", project: "Project", "unlinked-change": "Review Change" };
    const externals = graph.externals || [];

    // ---- indices ----
    const byId = new Map();
    [...externals, ...graph.sources, ...graph.sections, ...graph.runtimes].forEach(n => byId.set(n.id, n));
    const srcEdges = graph.edges.filter(e => e.relation === "source_to_section");
    const rtEdges = graph.edges.filter(e => e.relation === "section_to_runtime");
    const importEdges = graph.edges.filter(e => e.relation === "external_to_source");
    const inputEdges = graph.edges.filter(e => e.relation === "input_to_source");
    const importEdgesTo = (id) => importEdges.filter(e => e.to_id === id);
    const importEdgesFrom = (id) => importEdges.filter(e => e.from_id === id);
    const inputEdgesTo = (id) => inputEdges.filter(e => e.to_id === id);
    const inputEdgesFrom = (id) => inputEdges.filter(e => e.from_id === id);
    const outAdj = new Map(), inAdj = new Map();
    graph.edges.forEach(e => {
      (outAdj.get(e.from_id) || outAdj.set(e.from_id, []).get(e.from_id)).push(e.to_id);
      (inAdj.get(e.to_id) || inAdj.set(e.to_id, []).get(e.to_id)).push(e.from_id);
    });
    const srcEdgesTo = (id) => srcEdges.filter(e => e.to_id === id);
    const srcEdgesFrom = (id) => srcEdges.filter(e => e.from_id === id);
    const rtEdgesFrom = (id) => rtEdges.filter(e => e.from_id === id);
    const rtEdgesTo = (id) => rtEdges.filter(e => e.to_id === id);

    // ---- change-review (diff) mode ----
    const diffMode = !!(graph.diff && graph.diff.available);
    const CHG_LABEL = { added: "新增", modified: "修改", removed: "删除", unchanged: "未变" };
    function lineDiffRows(oldText, newText) {
      const a = String(oldText || "").split("\n"), b = String(newText || "").split("\n");
      const m = a.length, n = b.length;
      const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
      for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      const out = []; let i = 0, j = 0;
      while (i < m && j < n) {
        if (a[i] === b[j]) { out.push({ type: "ctx", text: a[i], oldNo: i + 1, newNo: j + 1 }); i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push({ type: "del", text: a[i], oldNo: i + 1, newNo: null }); i++; }
        else { out.push({ type: "add", text: b[j], oldNo: null, newNo: j + 1 }); j++; }
      }
      while (i < m) out.push({ type: "del", text: a[i], oldNo: i + 1, newNo: null }), i++;
      while (j < n) out.push({ type: "add", text: b[j], oldNo: null, newNo: j + 1 }), j++;
      return out;
    }
    function diffLineLabel(row) {
      const no = row.type === "del" ? row.oldNo : row.type === "add" ? row.newNo : row.newNo;
      const sign = row.type === "add" ? "+" : row.type === "del" ? "−" : " ";
      return sign + (no == null ? "" : no);
    }
    function diffBlock(oldText, newText, caption) {
      const rows = lineDiffRows(oldText, newText).map(row => {
        const cls = row.type === "add" ? " d-add" : row.type === "del" ? " d-del" : "";
        return '<div class="code-line' + cls + '"><span class="ln">' + esc(diffLineLabel(row)) + '</span><span class="lc">' + esc(row.text || " ") + "</span></div>";
      }).join("");
      return '<div class="code">' + (caption ? '<div class="code-cap">' + caption + " · diff</div>" : "") +
        '<div class="code-scroll">' + rows + "</div></div>";
    }
    // Content block that becomes a diff when the node changed under review.
    function contentBlock(node, text, startLine, caption) {
      if (node && node.change === "modified" && node.prev_content != null)
        return diffBlock(node.prev_content, text, caption);
      return codeBlock(text, startLine, caption);
    }
    function changeBanner(node) {
      if (!reviewView || !node || !node.change || node.change === "unchanged") return "";
      const label = node.change === "added" ? "本次新增 · base 中不存在"
        : node.change === "removed" ? "本次删除 · 仅存在于 base"
        : "本次修改 · 下方为 base → 工作树 diff";
      return '<div class="diff-banner ' + node.change + '">' + esc(label) + "</div>";
    }

    // section -> overall compile status (exact iff every runtime mapping is exact)
    const sectionCompile = (id) => {
      const es = rtEdgesFrom(id);
      if (!es.length) return "uncertain";
      return es.every(e => e.status === "exact") ? "exact" : "uncertain";
    };
    // node primary status used for the status dot + filtering
    const nodeStatus = (n) => {
      if (n.kind === "external") return n.status || "imported";
      if (graph.sources.includes(n)) {
        if (n.status === "missing") return "missing";
        const e = srcEdgesFrom(n.id)[0];
        return e ? e.status : "uncertain";
      }
      if (graph.runtimes.includes(n)) {
        const es = rtEdgesTo(n.id);
        return es.length && es.every(e => e.status === "exact") ? "exact" : "uncertain";
      }
      return n.relation_state || "uncertain";
    };

    // ---- ordering ----
    const sectionSort = (s) => {
      const r = rtEdgesFrom(s.id).map(e => e.runtime_range && e.runtime_range.start_line).filter(Boolean);
      return r.length ? Math.min(...r) : 1e9;
    };
    const orderedSections = [...graph.sections].sort((a, b) => sectionSort(a) - sectionSort(b) || a.name.localeCompare(b.name));
    function isCaptureInput(s) {
      const pointer = String((s && s.pointer) || "").replace(/\\/g, "/");
      return !!s && (s.kind === "capture" || s.kind === "memory" || s.layer === "capture" ||
        pointer.startsWith("capture/") || pointer.includes("/capture/"));
    }
    const orderedSources = [...graph.sources].sort((a, b) => {
      const ko = ["source", "capture", "memory", "project"];
      return ko.indexOf(a.kind) - ko.indexOf(b.kind) || a.label.localeCompare(b.label);
    });
    const captureSources = orderedSources.filter(isCaptureInput);
    const canonicalSources = orderedSources.filter(s => !isCaptureInput(s));

    // ---- gap model (deduped, severity-ranked) ----
    function gaps() {
      const out = [];
      // Sections already named by a compiler-emitted gap should not be
      // double-counted by the synthesized relation gaps below.
      const flaggedSections = new Set(graph.unexplained.map(u => u.section).filter(Boolean));
      graph.unexplained.forEach(u => {
        const sev = (u.type === "missing_source_relation" || u.type === "unresolved_source_pointer"
          || u.type === "missing_compile_mapping") ? "high" : "med";
        out.push({
          type: u.type, sev,
          object: u.section || u.config || u.source || "workspace",
          target: nodeForName(u.section) || nodeForRuntime(u.config),
          msg: u.message || JSON.stringify(u),
        });
      });
      graph.sections.filter(s => s.relation_state === "uncertain" && !flaggedSections.has(s.name)).forEach(s => {
        out.push({ type: "uncertain_relation", sev: "med", object: s.name, target: s,
          msg: s.relation_note || "section source relation is uncertain" });
      });
      graph.sections.filter(s => s.relation_state === "declared" && !flaggedSections.has(s.name)).forEach(s => {
        out.push({ type: "declared_without_derive_record", sev: "low", object: s.name, target: s,
          msg: s.relation_note || "declares upstream pointers, but no exact derive record exists" });
      });
      const rank = { high: 0, med: 1, low: 2 };
      out.sort((a, b) => rank[a.sev] - rank[b.sev]);
      out.forEach((g, i) => g.id = "GAP-" + String(i + 1).padStart(3, "0"));
      return out;
    }
    const nodeForName = (name) => name ? graph.sections.find(s => s.name === name) : null;
    const nodeForRuntime = (cfg) => cfg ? graph.runtimes.find(r => r.config === cfg) : null;

    // ---- metrics ----
    function metrics() {
      const totalRt = rtEdges.length;
      const exactRt = rtEdges.filter(e => e.status === "exact").length;
      const realSections = graph.sections.filter(s => s.relation_state !== "wrapper");
      const backed = realSections.filter(s => s.relation_state === "derived" || s.relation_state === "declared").length;
      return {
        runtimes: graph.runtimes.length,
        sections: graph.sections.length,
        exactPct: totalRt ? Math.round(exactRt / totalRt * 100) : 0,
        backedPct: realSections.length ? Math.round(backed / realSections.length * 100) : 0,
        gaps: gaps().length,
      };
    }

    // ---- icons ----
    const ICONS = {
      source: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h11l5 5v11a0 0 0 0 1 0 0H4z"/><path d="M14 4v5h5"/></svg>',
      capture: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 7h3l2-2h4l2 2h3v12H5z"/><circle cx="12" cy="13" r="3"/></svg>',
      memory: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a4 4 0 0 0-4 4v0a3 3 0 0 0-1 5.8V17a3 3 0 0 0 5 2 3 3 0 0 0 5-2v-4.2A3 3 0 0 0 16 7v0a4 4 0 0 0-4-4z"/></svg>',
      project: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 7l9-4 9 4-9 4z"/><path d="M3 7v10l9 4 9-4V7"/></svg>',
      section: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/></svg>',
      runtime: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v12H4z"/><path d="M8 21h8M9 9l2 2-2 2M13 13h3"/></svg>',
      external: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 3l-9 9"/><path d="M15 3h6v6"/><path d="M21 14v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5"/></svg>',
    };

    // ---- DOM render: lanes ----
    const laneExternal = document.getElementById("lane-external");
    const laneCaptures = document.getElementById("lane-captures");
    const laneSources = document.getElementById("lane-sources");
    const laneSections = document.getElementById("lane-sections");
    const laneRuntimes = document.getElementById("lane-runtimes");

    const CHG_SIGN = { added: "+", modified: "~", removed: "−" };
    function nodeEl(n, kind, inner) {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "node";
      const chg = n.change && n.change !== "unchanged" ? n.change : "";
      if (chg) {
        el.classList.add("ch-" + chg);
        inner += '<span class="chg chg-' + chg + '">' + CHG_SIGN[chg] + "</span>";
      }
      el.dataset.id = n.id;
      el.dataset.status = nodeStatus(n);
      el.dataset.change = chg || "unchanged";
      el.dataset.search = (n.name || n.label || "") + " " + (n.pointer || n.path || "") + " " + (n.config || "");
      el.innerHTML = inner;
      el.addEventListener("click", () => { cancelHoverPreview(); hideHoverCard(); select(n.id); });
      el.addEventListener("mouseenter", () => { hover(n.id); scheduleHoverPreview(() => showNodePreview(n.id, el)); });
      el.addEventListener("mouseleave", () => { hover(null); cancelHoverPreview(); scheduleHideHoverCard(); });
      return el;
    }
    function statusDot(s) { return '<span class="sdot" style="background:' + (STATUS_COLOR[s] || "var(--muted)") + '"></span>'; }
    function tag(text, color) {
      return '<span class="tag">' + (color ? '<span class="d" style="background:' + color + '"></span>' : "") + esc(text) + "</span>";
    }

    // Architectural layers are derived in the compiler (path prefix / frontmatter).
    // Both source and section lanes group by layer so the graph reads as an
    // architecture, not a flat list.
    const LAYER_PRIORITY = { base: 0, core: 1, source: 2, customers: 3, instances: 4,
      skills: 5, docs: 6, config: 7, capture: 8, memory: 9, workbench: 10, project: 10, "runtime-build": 11 };
    function layerRank(l) { return l in LAYER_PRIORITY ? LAYER_PRIORITY[l] : (String(l).startsWith("external") ? 90 : 50); }
    function groupByLayer(items) {
      const groups = new Map();
      items.forEach(it => { const l = it.layer || "core"; (groups.get(l) || groups.set(l, []).get(l)).push(it); });
      return [...groups.entries()].sort((a, b) => layerRank(a[0]) - layerRank(b[0]) || a[0].localeCompare(b[0]));
    }
    function groupLabel(lane, layer, count) {
      const lab = document.createElement("div");
      lab.className = "lane-group-label";
      lab.innerHTML = esc(layer) + ' <span class="grp-count">' + count + "</span>";
      lane.appendChild(lab);
    }

    function renderSources() {
      groupByLayer(canonicalSources).forEach(([layer, items]) => {
        groupLabel(laneSources, layer, items.length);
        items.forEach(s => {
          const st = nodeStatus(s);
          laneSources.appendChild(nodeEl(s, "source",
            '<div class="row">' +
              '<span class="kind-ic" style="background:' + (KIND_COLOR[s.kind] || "#8f969e") + '">' + (ICONS[s.kind] || ICONS.source) + "</span>" +
              '<span class="name">' + esc(s.label) + "</span>" + statusDot(st) +
            "</div>" +
            '<div class="ptr">' + esc(s.pointer) + "</div>" +
            (s.status === "missing" ? '<div class="submeta" style="color:var(--missing)">未解析 · missing</div>' : "")
          ));
        });
      });
    }
    function renderCaptures() {
      if (!captureSources.length) return;
      laneCaptures.hidden = false;
      groupByLayer(captureSources).forEach(([layer, items]) => {
        groupLabel(laneCaptures, layer, items.length);
        items.forEach(s => {
          const st = nodeStatus(s);
          laneCaptures.appendChild(nodeEl(s, "source",
            '<div class="row">' +
              '<span class="kind-ic" style="background:' + (KIND_COLOR[s.kind] || "#8f969e") + '">' + (ICONS[s.kind] || ICONS.capture) + "</span>" +
              '<span class="name">' + esc(s.label) + "</span>" + statusDot(st) +
            "</div>" +
            '<div class="ptr">' + esc(s.pointer) + "</div>" +
            (inputEdgesFrom(s.id).length ? '<div class="submeta"><span class="meta-mark" style="color:var(--declared)">→ KB</span></div>' : "")
          ));
        });
      });
    }
    function renderSections() {
      groupByLayer(orderedSections).forEach(([layer, items]) => {
        groupLabel(laneSections, layer, items.length);
        items.forEach(s => {
          const rs = s.relation_state;
          const cstat = sectionCompile(s.id);
          const rtMark = rtEdgesFrom(s.id).length
            ? '<span class="meta-mark" style="color:' + (cstat === "exact" ? "var(--exact)" : "var(--uncertain)") + '">' + (cstat === "exact" ? "→ exact" : "→ runtime?") + "</span>"
            : "";
          laneSections.appendChild(nodeEl(s, "section",
            '<div class="row">' +
              '<span class="kind-ic" style="background:#5f6670">' + ICONS.section + "</span>" +
              '<span class="name">' + esc(s.name) + "</span>" + statusDot(rs) +
            "</div>" +
            '<div class="submeta">' + esc(rs) + (rtMark ? '<span class="dotsep">·</span>' + rtMark : "") + "</div>"
          ));
        });
      });
    }
    function renderRuntimes() {
      graph.runtimes.forEach(r => {
        const st = nodeStatus(r);
        const mc = (r.mirrors || []).length;
        const el = nodeEl(r, "runtime",
          '<div class="row">' +
            '<span class="kind-ic" style="background:#5f7d7a">' + ICONS.runtime + "</span>" +
            '<span class="name">' + esc(r.config) + "</span>" + statusDot(st) +
          "</div>" +
          '<div class="ptr">' + esc(r.path) + "</div>" +
          '<div class="submeta"><span class="meta-mark" style="color:var(--exact)">' + esc(r.target) + "</span>" + (mc ? '<span class="dotsep">·</span>' + mc + " mirror" : "") + "</div>"
        );
        laneRuntimes.appendChild(el);
      });
    }
    function renderExternals() {
      externals.forEach(x => {
        const into = importEdgesFrom(x.id).length;
        const el = nodeEl(x, "external",
          '<div class="row">' +
            '<span class="kind-ic" style="background:#73677d">' + ICONS.external + "</span>" +
            '<span class="name">' + esc(x.label) + "</span>" + statusDot(x.status) +
          "</div>" +
          '<div class="submeta"><span class="meta-mark" style="color:' + STATUS_COLOR[x.status] + '">' + (x.status === "pending" ? "待导入" : "已导入") + "</span><span class=\"dotsep\">·</span>" + (x.file_count || into) + " capture</div>"
        );
        laneExternal.appendChild(el);
      });
    }

    // ---- SVG links ----
    const svg = document.getElementById("links");
    const chips = document.getElementById("edge-chips");
    const lanes = document.getElementById("lanes");
    const graphEmpty = document.getElementById("graph-empty");
    const canvasEl = document.getElementById("canvas");
    let pathByEdge = new Map();
    function elFor(id) { return lanes.querySelector('.node[data-id="' + cssEsc(id) + '"]'); }
    function cssEsc(s) { return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/"/g, '\\"'); }
    function edgeBrief(e) {
      if (e.relation === "external_to_source") return e.status === "pending" ? "待导入" : "导入";
      if (e.relation === "input_to_source") return "整合";
      return e.status || "—";
    }
    function edgeLabel(e) {
      if (e.relation === "section_to_runtime") return "Section→Runtime";
      if (e.relation === "external_to_source") return "Import";
      if (e.relation === "input_to_source") return "Input→Source";
      return "Source→Section";
    }
    function showEdgeChip(e) {
      if (e.relation === "input_to_source" || e.relation === "external_to_source") return true;
      if (e.change && e.change !== "unchanged") return true;
      return e.status === "uncertain" || e.status === "missing";
    }
    function refreshLaneColumns() {
      const count = [...lanes.querySelectorAll(".lane")].filter(lane => !lane.hidden && !lane.classList.contains("filtered-empty")).length;
      lanes.style.setProperty("--lane-count", String(Math.max(1, count)));
      const minWidth = Math.max(1, count) * 292 + Math.max(0, count - 1) * 72;
      lanes.style.setProperty("--lane-min-width", minWidth + "px");
    }

    function drawLinks() {
      svg.innerHTML = "";
      chips.innerHTML = "";
      pathByEdge = new Map();
      const wrap = lanes.getBoundingClientRect();
      const NS = "http://www.w3.org/2000/svg";
      graph.edges.forEach(e => {
        const a = elFor(e.from_id), b = elFor(e.to_id);
        if (!a || !b) return;
        if (a.classList.contains("dim") || b.classList.contains("dim")) return;
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        const x1 = ra.right - wrap.left, y1 = ra.top - wrap.top + ra.height / 2;
        const x2 = rb.left - wrap.left, y2 = rb.top - wrap.top + rb.height / 2;
        const dx = Math.max(40, (x2 - x1) * 0.5);
        const d = "M" + x1 + "," + y1 + " C" + (x1 + dx) + "," + y1 + " " + (x2 - dx) + "," + y2 + " " + x2 + "," + y2;
        const p = document.createElementNS(NS, "path");
        p.setAttribute("d", d);
        p.setAttribute("fill", "none");
        p.setAttribute("stroke", "var(--line)");
        p.setAttribute("stroke-width", "1.5");
        p.setAttribute("stroke-linecap", "round");
        const baseDash = e.change === "removed" ? "2 4" : ((e.status === "uncertain" || e.status === "missing") ? "4 4" : "");
        if (baseDash) p.setAttribute("stroke-dasharray", baseDash);
        p.dataset.dash = baseDash;
        p.dataset.from = e.from_id;
        p.dataset.to = e.to_id;
        p.dataset.status = e.status;
        p.dataset.edge = e.id;
        svg.appendChild(p);
        // Transparent wide hit-path so the edge itself is an easy click/hover target.
        const hit = document.createElementNS(NS, "path");
        hit.setAttribute("d", d);
        hit.setAttribute("fill", "none");
        hit.setAttribute("stroke", "transparent");
        hit.setAttribute("stroke-width", "24");
        hit.setAttribute("pointer-events", "stroke");
        hit.dataset.hit = e.id;
        hit.style.cursor = "pointer";
        hit.addEventListener("click", (ev) => { ev.stopPropagation(); cancelHoverPreview(); hideHoverCard(); selectEdge(e.id); });
        hit.addEventListener("mouseenter", () => { hoverEdgeId = e.id; applyHighlight(); scheduleHoverPreview(() => showEdgePreview(e.id, hit)); });
        hit.addEventListener("mouseleave", () => { hoverEdgeId = null; applyHighlight(); cancelHoverPreview(); scheduleHideHoverCard(); });
        svg.appendChild(hit);
        // Only show chips for review-relevant edges. Routine exact/derived
        // edges remain hoverable through the wide transparent hit-path, but
        // their labels no longer pile up in the middle of dense lanes.
        if (showEdgeChip(e)) {
          const chip = document.createElement("div");
          chip.className = "edge-chip";
          chip.dataset.edge = e.id;
          chip.dataset.from = e.from_id;
          chip.dataset.to = e.to_id;
          chip.style.left = ((x1 + x2) / 2) + "px";
          chip.style.top = ((y1 + y2) / 2) + "px";
          chip.title = edgeLabel(e) + " · " + (e.evidence || "");
          chip.innerHTML = '<span class="d" style="background:' + (STATUS_COLOR[e.status] || "var(--muted)") + '"></span>' + esc(edgeBrief(e));
          chip.addEventListener("click", (ev) => { ev.stopPropagation(); cancelHoverPreview(); hideHoverCard(); selectEdge(e.id); });
          chip.addEventListener("mouseenter", () => { hoverEdgeId = e.id; applyHighlight(); scheduleHoverPreview(() => showEdgePreview(e.id, chip)); });
          chip.addEventListener("mouseleave", () => { hoverEdgeId = null; applyHighlight(); cancelHoverPreview(); scheduleHideHoverCard(); });
          chips.appendChild(chip);
        }
        const key = e.from_id + "|" + e.to_id;
        (pathByEdge.get(key) || pathByEdge.set(key, []).get(key)).push(p);
      });
      applyHighlight();
    }

    // ---- highlight / selection ----
    let selectedId = null, hoverId = null, keyboardFocusId = null, inspectorMax = false, activeTab = 0, panelOpen = false;
    let selectedEdgeId = null, hoverEdgeId = null;
    const edgeById = new Map(graph.edges.map(e => [e.id, e]));

    // Detail panel as tabs: [label, paneHTML] pairs; first is active by default.
    function tabbed(tabs) {
      const bar = '<div class="tabs">' + tabs.map((t, i) =>
        '<button class="tab' + (i === activeTab ? " active" : "") + '" data-tab="' + i + '">' +
        esc(t[0]) + (t[2] != null ? '<span class="n">' + t[2] + "</span>" : "") + "</button>").join("") + "</div>";
      const panes = '<div class="tabpanes">' + tabs.map((t, i) =>
        '<section class="tabpane" data-pane="' + i + '"' + (i === activeTab ? "" : " hidden") + ">" + t[1] + "</section>").join("") + "</div>";
      return bar + panes;
    }
    function lineage(id) {
      const set = new Set([id]);
      const up = [id]; while (up.length) { const c = up.pop(); (inAdj.get(c) || []).forEach(p => { if (!set.has(p)) { set.add(p); up.push(p); } }); }
      const dn = [id]; while (dn.length) { const c = dn.pop(); (outAdj.get(c) || []).forEach(p => { if (!set.has(p)) { set.add(p); dn.push(p); } }); }
      return set;
    }
    function applyHighlight() {
      const edge = hoverEdgeId ? edgeById.get(hoverEdgeId) : (selectedEdgeId ? edgeById.get(selectedEdgeId) : null);
      let focus = null;
      if (edge) focus = new Set([edge.from_id, edge.to_id]);
      else { const focusId = hoverId || keyboardFocusId || selectedId; focus = focusId ? lineage(focusId) : null; }
      lanes.querySelectorAll(".node").forEach(el => {
        el.classList.toggle("sel", !edge && el.dataset.id === selectedId);
        el.classList.toggle("kbd", !edge && el.dataset.id === keyboardFocusId && el.dataset.id !== selectedId);
        el.classList.toggle("hit", !!focus && focus.has(el.dataset.id) && (edge || el.dataset.id !== selectedId));
      });
      svg.querySelectorAll("path[data-edge]").forEach(p => {
        const isSel = edge && p.dataset.edge === edge.id;
        const on = isSel || (focus && focus.has(p.dataset.from) && focus.has(p.dataset.to) && !edge);
        p.classList.toggle("flow", !!isSel);
        const baseDash = p.dataset.dash || "";
        if (isSel) {
          p.setAttribute("stroke", "var(--accent)");
          p.setAttribute("stroke-width", "3");
          p.setAttribute("stroke-dasharray", "7 6");
          p.setAttribute("opacity", "1");
        } else if (on) {
          p.setAttribute("stroke", STATUS_COLOR[p.dataset.status] || "var(--accent)");
          p.setAttribute("stroke-width", "2.4");
          p.setAttribute("stroke-dasharray", baseDash);
          p.setAttribute("opacity", "1");
        } else {
          p.setAttribute("stroke", "var(--border-strong)");
          p.setAttribute("stroke-width", "2.25");
          p.setAttribute("stroke-dasharray", baseDash);
          p.setAttribute("opacity", focus ? "0.22" : "0.85");
        }
      });
      chips.querySelectorAll(".edge-chip").forEach(c => {
        const isSel = edge && c.dataset.edge === edge.id;
        const on = isSel || (focus && focus.has(c.dataset.from) && focus.has(c.dataset.to) && !edge);
        c.classList.toggle("on", !!isSel);
        c.classList.toggle("dim", !!focus && !on);
      });
    }
    function hover(id) { hoverId = id; applyHighlight(); }
    // Hover is a local preview; click pins full detail into the right drawer.
    // This keeps the dense graph scannable and avoids throwing the user's eye
    // across the monitor for every incidental hover.
    let hoverTimer = null, hoverHideTimer = null;
    function scheduleHoverPreview(fn) { clearTimeout(hoverTimer); hoverTimer = setTimeout(fn, 130); }
    function cancelHoverPreview() { clearTimeout(hoverTimer); }
    function scheduleHideHoverCard() {
      clearTimeout(hoverHideTimer);
      hoverHideTimer = setTimeout(hideHoverCard, 180);
    }
    function cancelHideHoverCard() { clearTimeout(hoverHideTimer); }
    function previewCode(text, startLine, caption, maxLines, extraClass) {
      const all = String(text || "").split("\n");
      const lines = all.slice(0, maxLines || 10);
      const start = startLine || 1;
      const rows = lines.map((ln, i) =>
        '<div class="preview-line"><span class="ln">' + (start + i) + '</span><span class="lc">' + esc(ln || " ") + "</span></div>"
      ).join("");
      const more = all.length > lines.length ? '<div class="preview-more">完整内容在右侧详情</div>' : "";
      return '<div class="preview-code' + (extraClass ? " " + extraClass : "") + '">' + (caption ? '<div class="preview-cap">' + esc(caption) + "</div>" : "") + rows + more + "</div>";
    }
    function previewDiff(oldText, newText, caption, maxRows) {
      const raw = lineDiffRows(oldText, newText);
      const limit = maxRows || 14;
      const firstChange = raw.findIndex(row => row.type !== "ctx");
      let start = 0, end = Math.min(raw.length, limit);
      if (firstChange >= 0) {
        const context = 2;
        start = Math.max(0, firstChange - context);
        let lastChange = firstChange, after = 0;
        for (let i = firstChange + 1; i < raw.length; i++) {
          if (raw[i].type !== "ctx") { lastChange = i; after = 0; continue; }
          after++;
          if (after >= context) break;
        }
        end = Math.min(raw.length, Math.max(lastChange + context + 1, start + 1));
        if (end - start > limit) end = start + limit;
      }
      const rows = raw.slice(start, end)
        .map(row => {
          const cls = row.type === "add" ? " d-add" : row.type === "del" ? " d-del" : "";
          return '<div class="preview-line' + cls + '"><span class="ln">' + esc(diffLineLabel(row)) + '</span><span class="lc">' + esc(row.text || " ") + "</span></div>";
        }).join("");
      const located = firstChange > 0 ? '<div class="preview-more">已定位到第 ' + (raw[firstChange].newNo || raw[firstChange].oldNo || 1) + " 行附近的变更 hunk</div>" : "";
      const more = (start > 0 || end < raw.length) ? '<div class="preview-more">完整 diff 在右侧详情</div>' : "";
      return '<div class="preview-code preview-diff">' + (caption ? '<div class="preview-cap">' + esc(caption) + " · diff hunk</div>" : "") + located + rows + more + "</div>";
    }
    function previewHeader(kind, title, subtitle, status) {
      return '<div class="preview-head">' +
        '<p class="preview-eyebrow">' + (status ? statusDot(status) : "") + esc(kind) + "</p>" +
        '<h3 class="preview-title">' + esc(title || "—") + "</h3>" +
        (subtitle ? '<p class="preview-sub">' + esc(subtitle) + "</p>" : "") +
      "</div>";
    }
    function previewGrid(rows) {
      return '<div class="preview-grid">' + rows.filter(Boolean).map(([k, v]) =>
        '<div class="preview-row"><span class="preview-k">' + esc(k) + '</span><span class="preview-v">' + v + "</span></div>"
      ).join("") + "</div>";
    }
    function previewMeta(items) {
      return '<div class="preview-meta">' + items.filter(Boolean).map(([k, v, color]) =>
        '<span class="preview-chip">' + (color ? '<span class="d" style="width:7px;height:7px;border-radius:50%;background:' + color + '"></span>' : "") +
        '<b>' + esc(k) + "</b>" + esc(v == null ? "" : String(v)) + "</span>"
      ).join("") + "</div>";
    }
    function previewFlow(nodes) {
      const links = nodes.filter(Boolean).map(n => nodelink(n, nodeStatus(n))).join('<span class="lin-arrow">→</span>');
      return links ? '<div class="preview-flow">' + links + "</div>" : "";
    }
    function previewCompare(fromTitle, fromText, fromStart, toTitle, toText, toStart, maxLines) {
      return '<div class="preview-compare">' +
        '<div class="preview-pane"><p class="preview-pane-title"><span>From</span><span>' + esc(fromTitle || "") + "</span></p>" +
          (fromText ? previewCode(fromText, fromStart || 1, "", maxLines || 10, "compact") : '<div class="empty">无可用原文。</div>') + "</div>" +
        '<div class="preview-pane"><p class="preview-pane-title"><span>To</span><span>' + esc(toTitle || "") + "</span></p>" +
          (toText ? previewCode(toText, toStart || 1, "", maxLines || 10, "compact") : '<div class="empty">无可用产物。</div>') + "</div>" +
      "</div>";
    }
    function changePreview(node, text, startLine, caption) {
      if (node && node.change === "modified" && node.prev_content != null) return previewDiff(node.prev_content, text, caption, 16);
      const isRemoved = node && node.change === "removed";
      return previewCode(isRemoved ? (node.prev_content || text || "") : text, startLine, caption, 12);
    }
    function sourcePreviewHTML(s) {
      const downstream = [...inputEdgesFrom(s.id), ...srcEdgesFrom(s.id)];
      const consumers = downstream.map(e => byId.get(e.to_id));
      return previewHeader((KIND_LABEL[s.kind] || s.kind || "Source") + " Source", s.label, s.pointer, nodeStatus(s)) +
        previewMeta([
          ["change ", s.change && s.change !== "unchanged" ? (CHG_LABEL[s.change] || s.change) : "—", STATUS_COLOR[nodeStatus(s)]],
          ["status ", s.status === "missing" ? "missing" : "resolved"],
          ["to ", consumers.length + " downstream"],
          ["layer ", s.layer || "core"],
        ]) +
        '<div class="preview-section"><h4>' + (s.change && s.change !== "unchanged" ? "Review diff / 内容变化" : "内容摘录") + "</h4>" +
          changePreview(s, s.content_excerpt || "", s.position && s.position.start_line, s.pointer) + "</div>" +
        previewFlow([s, consumers[0]]);
    }
    function sectionPreviewHTML(s) {
      const sources = srcEdgesTo(s.id).map(e => byId.get(e.from_id));
      const runtimes = rtEdgesFrom(s.id).map(e => byId.get(e.to_id));
      return previewHeader((s.type || "Section") + " Section", s.name, s.relation_note || "", s.relation_state) +
        previewMeta([
          ["change ", s.change && s.change !== "unchanged" ? (CHG_LABEL[s.change] || s.change) : "—", STATUS_COLOR[s.relation_state]],
          ["relation ", s.relation_state || "—"],
          ["from ", sources.length + " source"],
          ["to ", runtimes.length + " runtime"],
        ]) +
        '<div class="preview-section"><h4>' + (s.change && s.change !== "unchanged" ? "Review diff / Section 变化" : "Section 内容") + "</h4>" +
          changePreview(s, s.content, s.position && s.position.start_line, s.name) + "</div>" +
        previewFlow([sources[0], s, runtimes[0]]);
    }
    function runtimePreviewHTML(r) {
      const maps = rtEdgesTo(r.id).slice().sort((a, b) =>
        ((a.runtime_range && a.runtime_range.start_line) || 1e9) - ((b.runtime_range && b.runtime_range.start_line) || 1e9));
      const firstSection = maps[0] ? byId.get(maps[0].from_id) : null;
      return previewHeader((r.target || "Runtime").toUpperCase() + " Runtime", r.config, r.path, nodeStatus(r)) +
        previewMeta([
          ["change ", r.change && r.change !== "unchanged" ? (CHG_LABEL[r.change] || r.change) : "—", STATUS_COLOR[nodeStatus(r)]],
          ["status ", nodeStatus(r)],
          ["mapped ", maps.length + " section"],
          ["mirror ", ((r.mirrors || []).length || 0) + ""],
        ]) +
        '<div class="preview-section"><h4>' + (r.change && r.change !== "unchanged" ? "Review diff / Runtime 变化" : "Runtime 摘录") + "</h4>" +
          changePreview(r, r.content, 1, r.path) + "</div>" +
        previewFlow([firstSection, r]);
    }
    function externalPreviewHTML(x) {
      const imports = importEdgesFrom(x.id);
      const first = imports[0] ? byId.get(imports[0].to_id) : null;
      return previewHeader("External Input", x.label, "capture → review → import", x.status) +
        previewMeta([
          ["status ", x.status || "—", STATUS_COLOR[x.status]],
          ["files ", (x.file_count || imports.length) + " capture"],
        ]) +
        previewFlow([x, first]) +
        '<div class="preview-section"><h4>导入说明</h4><p class="preview-sub" style="font-family:var(--font)">只展示 capture frontmatter 记录的来源，不直接读取外部语料原文。</p></div>';
    }
    function edgePreviewHTML(e) {
      const from = byId.get(e.from_id), to = byId.get(e.to_id);
      const isRt = e.relation === "section_to_runtime";
      const rel = isRt ? "Section → Runtime" : e.relation === "external_to_source" ? "External Input → Capture" : e.relation === "input_to_source" ? "Input / Capture → Canonical Source" : "Source → Section";
      let fromText = "", toText = "", fromStart = 1, toStart = 1, fromTitle = "", toTitle = "", method;
      if (e.relation === "section_to_runtime") {
        const rng = e.runtime_range;
        fromText = (from && from.content) || "";
        fromStart = (from && from.position && from.position.start_line) || 1;
        fromTitle = (from && from.name) || "section";
        toText = (rng && rng.start_line && to) ? String(to.content || "").split("\n").slice(rng.start_line - 1, rng.end_line).join("\n") : "";
        toStart = (rng && rng.start_line) || 1;
        toTitle = (to && to.config ? to.config : "runtime") + (rng && rng.start_line ? " lines " + rng.start_line + (rng.end_line !== rng.start_line ? "-" + rng.end_line : "") : "");
        method = { kind: "compiler exact copy", color: "var(--exact)", note: "section block → runtime 命中行" };
      } else {
        fromText = (from && (from.content_excerpt || from.content)) || "";
        fromStart = (from && from.position && from.position.start_line) || 1;
        fromTitle = (from && (from.pointer || from.name || from.label)) || "from";
        toText = (to && (to.content || to.content_excerpt)) || "";
        toStart = (to && to.position && to.position.start_line) || 1;
        toTitle = (to && (to.name || to.pointer || to.label)) || "to";
        method = e.relation === "external_to_source"
          ? { kind: "capture import", color: "var(--declared)", note: "frontmatter 记录外部来源；不读取外部原文" }
          : e.relation === "input_to_source"
          ? { kind: "KB source declaration", color: "var(--declared)", note: "KB frontmatter 声明该 clipping/capture 被整合进这份知识库" }
          : classifyExtraction(fromText, toText);
      }
      return previewHeader(rel, (from && (from.name || from.label || from.config)) + " → " + (to && (to.name || to.label || to.config)), e.evidence || "", e.status) +
        previewMeta([
          ["method ", method.kind, method.color],
          ["status ", e.status || "—", STATUS_COLOR[e.status]],
          ["confidence ", e.confidence || "—"],
        ]) +
        '<p class="preview-sub" style="font-family:var(--font);margin-top:6px">' + esc(method.note || "") + "</p>" +
        previewCompare(fromTitle, fromText, fromStart, toTitle, toText, toStart, isRt ? 10 : 11) +
        previewFlow([from, to]);
    }
    function nodePreviewHTML(n) {
      if (!n) return '<div class="empty">节点不存在。</div>';
      if (n.kind === "external") return externalPreviewHTML(n);
      if (graph.sources.includes(n)) return sourcePreviewHTML(n);
      if (graph.runtimes.includes(n)) return runtimePreviewHTML(n);
      return sectionPreviewHTML(n);
    }
    function showNodePreview(id, anchor) {
      const n = byId.get(id);
      if (!n) return;
      showHoverCard(anchor, nodePreviewHTML(n));
    }
    function showEdgePreview(eid, anchor) {
      const e = edgeById.get(eid);
      if (!e) return;
      showHoverCard(anchor, edgePreviewHTML(e));
    }
    function showHoverCard(anchor, html) {
      cancelHideHoverCard();
      hoverCard.innerHTML = html + '<p class="hover-hint">Hover 一屏预览关键内容；Enter/单击固定到右侧完整详情。</p>';
      hoverCard.hidden = false;
      hoverCard.style.left = "0px";
      hoverCard.style.top = "0px";
      const splitRect = splitEl.getBoundingClientRect();
      const anchorRect = anchor.getBoundingClientRect();
      const cardRect = hoverCard.getBoundingClientRect();
      const gap = 12;
      let left = anchorRect.right - splitRect.left + gap;
      if (left + cardRect.width > splitRect.width - gap) {
        left = anchorRect.left - splitRect.left - cardRect.width - gap;
      }
      if (left < gap) {
        left = Math.min(Math.max(gap, anchorRect.left - splitRect.left), Math.max(gap, splitRect.width - cardRect.width - gap));
      }
      let top = anchorRect.top - splitRect.top + Math.min(10, Math.max(0, anchorRect.height / 2 - 12));
      if (top + cardRect.height > splitRect.height - gap) top = splitRect.height - cardRect.height - gap;
      if (top < gap) top = gap;
      hoverCard.style.left = Math.round(left) + "px";
      hoverCard.style.top = Math.round(top) + "px";
      bindHoverCard();
    }
    function hideHoverCard() {
      cancelHideHoverCard();
      hoverCard.hidden = true;
      hoverCard.innerHTML = "";
    }
    function bindHoverCard() {
      hoverCard.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
        hoverCard.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
        hoverCard.querySelectorAll(".tabpane").forEach(p => { p.hidden = Number(p.dataset.pane) !== Number(t.dataset.tab); });
      }));
      hoverCard.querySelectorAll("[data-goto]").forEach(b => {
        const id = b.dataset.goto;
        if (!id) return;
        b.addEventListener("click", () => { hideHoverCard(); select(id); });
      });
    }
    function select(id) {
      if (selectedId === id && !selectedEdgeId && panelOpen) return;
      activeTab = 0;
      selectedId = id;
      selectedEdgeId = null;
      keyboardFocusId = null;
      applyHighlight();
      renderInspector();
      setPanel(true);
    }
    function selectEdge(eid) {
      if (selectedEdgeId === eid && panelOpen) return;
      activeTab = 0;
      selectedEdgeId = eid;
      selectedId = null;
      keyboardFocusId = null;
      applyHighlight();
      renderInspector();
      setPanel(true);
    }
    function visibleNodeEls() {
      return [...lanes.querySelectorAll(".node")].filter(el => !el.classList.contains("dim") && el.offsetParent !== null);
    }
    function visibleLaneGroups() {
      return [...lanes.querySelectorAll(".lane")]
        .filter(lane => !lane.hidden && lane.offsetParent !== null)
        .map(lane => ({
          lane,
          nodes: [...lane.querySelectorAll(".node")].filter(el => !el.classList.contains("dim") && el.offsetParent !== null)
        }))
        .filter(g => g.nodes.length);
    }
    function centerY(el) {
      const r = el.getBoundingClientRect();
      return r.top + r.height / 2;
    }
    function pickClosestY(nodes, y) {
      return nodes.slice().sort((a, b) => {
        const da = Math.abs(centerY(a) - y);
        const db = Math.abs(centerY(b) - y);
        if (da !== db) return da - db;
        return a.getBoundingClientRect().top - b.getBoundingClientRect().top;
      })[0];
    }
    function moveKeyboardFocus(dir) {
      const nodes = visibleNodeEls();
      if (!nodes.length) return;
      const rawCurrent = elFor(keyboardFocusId || selectedId || hoverId);
      const current = rawCurrent && nodes.includes(rawCurrent) ? rawCurrent : nodes[0];
      let next = current;
      const groups = visibleLaneGroups();
      const currentLane = current.closest(".lane");
      const groupIndex = groups.findIndex(g => g.lane === currentLane);
      if (dir === "up" || dir === "down") {
        const sameLane = groupIndex >= 0 ? groups[groupIndex].nodes : nodes;
        const ordered = sameLane.slice().sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
        const i = ordered.indexOf(current);
        const j = i + (dir === "down" ? 1 : -1);
        if (j >= 0 && j < ordered.length) next = ordered[j];
      } else if (groupIndex >= 0) {
        const j = groupIndex + (dir === "right" ? 1 : -1);
        if (j >= 0 && j < groups.length) next = pickClosestY(groups[j].nodes, centerY(current));
      }
      keyboardFocusId = next.dataset.id;
      selectedEdgeId = null;
      hoverEdgeId = null;
      hoverId = keyboardFocusId;
      applyHighlight();
      next.scrollIntoView({ block: "nearest", inline: "nearest" });
      showNodePreview(keyboardFocusId, next);
    }
    function pinKeyboardFocus() {
      if (keyboardFocusId) select(keyboardFocusId);
    }

    // ---- inspector ----
    const inspBody = document.getElementById("insp-body");
    function pos(p) {
      if (!p) return "—";
      const ln = p.start_line ? (":" + p.start_line + (p.end_line && p.end_line !== p.start_line ? "-" + p.end_line : "")) : "";
      return p.path + ln + (p.exists === false ? "（missing）" : "");
    }
    function codeBlock(text, startLine, caption, hlRange) {
      const lines = String(text || "").split("\n");
      const start = startLine || 1;
      const rows = lines.map((ln, i) => {
        const no = start + i;
        const hl = hlRange && no >= hlRange[0] && no <= hlRange[1] ? " hl" : "";
        return '<div class="code-line' + hl + '"><span class="ln">' + no + '</span><span class="lc">' + esc(ln || " ") + "</span></div>";
      }).join("");
      return '<div class="code">' + (caption ? '<div class="code-cap">' + caption + "</div>" : "") +
        '<div class="code-scroll">' + rows + "</div></div>";
    }
    function nodelink(n, statusOverride) {
      if (!n) return "";
      const st = statusOverride || nodeStatus(n);
      const label = n.name || n.label || n.config;
      return '<button class="nodelink" data-goto="' + esc(n.id) + '"><span class="d" style="background:' +
        (STATUS_COLOR[st] || "var(--muted)") + '"></span><span class="name">' + esc(label) + "</span></button>";
    }
    function eyebrow(text, status) {
      return '<p class="insp-eyebrow">' + (status ? '<span class="sdot" style="width:8px;height:8px;box-shadow:none;background:' +
        (STATUS_COLOR[status] || "var(--muted)") + '"></span>' : "") + esc(text) + "</p>";
    }

    // Inspector width is user-controlled (drag the divider, persisted). When the
    // docked panel is wide enough — or maximized — section detail lays out as a
    // full three-column lineage instead of a single cramped column.
    const inspectorEl = document.getElementById("inspector");
    let wideLayout = false;
    function isWide() { return inspectorMax || inspectorEl.getBoundingClientRect().width >= 820; }
    function replayPanelIn() {
      inspBody.classList.remove("anim"); void inspBody.offsetWidth; inspBody.classList.add("anim");
    }
    function renderInspector() {
      wideLayout = isWide();
      if (selectedEdgeId) inspBody.innerHTML = edgeHTML(edgeById.get(selectedEdgeId));
      else {
        const n = selectedId ? byId.get(selectedId) : null;
        if (!n) inspBody.innerHTML = overviewHTML();
        else if (n.kind === "external") inspBody.innerHTML = externalHTML(n);
        else if (graph.sources.includes(n)) inspBody.innerHTML = sourceHTML(n);
        else if (graph.runtimes.includes(n)) inspBody.innerHTML = runtimeHTML(n);
        else inspBody.innerHTML = sectionHTML(n);
      }
      bindInspector();
      replayPanelIn();
    }
    function externalHTML(x) {
      const imports = importEdgesFrom(x.id);
      return eyebrow("External Input · 导入", x.status) +
        '<h2 class="insp-title">' + esc(x.label) + "</h2>" +
        '<p class="insp-sub" style="font-family:var(--font)">外部语料经 forge 的 capture → review → import 流水线进入 canonical source。</p>' +
        '<div class="insp-section"><div class="kv">' +
          '<span class="k">类型</span><span class="v">' + tag("external input", "var(--declared)") + "</span>" +
          '<span class="k">状态</span><span class="v">' + tag(x.status === "pending" ? "待导入 pending" : "已导入 imported", STATUS_COLOR[x.status]) + "</span>" +
          '<span class="k">导入文件</span><span class="v">' + (x.file_count || imports.length) + "</span>" +
        "</div></div>" +
        '<div class="insp-section"><h4>导入成的 capture（' + imports.length + "）</h4>" +
          (imports.length ? '<div class="lineage">' + imports.map(e => '<div class="lin-row">' + nodelink(byId.get(e.to_id), e.status) + '<span class="lin-arrow">· ' + esc(e.status) + "</span></div>").join("") + "</div>"
            : '<div class="empty">没有关联的 capture。</div>') +
        "</div>" +
        '<p class="note">这层只展示 capture frontmatter 记录的导入来源,不直接读取外部语料原文。原始语料经 review 后才落入 canonical source。</p>';
    }

    // Classify how a source's text became a section's text (no derive record in
    // the data, so this is a computed, honest approximation — not a claim of
    // exact span mapping).
    function classifyExtraction(fromText, toText) {
      const from = String(fromText || ""), to = String(toText || "");
      if (!from || !to) return { kind: "—", note: "缺一侧文本，无法比对" };
      const norm = (s) => s.replace(/\s+/g, " ").trim();
      const nf = norm(from), nt = norm(to);
      if (nf.includes(nt)) return { kind: "逐字拷贝", color: "var(--exact)", note: "section 文本在 source 中逐字出现" };
      const toLines = to.split("\n").map(l => l.trim()).filter(l => l.length > 4);
      const hit = toLines.filter(l => nf.includes(norm(l))).length;
      if (toLines.length && hit / toLines.length >= 0.5) return { kind: "部分摘录", color: "var(--declared)", note: hit + "/" + toLines.length + " 行在 source 中可逐字定位" };
      if (hit > 0) return { kind: "改写 + 少量摘录", color: "var(--uncertain)", note: "仅 " + hit + " 行可逐字定位，其余为转写" };
      return { kind: "转写 / 蒸馏", color: "var(--uncertain)", note: "section 文本未在 source 中逐字出现（声明级关系，无精确 derive record）" };
    }

    function edgeHTML(e) {
      if (!e) return '<div class="empty">边不存在。</div>';
      const from = byId.get(e.from_id), to = byId.get(e.to_id);
      if (e.relation === "external_to_source") {
        const head = eyebrow("External Input → Capture · " + (e.status || ""), e.status) +
          '<h2 class="insp-title" style="font-size:17px">' + esc(from && (from.name || from.label || from.config)) +
          ' <span style="color:var(--muted-2)">→</span> ' + esc(to && (to.name || to.label || to.config)) + "</h2>" +
          '<p class="insp-sub" style="font-family:var(--font)">capture frontmatter 记录外部来源；Portal 不直接读取外部语料原文。</p>';
        const methodCard =
          '<div class="kv">' +
            '<span class="k">关系</span><span class="v">' + statusTag(e.status) + "</span>" +
            '<span class="k">记录方式</span><span class="v">' + tag("capture frontmatter", "var(--declared)") + "</span>" +
            '<span class="k">外部来源</span><span class="v">' + esc((from && from.label) || "—") + "</span>" +
            '<span class="k">导入文件</span><span class="v">' + esc((to && to.pointer) || "—") + "</span>" +
            '<span class="k">证据</span><span class="v" style="font-family:var(--mono);font-size:12px">' + esc(e.evidence || "—") + "</span>" +
          "</div>";
        const flow =
          '<div class="insp-section"><h4>外部来源（From）</h4>' +
            '<div class="kv">' +
              '<span class="k">名称</span><span class="v">' + esc((from && from.label) || "—") + "</span>" +
              '<span class="k">状态</span><span class="v">' + tag(from && from.status === "pending" ? "待导入 pending" : "已导入 imported", STATUS_COLOR[from && from.status]) + "</span>" +
              '<span class="k">文件数</span><span class="v">' + ((from && from.file_count) || 0) + "</span>" +
            "</div>" +
          "</div>" +
          '<div class="insp-section"><h4>导入产物（Capture）</h4>' +
            (to && to.content_excerpt ? codeBlock(to.content_excerpt, to.position && to.position.start_line, esc(to.pointer))
              : '<div class="empty">capture 摘录不可用。</div>') +
          "</div>";
        return head +
          '<div class="insp-section">' + methodCard + "</div>" +
          '<div class="insp-section" style="display:flex;gap:8px;flex-wrap:wrap">' + nodelink(from, e.status) + '<span class="lin-arrow">→</span>' + nodelink(to, e.status) + "</div>" +
          flow;
      }
      const isRt = e.relation === "section_to_runtime";
      const isInput = e.relation === "input_to_source";
      const relLabel = isRt ? "Section → Runtime" : isInput ? "Input / Capture → Canonical Source" : "Source → Section";
      const head = eyebrow(relLabel + " · " + (e.status || ""), e.status) +
        '<h2 class="insp-title" style="font-size:17px">' + esc(from && (from.name || from.label || from.config)) +
        ' <span style="color:var(--muted-2)">→</span> ' + esc(to && (to.name || to.label || to.config)) + "</h2>" +
        (isRt
          ? '<p class="insp-sub" style="font-family:var(--font)">编译器把 section block 逐字渲染进 runtime；命中行范围是精确的。</p>'
          : isInput
          ? '<p class="insp-sub" style="font-family:var(--font)">KB frontmatter 声明该 clipping/capture 已整合进 canonical knowledge source。</p>'
          : '<p class="insp-sub" style="font-family:var(--font)">声明级血缘：' + esc(e.evidence || "") + "</p>");
      // Original info (from) and product (to)
      let fromText, fromCap, toText, toCap, toStart = 1, hlRange = null, method;
      if (isRt) {
        fromText = to ? "" : ""; // placeholder, set below
        const rng = e.runtime_range;
        fromText = (from && from.content) || "";
        fromCap = esc((from && from.name) || "section");
        toText = (rng && rng.start_line && to) ? String(to.content || "").split("\n").slice(rng.start_line - 1, rng.end_line).join("\n") : "";
        toStart = (rng && rng.start_line) || 1;
        toCap = esc((to && to.config) || "runtime") + " · lines " + (rng && rng.start_line ? rng.start_line + (rng.end_line !== rng.start_line ? "-" + rng.end_line : "") : "—");
        method = { kind: "compiler 逐字渲染", color: "var(--exact)", note: "section block 渲染后在 runtime 文本逐字命中" };
      } else {
        fromText = (from && from.content_excerpt) || "";
        fromCap = esc((from && from.pointer) || "source");
        toText = (to && (to.content || to.content_excerpt)) || "";
        toStart = (to && to.position && to.position.start_line) || 1;
        toCap = esc((to && (to.name || to.pointer)) || (isInput ? "canonical source" : "section"));
        method = isInput
          ? { kind: "KB frontmatter 声明", color: "var(--declared)", note: "这是 review graph 中的 source-to-source 关系，不替代 section/runtime provenance" }
          : classifyExtraction(fromText, toText);
      }
      const methodCard =
        '<div class="kv">' +
          '<span class="k">关系</span><span class="v">' + statusTag(e.status) + "</span>" +
          '<span class="k">提取方式</span><span class="v"><span class="tag"><span class="d" style="background:' + (method.color || "var(--muted)") + '"></span>' + esc(method.kind) + "</span></span>" +
          '<span class="k">说明</span><span class="v">' + esc(method.note) + "</span>" +
          '<span class="k">证据</span><span class="v" style="font-family:var(--mono);font-size:12px">' + esc(e.evidence || "—") + "</span>" +
        "</div>";
      const flow =
        '<div class="insp-section"><h4>原信息（From）</h4>' +
          (fromText ? codeBlock(fromText, isRt ? ((from && from.position && from.position.start_line) || 1) : ((from && from.position && from.position.start_line) || 1), fromCap) : '<div class="empty">无可用原文。</div>') +
        "</div>" +
        '<div class="insp-section"><h4>提取产物（To）' + (isRt ? " · 命中行" : "") + "</h4>" +
          (toText ? codeBlock(toText, toStart, toCap) : '<div class="empty">无可用产物文本。</div>') +
        "</div>";
      return head +
        '<div class="insp-section">' + methodCard + "</div>" +
        '<div class="insp-section" style="display:flex;gap:8px;flex-wrap:wrap">' + nodelink(from, e.status) + '<span class="lin-arrow">→</span>' + nodelink(to, e.status) + "</div>" +
        flow;
    }

    function changedNodes() {
      return [...graph.sources, ...graph.sections, ...graph.runtimes]
        .filter(n => n.change && n.change !== "unchanged");
    }
    function diffOverviewHTML() {
      const d = graph.diff;
      const items = changedNodes().sort((a, b) => {
        const ord = { added: 0, modified: 1, removed: 2 };
        return ord[a.change] - ord[b.change];
      });
      const list = items.length ? items.map(n => {
        const kind = graph.runtimes.includes(n) ? "runtime" : graph.sections.includes(n) ? "section" : "source";
        return '<button class="gap sev-' + (n.change === "removed" ? "high" : n.change === "modified" ? "med" : "low") + '" data-goto="' + esc(n.id) + '">' +
          '<div class="gh"><span class="chg chg-' + n.change + '" style="position:static;box-shadow:none">' + CHG_SIGN[n.change] + "</span>" +
          tag(CHG_LABEL[n.change], STATUS_COLOR[n.change === "removed" ? "missing" : n.change === "modified" ? "uncertain" : "exact"]) +
          '<span class="gid">' + esc(kind) + "</span></div>" +
          '<div class="gobj">' + esc(n.name || n.label || n.config) + "</div></button>";
      }).join("") : '<div class="empty">工作树与 base 相比没有改动。</div>';
      return '<div class="insp-section">' +
        '<div class="distro-legend" style="margin-bottom:12px">' +
          '<span class="diff-pill"><span class="d" style="width:8px;height:8px;border-radius:50%;background:var(--exact)"></span>新增 <b>' + d.added + "</b></span>" +
          '<span class="diff-pill"><span class="d" style="width:8px;height:8px;border-radius:50%;background:var(--uncertain)"></span>修改 <b>' + d.modified + "</b></span>" +
          '<span class="diff-pill"><span class="d" style="width:8px;height:8px;border-radius:50%;background:var(--missing)"></span>删除 <b>' + d.removed + "</b></span>" +
        "</div>" +
        '<h4>改动节点 · ' + items.length + "</h4><div class=\"gap-list\">" + list + "</div></div>";
    }
    function overviewHTML() {
      const m = metrics();
      const gp = gaps();
      const distro = ["exact", "derived", "declared", "uncertain", "missing", "wrapper"].map(st => {
        let count = 0;
        if (st === "exact") count = rtEdges.filter(e => e.status === "exact").length;
        else count = graph.sections.filter(s => s.relation_state === st).length;
        return { st, count };
      }).filter(d => d.count);
      const totalDistro = distro.reduce((a, b) => a + b.count, 0) || 1;
      const gapList = gp.length ? gp.map(g =>
        '<button class="gap sev-' + g.sev + '" data-goto="' + esc(g.target ? g.target.id : "") + '">' +
          '<div class="gh"><span class="gid">' + g.id + '</span>' + tag(g.type.replace(/_/g, " "), STATUS_COLOR[g.sev === "high" ? "missing" : g.sev === "med" ? "uncertain" : "declared"]) + "</div>" +
          '<div class="gobj">' + esc(g.object) + "</div>" +
          '<div class="gmsg">' + esc(g.msg) + "</div>" +
        "</button>").join("") : '<div class="empty">没有未解释的关系。所有 section 都有可审计的来源。</div>';
      const rv = diffMode && reviewView;
      return eyebrow(rv ? "改动评审" : "审计总览") +
        '<h2 class="insp-title">' + (rv ? "Change Review" : "Provenance 健康度") + "</h2>" +
        '<p class="insp-sub" style="font-family:var(--font)">' + (rv ? "对比 base=" + esc(graph.diff.base_ref) + " 与工作树；点改动节点看 diff 和影响链路。" : "点任意节点查看血缘；hover 高亮整条链路。") + "</p>" +
        (rv ? diffOverviewHTML() : "") +
        '<div class="insp-section"><div class="health-bars">' +
          hbar("Runtime exact 覆盖", m.exactPct, "var(--exact)", exactSubtitle()) +
          hbar("Section 有来源支撑", m.backedPct, "var(--declared)", backedSubtitle()) +
        "</div></div>" +
        '<div class="insp-section"><h4>关系分布</h4>' +
          '<div class="distro">' + distro.map(d => '<i style="width:' + (d.count / totalDistro * 100) + '%;background:' + STATUS_COLOR[d.st] + '"></i>').join("") + "</div>" +
          '<div class="distro-legend">' + distro.map(d => '<span class="li"><span class="d" style="background:' + STATUS_COLOR[d.st] + '"></span>' + d.st + " · " + d.count + "</span>").join("") + "</div>" +
        "</div>" +
        '<div class="insp-section"><h4>Review Gaps · ' + gp.length + "</h4>" +
          '<div class="gap-list">' + gapList + "</div></div>" +
        workflowHTML() +
        '<p class="note">Portal 不是事实源。它只展示 compiler 的 exact mapping、section frontmatter 的声明,以及显式 uncertain。所有关系修正都要产生 derive record 或 proposal,不在 Portal 内直接改事实源。</p>';
    }
    function exactSubtitle() {
      const e = rtEdges.filter(x => x.status === "exact").length;
      return e + " / " + rtEdges.length + " 条 section→runtime 命中精确行范围";
    }
    function backedSubtitle() {
      const real = graph.sections.filter(s => s.relation_state !== "wrapper");
      const backed = real.filter(s => s.relation_state === "derived" || s.relation_state === "declared").length;
      return backed + " / " + real.length + " 个 section 声明了 upstream";
    }
    function hbar(label, pct, color, sub) {
      return '<div class="hbar"><div class="hbar-top"><span class="label">' + esc(label) + '</span><span class="pct" style="color:' + color + '">' + pct + '%</span></div>' +
        '<div class="track"><i style="width:' + pct + '%;background:' + color + '"></i></div>' +
        (sub ? '<div class="insp-sub" style="font-family:var(--font);margin-top:6px">' + esc(sub) + "</div>" : "") + "</div>";
    }
    function workflowHTML() {
      const steps = [["1", "propose", "Agent 提案补 derive record 或 source pointer"],
        ["2", "review", "Owner 审核 source、section 与 runtime 证据"],
        ["3", "approve", "通过后写入 canonical source / proposal"],
        ["4", "rejected", "驳回,不自动补全历史关系"]];
      return '<div class="insp-section"><h4>Owner 审核工作流</h4><div class="workflow">' +
        steps.map(s => '<div class="wf-step"><span class="wf-num">' + s[0] + '</span><span><b>' + s[1] + "</b> · " + esc(s[2]) + "</span></div>").join("") +
        "</div></div>";
    }

    function sourceHTML(s) {
      const consumers = [...inputEdgesFrom(s.id), ...srcEdgesFrom(s.id)];
      const upstreamInputs = inputEdgesTo(s.id);
      const head = eyebrow((KIND_LABEL[s.kind] || s.kind) + " Source", nodeStatus(s)) +
        '<h2 class="insp-title">' + esc(s.label) + "</h2>" +
        '<p class="insp-sub">' + esc(s.pointer) + "</p>" +
        changeBanner(s);
      const content =
        '<div class="kv">' +
          '<span class="k">架构层</span><span class="v">' + tag(s.layer || "core", "var(--accent)") + "</span>" +
          '<span class="k">kind</span><span class="v">' + esc(KIND_LABEL[s.kind] || s.kind || "") + "</span>" +
          '<span class="k">位置</span><span class="v">' + esc(pos(s.position)) + "</span>" +
          '<span class="k">状态</span><span class="v">' + (s.status === "missing" ? tag("未解析 missing", "var(--missing)") : s.status === "unlinked" ? tag("review-only unlinked", "var(--uncertain)") : tag("已解析 resolved", "var(--exact)")) + "</span>" +
        "</div>" +
        '<div class="insp-section">' +
          ((s.content_excerpt || s.prev_content) ? contentBlock(s, s.content_excerpt, s.position && s.position.start_line, esc(s.pointer))
            : '<div class="empty">摘录不可用（目录或缺失文件）。</div>') +
        "</div>";
      const lineage = consumers.length
        ? '<div class="lineage">' + consumers.map(e => '<div class="lin-row">' + nodelink(byId.get(e.to_id), e.status) + "</div>").join("") + "</div>"
        : '<div class="empty">没有下游声明引用它。</div>';
      const inputs = upstreamInputs.length
        ? '<div class="lineage">' + upstreamInputs.map(e => '<div class="lin-row">' + nodelink(byId.get(e.from_id), e.status) + '<span class="lin-arrow">→</span>' + nodelink(s) + "</div>").join("") + "</div>"
        : '<div class="empty">没有上游 clipping/capture 声明。</div>';
      return head + tabbed([["Content", content], ["上游输入", inputs, upstreamInputs.length], ["下游", lineage, consumers.length]]);
    }

    function sectionHTML(s) {
      const sources = srcEdgesTo(s.id);
      const runtimes = rtEdgesFrom(s.id);
      const upstream = sources.length
        ? sources.map(e => nodelink(byId.get(e.from_id), e.status)).join("")
        : (s.relation_state === "wrapper" ? tag("compiled wrapper · 无 upstream（设计如此）", "var(--wrapper)") : tag("无 source/upstream", "var(--uncertain)"));
      const downstream = runtimes.length ? runtimes.map(e => nodelink(byId.get(e.to_id), e.status)).join("") : tag("无 runtime mapping", "var(--uncertain)");
      const sourceBlocks = sources.map(e => {
        const src = byId.get(e.from_id);
        const cap = esc(src.label) + " · " + esc(src.layer || "") + " · " + statusTag(e.status);
        return src.content_excerpt ? codeBlock(src.content_excerpt, src.position && src.position.start_line, cap) : ('<div class="empty">' + esc(src.label) + ": excerpt 不可用</div>");
      }).join("") || '<div class="empty">无 source / upstream 声明</div>';
      const runtimeBlocks = runtimes.map(e => {
        const r = byId.get(e.to_id);
        const rng = e.runtime_range;
        const excerpt = (rng && rng.start_line) ? String(r.content || "").split("\n").slice(rng.start_line - 1, rng.end_line).join("\n") : "";
        const cap = esc(r.config) + " · " + (rng && rng.start_line ? "lines " + rng.start_line + (rng.end_line !== rng.start_line ? "-" + rng.end_line : "") : "no exact range") + " · " + statusTag(e.status);
        return excerpt ? codeBlock(excerpt, rng.start_line, cap) : '<div class="empty">' + esc(r.config) + ": " + esc(e.evidence) + "</div>";
      }).join("") || '<div class="empty">无 runtime mapping</div>';
      const head = eyebrow((s.type || "section") + " · " + s.relation_state, s.relation_state) +
        '<h2 class="insp-title">' + esc(s.name) + "</h2>" +
        '<p class="insp-sub" style="font-family:var(--font)">' + esc(s.relation_note || "") + "</p>" +
        changeBanner(s);
      const content =
        '<div class="kv">' +
          '<span class="k">架构层</span><span class="v">' + tag(s.layer || "core", "var(--accent)") + "</span>" +
          '<span class="k">位置</span><span class="v">' + esc(pos(s.position)) + "</span>" +
          '<span class="k">source 数</span><span class="v">' + sources.length + "</span>" +
          '<span class="k">runtime 数</span><span class="v">' + runtimes.length + "</span>" +
        "</div>" +
        '<div class="insp-section">' + contentBlock(s, s.content, s.position && s.position.start_line, esc(s.name)) + "</div>";
      const lineage =
        '<div class="lineage">' +
          '<div class="lin-row">' + upstream + '<span class="lin-arrow">→</span>' + nodelink(s) + "</div>" +
          '<div class="lin-row">' + nodelink(s) + '<span class="lin-arrow">→</span>' + downstream + "</div>" +
        "</div>" +
        '<div class="insp-section"><h4>Source 摘录</h4>' + sourceBlocks + "</div>";
      return head + tabbed([
        ["Content", content],
        ["Lineage", lineage, sources.length],
        ["Runtime hits", runtimeBlocks, runtimes.length],
      ]);
    }

    function runtimeHTML(r) {
      const maps = rtEdgesTo(r.id).slice().sort((a, b) =>
        ((a.runtime_range && a.runtime_range.start_line) || 1e9) - ((b.runtime_range && b.runtime_range.start_line) || 1e9));
      const chips = maps.map(e => {
        const s = byId.get(e.from_id);
        const rng = e.runtime_range;
        return '<button class="nodelink" data-goto="' + esc(s.id) + '" data-hlrange="' +
          ((rng && rng.start_line) || "") + "," + ((rng && rng.end_line) || "") +
          '"><span class="d" style="background:' + (STATUS_COLOR[e.status] || "var(--muted)") + '"></span><span class="name">' +
          esc(s.name) + "</span></button>";
      }).join("");
      const mirrors = (r.mirrors || []).map(m => esc(pos(m))).join("<br>") || "—";
      const head = eyebrow(r.target + " runtime", nodeStatus(r)) +
        '<h2 class="insp-title">' + esc(r.config) + "</h2>" +
        '<p class="insp-sub">' + esc(r.path) + "</p>" +
        changeBanner(r);
      const content =
        '<div class="kv">' +
          '<span class="k">canonical</span><span class="v">' + esc(pos(r.position)) + "</span>" +
          '<span class="k">mirror</span><span class="v">' + mirrors + "</span>" +
        "</div>" +
        '<div class="insp-section">' + contentBlock(r, r.content, 1, esc(r.path)) + "</div>";
      const sections =
        '<p class="insp-sub" style="font-family:var(--font);margin:0 0 10px">hover 一个 section 高亮它命中的行范围。</p>' +
        '<div class="lineage"><div class="lin-row">' + (chips || '<div class="empty">无映射</div>') + "</div></div>";
      return head + tabbed([["Content", content], ["映射的 Section", sections, maps.length]]);
    }
    function statusTag(s) { return '<span class="tag"><span class="d" style="background:' + (STATUS_COLOR[s] || "var(--muted)") + '"></span>' + esc(s) + "</span>"; }

    function bindInspector() {
      inspBody.querySelectorAll("[data-goto]").forEach(b => {
        const id = b.dataset.goto;
        if (!id) return;
        b.addEventListener("click", () => { selectedId = id; selectedEdgeId = null; activeTab = 0; applyHighlight(); renderInspector();
          const el = elFor(id); if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" }); });
        if (b.dataset.hlrange) {
          const [a, c] = b.dataset.hlrange.split(",").map(Number);
          b.addEventListener("mouseenter", () => hlRuntimeLines(a, c));
          b.addEventListener("mouseleave", () => hlRuntimeLines(0, 0));
        }
      });
      inspBody.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
        activeTab = Number(t.dataset.tab);
        inspBody.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === t));
        inspBody.querySelectorAll(".tabpane").forEach(p => { p.hidden = Number(p.dataset.pane) !== activeTab; });
      }));
    }
    function hlRuntimeLines(a, c) {
      inspBody.querySelectorAll(".code-line").forEach(row => {
        const no = Number(row.querySelector(".ln").textContent);
        row.classList.toggle("hl", a && no >= a && no <= c);
      });
      if (a) {
        const first = [...inspBody.querySelectorAll(".code-line")].find(r => Number(r.querySelector(".ln").textContent) === a);
        if (first) first.scrollIntoView({ block: "nearest" });
      }
    }

    // ---- filters & search ----
    const activeStatus = new Set(["exact", "derived", "declared", "uncertain", "missing", "wrapper"]);
    let gapsOnly = false;
    let changedOnly = diffMode;
    let query = "";
    function applyFilters() {
      const gapTargets = gapsOnly ? gapNodeSet() : null;
      const changedTargets = changedOnly ? changedNodeSet() : null;
      lanes.querySelectorAll(".node").forEach(el => {
        const st = el.dataset.status;
        let visible = activeStatus.has(st);
        if (visible && query) visible = el.dataset.search.toLowerCase().includes(query);
        if (visible && gapTargets) visible = gapTargets.has(el.dataset.id);
        if (visible && changedTargets) visible = changedTargets.has(el.dataset.id);
        el.classList.toggle("dim", !visible);
      });
      refreshFilteredLanes();
      refreshLaneColumns();
      requestAnimationFrame(drawLinks);
    }
    function refreshFilteredLanes() {
      let visibleNodeCount = 0;
      lanes.querySelectorAll(".lane").forEach(lane => {
        let anyVisible = false;
        let currentLabel = null;
        let currentVisible = false;
        const groups = [];
        [...lane.children].forEach(child => {
          if (child.classList.contains("lane-head")) return;
          if (child.classList.contains("lane-group-label")) {
            if (currentLabel) groups.push([currentLabel, currentVisible]);
            currentLabel = child;
            currentVisible = false;
            return;
          }
          if (child.classList.contains("node") && !child.classList.contains("dim")) {
            anyVisible = true;
            currentVisible = true;
            visibleNodeCount++;
          }
        });
        if (currentLabel) groups.push([currentLabel, currentVisible]);
        groups.forEach(([label, visible]) => { label.hidden = !visible; });
        lane.classList.toggle("filtered-empty", !anyVisible);
      });
      graphEmpty.hidden = visibleNodeCount > 0;
    }
    function gapNodeSet() {
      const set = new Set();
      gaps().forEach(g => { if (g.target) lineage(g.target.id).forEach(x => set.add(x)); });
      return set;
    }
    function changedNodeSet() {
      const set = new Set();
      changedNodes().forEach(n => lineage(n.id).forEach(x => set.add(x)));
      return set;
    }

    // ---- mount ----
    function mountCounts() {
      const m = metrics();
      document.getElementById("counts").innerHTML = [
        ["sources", graph.sources.length, ""],
        ["sections", graph.sections.length, ""],
        ["runtime", graph.runtimes.length, ""],
        ["gaps", m.gaps, m.gaps ? "warn" : ""],
      ].map(([lab, val, cls]) => '<span class="ct ' + cls + '"><b>' + val + "</b>" + lab + "</span>").join("");
    }
    (function mountCrumbs() {
      const root = String(graph.workspace_root || "");
      const repo = root.split("/").filter(Boolean).pop() || root || "workspace";
      const parts = ['<span class="repo">' + esc(repo) + '</span>',
        '<span class="sep">/</span>',
        '<span class="branch">layout=' + esc(graph.layout) + "</span>"];
      if (diffMode) parts.push('<span class="branch">⎇ base ' + esc(graph.diff.base_ref) + "</span>");
      document.getElementById("crumbs").innerHTML = parts.join(" ");
    })();
    document.getElementById("cnt-captures").textContent = captureSources.length;
    document.getElementById("cnt-sources").textContent = canonicalSources.length;
    document.getElementById("cnt-sections").textContent = graph.sections.length;
    document.getElementById("cnt-runtimes").textContent = graph.runtimes.length;
    if (externals.length) {
      laneExternal.hidden = false;
      document.getElementById("cnt-external").textContent = externals.length;
    }
    mountCounts();
    // ---- Audit / Review mode toggle ----
    let reviewView = diffMode;
    const modeReview = document.getElementById("mode-review");
    function applyMode() {
      document.body.classList.toggle("audit-view", !reviewView);
      document.querySelectorAll("#mode-seg .seg-btn").forEach(b =>
        b.classList.toggle("active", (b.dataset.mode === "review") === reviewView));
      if (diffMode) {
        changedOnly = reviewView;
        document.getElementById("changed-only").setAttribute("aria-pressed", String(changedOnly));
      }
      renderInspector();
      applyFilters();
    }
    if (!diffMode) { modeReview.disabled = true; modeReview.title = "用 forge audit portal --diff 生成以启用变更评审"; }
    document.querySelectorAll("#mode-seg .seg-btn").forEach(b => b.addEventListener("click", () => {
      if (b.dataset.mode === "review" && !diffMode) return;
      reviewView = b.dataset.mode === "review";
      applyMode();
    }));
    applyMode();
    renderExternals(); renderCaptures(); renderSources(); renderSections(); renderRuntimes();
    refreshLaneColumns();
    renderInspector();
    applyFilters();
    requestAnimationFrame(() => canvasEl.scrollTo({ left: 0, top: 0 }));
    requestAnimationFrame(drawLinks);

    // ---- events ----
    const input = document.getElementById("search");
    input.addEventListener("input", () => { query = input.value.trim().toLowerCase(); applyFilters(); });
    document.querySelectorAll(".filter").forEach(btn => btn.addEventListener("click", () => {
      const st = btn.dataset.status;
      const on = btn.getAttribute("aria-pressed") === "true";
      btn.setAttribute("aria-pressed", String(!on));
      if (on) activeStatus.delete(st); else activeStatus.add(st);
      applyFilters();
    }));
    const gapsBtn = document.getElementById("gaps-only");
    gapsBtn.addEventListener("click", () => { gapsOnly = !gapsOnly; gapsBtn.setAttribute("aria-pressed", String(gapsOnly)); applyFilters(); });
    const changedBtn = document.getElementById("changed-only");
    if (diffMode) {
      changedBtn.hidden = false;
      changedBtn.setAttribute("aria-pressed", String(changedOnly));
      changedBtn.addEventListener("click", () => { changedOnly = !changedOnly; changedBtn.setAttribute("aria-pressed", String(changedOnly)); applyFilters(); });
    }
    document.getElementById("reset-view").addEventListener("click", () => {
      hoverId = null; keyboardFocusId = null; query = ""; input.value = ""; gapsOnly = false; changedOnly = diffMode && reviewView;
      cancelHoverPreview(); hideHoverCard();
      gapsBtn.setAttribute("aria-pressed", "false");
      changedBtn.setAttribute("aria-pressed", "false");
      activeStatus.clear(); ["exact", "derived", "declared", "uncertain", "missing", "wrapper"].forEach(s => activeStatus.add(s));
      document.querySelectorAll(".filter").forEach(b => b.setAttribute("aria-pressed", "true"));
      applyFilters(); canvasEl.scrollTo({ left: 0, top: 0 }); closePanel();
    });
    canvasEl.addEventListener("click", (e) => {
      if (e.target.closest(".node")) return;
      hideHoverCard();
      if (panelOpen) closePanel();
    });
    // ---- floating detail drawer: open / close / maximize ----
    const inspector = document.getElementById("inspector");
    const backdrop = document.getElementById("insp-backdrop");
    const expandBtn = document.getElementById("insp-expand");
    const splitEl = document.getElementById("split");
    const divider = document.getElementById("divider");
    const hoverCard = document.getElementById("hover-card");
    hoverCard.addEventListener("mouseenter", cancelHideHoverCard);
    hoverCard.addEventListener("mouseleave", scheduleHideHoverCard);
    function setPanel(v) {
      panelOpen = v;
      splitEl.classList.toggle("panel-open", v);
    }
    function setMax(v) {
      inspectorMax = v;
      splitEl.classList.toggle("maxed", v);
      backdrop.hidden = !v;
      expandBtn.textContent = v ? "⤡" : "⤢";
      expandBtn.title = v ? "还原（E）" : "最大化（E）";
    }
    function closePanel() { hideHoverCard(); setMax(false); setPanel(false); selectedId = null; selectedEdgeId = null; keyboardFocusId = null; hoverId = null; applyHighlight(); }
    function openOverview() { hideHoverCard(); selectedId = null; selectedEdgeId = null; keyboardFocusId = null; hoverId = null; activeTab = 0; applyHighlight(); renderInspector(); setPanel(true); }
    expandBtn.addEventListener("click", () => setMax(!inspectorMax));
    document.getElementById("insp-close").addEventListener("click", closePanel);
    document.getElementById("overview-btn").addEventListener("click", () => panelOpen && !selectedId ? closePanel() : openOverview());
    backdrop.addEventListener("click", () => setMax(false));
    // ---- divider drag (resize the drawer) ----
    const WKEY = "forge-audit-insp-w";
    function setInspW(px, persist) {
      const w = Math.max(400, Math.min(px, window.innerWidth * 0.85));
      splitEl.style.setProperty("--insp-w", w + "px");
      if (persist) { try { localStorage.setItem(WKEY, String(Math.round(w))); } catch (e) {} }
    }
    try { const saved = localStorage.getItem(WKEY); if (saved) setInspW(parseInt(saved, 10), false); } catch (e) {}
    let dragging = false;
    divider.addEventListener("pointerdown", (e) => {
      dragging = true; divider.classList.add("drag"); document.body.classList.add("dragging");
      try { divider.setPointerCapture(e.pointerId); } catch (err) {}
    });
    divider.addEventListener("pointermove", (e) => {
      if (!dragging) return;
      setInspW(splitEl.getBoundingClientRect().right - e.clientX, false);
    });
    divider.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false; divider.classList.remove("drag"); document.body.classList.remove("dragging");
      setInspW(inspector.getBoundingClientRect().width, true);
    });
    divider.addEventListener("dblclick", () => { splitEl.style.removeProperty("--insp-w"); try { localStorage.removeItem(WKEY); } catch (e) {} });

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== input) { e.preventDefault(); input.focus(); input.select(); }
      if ((e.key === "e" || e.key === "E") && document.activeElement !== input && panelOpen) { e.preventDefault(); setMax(!inspectorMax); }
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key) && document.activeElement !== input) {
        e.preventDefault();
        const dir = e.key.replace("Arrow", "").toLowerCase();
        moveKeyboardFocus(dir);
      }
      if (e.key === "Enter" && document.activeElement !== input && keyboardFocusId) {
        e.preventDefault();
        pinKeyboardFocus();
      }
      if (e.key === "Escape") {
        if (document.activeElement === input) { input.blur(); }
        else if (!hoverCard.hidden) { hideHoverCard(); keyboardFocusId = null; hoverId = null; applyHighlight(); }
        else if (inspectorMax) { setMax(false); }
        else if (panelOpen) { closePanel(); }
      }
    });
    let rt;
    const scheduleDraw = () => { clearTimeout(rt); rt = setTimeout(drawLinks, 100); };
    window.addEventListener("resize", scheduleDraw);
    // Any reflow of the lanes (font load, filter dim, 3↔4 columns) re-aligns edges.
    if (window.ResizeObserver) new ResizeObserver(scheduleDraw).observe(lanes);
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => drawLinks());
  })();
  </script>
</body>
</html>
"""
