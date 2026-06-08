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
      /* Design language adopted from a Claude Design pass (Linear/Vercel-grade,
         restrained: exact recedes to gray, gaps & changes pop). */
      --bg: #f4f5f7;
      --canvas-dot: #e3e5ea;
      --panel: #ffffff;
      --panel-soft: #fafbfc;
      --surface-3: #f3f4f6;
      --ink: #16181d;
      --ink-soft: #585f6b;
      --muted: #8a909c;
      --muted-2: #aab0bb;
      --line: #e8eaee;
      --line-2: #dfe2e8;
      --line-soft: #eef0f3;
      --accent: #5b5bd6;
      --accent-2: #4a4ac4;
      --accent-soft: #eeeefb;
      --accent-ring: rgba(91, 91, 214, 0.35);
      --exact: #aab0bb;
      --exact-soft: #eef0f3;
      --derived: #2f6feb;
      --derived-soft: #eaf1fe;
      --declared: #8155f4;
      --declared-soft: #f1ecfe;
      --uncertain: #c5871a;
      --uncertain-soft: #fbf2dd;
      --missing: #db4a55;
      --missing-soft: #fdeced;
      --wrapper: #9aa1ad;
      --added: #1f9d57;
      --added-soft: #e7f6ee;
      --modified: #c5871a;
      --modified-soft: #fbf2dd;
      --removed: #db4a55;
      --removed-soft: #fdeced;
      --diff-add-bg: #e7f6ee;
      --diff-add-mark: #1f9d57;
      --diff-del-bg: #fdeced;
      --diff-del-mark: #db4a55;
      --shadow-sm: 0 1px 2px rgba(20, 22, 28, .05), 0 1px 1px rgba(20, 22, 28, .03);
      --shadow-md: 0 4px 16px rgba(20, 22, 28, .08), 0 1px 3px rgba(20, 22, 28, .05);
      --shadow-lg: 0 12px 40px rgba(20, 22, 28, .14), 0 2px 8px rgba(20, 22, 28, .06);
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
      background: #16181d; display: grid; place-items: center; color: #fff;
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
    .search:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); background: #fff; }
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

    /* ---------- body split ---------- */
    .split { flex: 1 1 auto; display: grid; grid-template-columns: minmax(0,1fr) 7px var(--insp-w, 620px); min-height: 0; }
    .divider { position: relative; cursor: col-resize; background: var(--line); }
    .divider::before { content: ""; position: absolute; inset: 0 -5px; }
    .divider:hover, .divider.drag { background: var(--accent); }
    .divider::after { content: ""; position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); width: 3px; height: 34px; border-radius: 3px; background: var(--muted); opacity: .5; }
    .divider:hover::after, .divider.drag::after { background: #fff; opacity: .9; }
    body.dragging { cursor: col-resize; user-select: none; }
    .canvas-wrap { position: relative; overflow: auto; padding: 22px 22px 56px; background-color: var(--bg); background-image: radial-gradient(var(--canvas-dot) 1px, transparent 1.4px); background-size: 18px 18px; }
    .lanes { position: relative; display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 38px; }
    .links-svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: visible; }
    .lane { position: relative; z-index: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
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
      padding: 8px 10px; box-shadow: var(--shadow-sm);
      transition: box-shadow .15s, border-color .15s, transform .12s, opacity .15s;
      display: grid; gap: 4px;
    }
    .node:hover { border-color: #cdc8bd; transform: translateY(-1px); box-shadow: var(--shadow-md); }
    .node .chg { position: absolute; top: -8px; right: -8px; min-width: 19px; height: 19px; padding: 0 5px; border-radius: 999px; display: grid; place-items: center; font-size: 12px; font-weight: 800; color: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.25); z-index: 2; }
    .chg-added { background: var(--added); }
    .chg-modified { background: var(--modified); }
    .chg-removed { background: var(--removed); }
    .node.ch-removed { opacity: .6; }
    .node.ch-removed .name { text-decoration: line-through; }
    .node.ch-added { border-color: #5ec39a; }
    .node.ch-modified { border-color: #e8b765; }
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
    .code-line.d-add .ln { background: #d3efdd; color: var(--diff-add-mark); }
    .code-line.d-del { background: var(--diff-del-bg); }
    .code-line.d-del .ln { background: #f7d7d4; color: var(--diff-del-mark); }
    .diff-banner { display: flex; align-items: center; gap: 8px; border-radius: var(--r-md); padding: 9px 12px; font-size: 12.5px; margin-bottom: 14px; font-weight: 600; }
    .diff-banner.added { background: var(--added-soft); color: #126c3b; }
    .diff-banner.modified { background: var(--modified-soft); color: #8a5e12; }
    .diff-banner.removed { background: var(--removed-soft); color: #a8323c; }
    .diff-pill { display: inline-flex; align-items: center; gap: 6px; border: 1px solid var(--line); border-radius: 999px; padding: 5px 11px; font-size: 12px; color: var(--ink-soft); background: var(--panel); }
    .diff-pill b { font-weight: 700; }
    .node .row { display: flex; align-items: center; gap: 8px; min-width: 0; }
    .node .kind-ic { width: 26px; height: 26px; border-radius: 7px; flex: 0 0 auto; display: grid; place-items: center; }
    .node .name { font-weight: 650; font-size: 13.5px; letter-spacing: -.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1 1 auto; }
    .node .ptr { font-size: 11.5px; color: var(--muted); font-family: var(--mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .node .tags { display: flex; flex-wrap: wrap; gap: 5px; }
    .node .sdot { width: 9px; height: 9px; border-radius: 50%; flex: 0 0 auto; box-shadow: 0 0 0 3px rgba(0,0,0,.03); }
    .node.sel { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft), var(--shadow-md); }
    .node.dim { opacity: .26; filter: saturate(.5); }
    .node.hit { border-color: var(--accent); }

    .tag {
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 10.5px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
      background: var(--line-soft); color: var(--ink-soft);
    }
    .tag .d { width: 7px; height: 7px; border-radius: 50%; }
    .tag.mono { font-family: var(--mono); font-weight: 500; }

    /* ---------- inspector ---------- */
    .inspector { position: relative; border-left: 1px solid var(--line); background: var(--panel); overflow: auto; min-height: 0; }
    .insp-toolbar { position: sticky; top: 0; z-index: 3; display: flex; justify-content: flex-end; gap: 6px; padding: 8px 10px; background: linear-gradient(var(--panel), var(--panel) 70%, transparent); }
    .icon-btn { width: 30px; height: 30px; border: 1px solid var(--line); border-radius: 8px; background: var(--panel-soft); color: var(--ink-soft); font-size: 14px; line-height: 1; display: grid; place-items: center; }
    .icon-btn:hover { border-color: var(--accent); color: var(--accent); }
    .insp-pad { padding: 4px 20px 48px; }
    .insp-backdrop { position: fixed; inset: 0; background: rgba(24, 21, 16, .34); z-index: 40; backdrop-filter: blur(1px); }
    .inspector.max {
      position: fixed; top: 0; right: 0; bottom: 0;
      left: auto; width: min(1080px, 80vw); z-index: 50;
      box-shadow: -18px 0 50px rgba(24, 21, 16, .22);
      border-left: 1px solid var(--line);
    }
    .inspector.max .insp-pad { padding: 4px 32px 56px; }
    .inspector.max .code-scroll { max-height: 66vh; }
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
    .nodelink:hover { border-color: var(--accent); background: #fff; color: var(--accent); }
    .nodelink .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .nodelink .d { width: 7px; height: 7px; border-radius: 50%; flex: 0 0 auto; }

    .code {
      margin: 0; border: 1px solid var(--line); border-radius: var(--r-md); overflow: hidden;
      background: var(--panel-soft);
    }
    .code-scroll { max-height: 46vh; overflow: auto; }
    .code-line { display: grid; grid-template-columns: 42px minmax(0,1fr); font-family: var(--mono); font-size: 11.5px; line-height: 1.55; }
    .code-line .ln { color: #b8b2a6; text-align: right; padding: 0 9px; user-select: none; border-right: 1px solid var(--line-soft); background: #fbfaf6; }
    .code-line .lc { padding: 0 11px; white-space: pre; overflow-wrap: normal; }
    .code-line.hl { background: #fff7e6; }
    .code-line.hl .ln { background: #fdeccb; color: #9a6a12; }
    .code-cap { display: flex; justify-content: space-between; align-items: center; padding: 7px 11px; border-bottom: 1px solid var(--line); font-size: 11px; color: var(--muted); background: #fff; }

    .gap-list { display: flex; flex-direction: column; gap: 8px; }
    .gap {
      text-align: left; width: 100%; border: 1px solid var(--line); border-left-width: 3px;
      border-radius: var(--r-sm); background: var(--panel-soft); padding: 10px 12px;
      display: grid; gap: 3px; transition: border-color .12s, background .12s, transform .1s;
    }
    .gap:hover { background: #fff; transform: translateX(2px); }
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
      .split { grid-template-columns: 1fr; }
      .inspector { border-left: 0; border-top: 1px solid var(--line); max-height: 60vh; }
      .lanes { grid-template-columns: 1fr; gap: 22px; }
      .links-svg { display: none; }
      .metrics { display: none; }
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
      <button class="ghost-btn" id="reset-view">重置</button>
    </div>

    <div class="split">
      <div class="canvas-wrap" id="canvas">
        <div class="lanes" id="lanes">
          <svg class="links-svg" id="links"></svg>
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
      <div class="divider" id="divider" title="拖拽调整宽度（双击复位）"></div>
      <aside class="inspector" id="inspector">
        <div class="insp-toolbar">
          <button class="icon-btn" id="insp-expand" title="展开 / 收起详情（E）" aria-label="展开详情">⤢</button>
        </div>
        <div class="insp-pad" id="insp-body"></div>
      </aside>
    </div>
    <div class="insp-backdrop" id="insp-backdrop" hidden></div>
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
    };
    const KIND_COLOR = { source: "#0ea5a4", capture: "#d97706", memory: "#7c3aed", project: "#2563eb" };
    const KIND_LABEL = { source: "Source", capture: "Capture", memory: "Memory", project: "Project" };

    // ---- indices ----
    const byId = new Map();
    [...graph.sources, ...graph.sections, ...graph.runtimes].forEach(n => byId.set(n.id, n));
    const srcEdges = graph.edges.filter(e => e.relation === "source_to_section");
    const rtEdges = graph.edges.filter(e => e.relation === "section_to_runtime");
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
    function lineDiff(oldText, newText) {
      const a = String(oldText || "").split("\n"), b = String(newText || "").split("\n");
      const m = a.length, n = b.length;
      const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
      for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--)
        dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
      const out = []; let i = 0, j = 0;
      while (i < m && j < n) {
        if (a[i] === b[j]) { out.push(["ctx", a[i]]); i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(["del", a[i]]); i++; }
        else { out.push(["add", b[j]]); j++; }
      }
      while (i < m) out.push(["del", a[i++]]);
      while (j < n) out.push(["add", b[j++]]);
      return out;
    }
    function diffBlock(oldText, newText, caption) {
      const rows = lineDiff(oldText, newText).map(([t, l]) => {
        const cls = t === "add" ? " d-add" : t === "del" ? " d-del" : "";
        const sign = t === "add" ? "+" : t === "del" ? "−" : " ";
        return '<div class="code-line' + cls + '"><span class="ln">' + sign + '</span><span class="lc">' + esc(l || " ") + "</span></div>";
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
    const orderedSources = [...graph.sources].sort((a, b) => {
      const ko = ["source", "capture", "memory", "project"];
      return ko.indexOf(a.kind) - ko.indexOf(b.kind) || a.label.localeCompare(b.label);
    });

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
    };

    // ---- DOM render: lanes ----
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
      el.addEventListener("click", () => select(n.id));
      el.addEventListener("mouseenter", () => hover(n.id));
      el.addEventListener("mouseleave", () => hover(null));
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
      groupByLayer(orderedSources).forEach(([layer, items]) => {
        groupLabel(laneSources, layer, items.length);
        items.forEach(s => {
          const st = nodeStatus(s);
          laneSources.appendChild(nodeEl(s, "source",
            '<div class="row">' +
              '<span class="kind-ic" style="background:' + (KIND_COLOR[s.kind] || "#94a3b8") + '">' + (ICONS[s.kind] || ICONS.source) + "</span>" +
              '<span class="name">' + esc(s.label) + "</span>" + statusDot(st) +
            "</div>" +
            '<div class="ptr">' + esc(s.pointer) + "</div>" +
            (s.status === "missing" ? '<div class="tags">' + tag("未解析 missing", "var(--missing)") + "</div>" : "")
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
          laneSections.appendChild(nodeEl(s, "section",
            '<div class="row">' +
              '<span class="kind-ic" style="background:#475569">' + ICONS.section + "</span>" +
              '<span class="name">' + esc(s.name) + "</span>" + statusDot(rs) +
            "</div>" +
            '<div class="tags">' +
              tag(rs, STATUS_COLOR[rs]) +
              ((s.type && s.type !== rs) ? tag(s.type) : "") +
              (rtEdgesFrom(s.id).length ? tag((cstat === "exact" ? "exact→runtime" : "runtime?"), STATUS_COLOR[cstat]) : "") +
            "</div>"
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
            '<span class="kind-ic" style="background:#0f766e">' + ICONS.runtime + "</span>" +
            '<span class="name">' + esc(r.config) + "</span>" + statusDot(st) +
          "</div>" +
          '<div class="ptr">' + esc(r.path) + "</div>" +
          '<div class="tags">' + tag(r.target, "var(--exact)") + (mc ? tag(mc + " mirror") : "") + "</div>"
        );
        laneRuntimes.appendChild(el);
      });
    }

    // ---- SVG links ----
    const svg = document.getElementById("links");
    const lanes = document.getElementById("lanes");
    let pathByEdge = new Map();
    function elFor(id) { return lanes.querySelector('.node[data-id="' + cssEsc(id) + '"]'); }
    function cssEsc(s) { return (window.CSS && CSS.escape) ? CSS.escape(s) : String(s).replace(/"/g, '\\"'); }

    function drawLinks() {
      svg.innerHTML = "";
      pathByEdge = new Map();
      const wrap = lanes.getBoundingClientRect();
      const NS = "http://www.w3.org/2000/svg";
      graph.edges.forEach(e => {
        const a = elFor(e.from_id), b = elFor(e.to_id);
        if (!a || !b) return;
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
        if (e.status === "uncertain" || e.status === "missing") p.setAttribute("stroke-dasharray", "4 4");
        if (e.change === "removed") p.setAttribute("stroke-dasharray", "2 4");
        p.dataset.from = e.from_id;
        p.dataset.to = e.to_id;
        p.dataset.status = e.status;
        svg.appendChild(p);
        const key = e.from_id + "|" + e.to_id;
        (pathByEdge.get(key) || pathByEdge.set(key, []).get(key)).push(p);
      });
      applyHighlight();
    }

    // ---- highlight / selection ----
    let selectedId = null, hoverId = null, inspectorMax = false, activeTab = 0;

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
      const focusId = hoverId || selectedId;
      const focus = focusId ? lineage(focusId) : null;
      lanes.querySelectorAll(".node").forEach(el => {
        el.classList.toggle("sel", el.dataset.id === selectedId);
        el.classList.toggle("hit", !!focus && focus.has(el.dataset.id) && el.dataset.id !== selectedId);
      });
      svg.querySelectorAll("path").forEach(p => {
        const on = focus && focus.has(p.dataset.from) && focus.has(p.dataset.to);
        if (on) {
          p.setAttribute("stroke", STATUS_COLOR[p.dataset.status] || "var(--accent)");
          p.setAttribute("stroke-width", "2.4");
          p.setAttribute("opacity", "1");
        } else {
          p.setAttribute("stroke", "var(--line)");
          p.setAttribute("stroke-width", "1.5");
          p.setAttribute("opacity", focus ? "0.35" : "1");
        }
      });
    }
    function hover(id) { hoverId = id; applyHighlight(); }
    function select(id) {
      const changed = selectedId !== id;
      selectedId = (selectedId === id) ? null : id;
      if (changed) activeTab = 0;
      applyHighlight();
      renderInspector();
      const el = selectedId ? elFor(selectedId) : null;
      if (el) el.scrollIntoView({ block: "nearest", behavior: "smooth" });
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
    function renderInspector() {
      wideLayout = isWide();
      const n = selectedId ? byId.get(selectedId) : null;
      if (!n) inspBody.innerHTML = overviewHTML();
      else if (graph.sources.includes(n)) inspBody.innerHTML = sourceHTML(n);
      else if (graph.runtimes.includes(n)) inspBody.innerHTML = runtimeHTML(n);
      else inspBody.innerHTML = sectionHTML(n);
      bindInspector();
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
      const consumers = srcEdgesFrom(s.id);
      const head = eyebrow((KIND_LABEL[s.kind] || s.kind) + " Source", nodeStatus(s)) +
        '<h2 class="insp-title">' + esc(s.label) + "</h2>" +
        '<p class="insp-sub">' + esc(s.pointer) + "</p>" +
        changeBanner(s);
      const content =
        '<div class="kv">' +
          '<span class="k">架构层</span><span class="v">' + tag(s.layer || "core", "var(--accent)") + "</span>" +
          '<span class="k">kind</span><span class="v">' + esc(KIND_LABEL[s.kind] || s.kind || "") + "</span>" +
          '<span class="k">位置</span><span class="v">' + esc(pos(s.position)) + "</span>" +
          '<span class="k">状态</span><span class="v">' + (s.status === "missing" ? tag("未解析 missing", "var(--missing)") : tag("已解析 resolved", "var(--exact)")) + "</span>" +
        "</div>" +
        '<div class="insp-section">' +
          ((s.content_excerpt || s.prev_content) ? contentBlock(s, s.content_excerpt, s.position && s.position.start_line, esc(s.pointer))
            : '<div class="empty">摘录不可用（目录或缺失文件）。</div>') +
        "</div>";
      const lineage = consumers.length
        ? '<div class="lineage">' + consumers.map(e => '<div class="lin-row">' + nodelink(byId.get(e.to_id), e.status) + "</div>").join("") + "</div>"
        : '<div class="empty">没有 section 声明引用它。</div>';
      return head + tabbed([["Content", content], ["进入的 Section", lineage, consumers.length]]);
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
        b.addEventListener("click", () => { selectedId = id; activeTab = 0; applyHighlight(); renderInspector();
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
    let changedOnly = false;
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
    document.getElementById("cnt-sources").textContent = graph.sources.length;
    document.getElementById("cnt-sections").textContent = graph.sections.length;
    document.getElementById("cnt-runtimes").textContent = graph.runtimes.length;
    mountCounts();
    // ---- Audit / Review mode toggle ----
    let reviewView = diffMode;
    const modeReview = document.getElementById("mode-review");
    function applyMode() {
      document.body.classList.toggle("audit-view", !reviewView);
      document.querySelectorAll("#mode-seg .seg-btn").forEach(b =>
        b.classList.toggle("active", (b.dataset.mode === "review") === reviewView));
      renderInspector();
    }
    if (!diffMode) { modeReview.disabled = true; modeReview.title = "用 forge audit portal --diff 生成以启用变更评审"; }
    document.querySelectorAll("#mode-seg .seg-btn").forEach(b => b.addEventListener("click", () => {
      if (b.dataset.mode === "review" && !diffMode) return;
      reviewView = b.dataset.mode === "review";
      applyMode();
    }));
    applyMode();
    renderSources(); renderSections(); renderRuntimes();
    renderInspector();
    requestAnimationFrame(drawLinks);

    // ---- events ----
    const input = document.getElementById("search");
    input.addEventListener("input", () => { query = input.value.trim().toLowerCase(); applyFilters(); });
    document.querySelectorAll(".chip.filter").forEach(btn => btn.addEventListener("click", () => {
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
      const d = graph.diff;
      const pill = document.getElementById("diff-pill");
      pill.hidden = false;
      pill.innerHTML = "改动评审 base=" + esc(d.base_ref) + " · <b>+" + d.added + "</b> ~" + d.modified + " −" + d.removed;
      changedBtn.addEventListener("click", () => { changedOnly = !changedOnly; changedBtn.setAttribute("aria-pressed", String(changedOnly)); applyFilters(); });
    }
    document.getElementById("reset-view").addEventListener("click", () => {
      selectedId = null; hoverId = null; query = ""; input.value = ""; gapsOnly = false; changedOnly = false;
      gapsBtn.setAttribute("aria-pressed", "false");
      changedBtn.setAttribute("aria-pressed", "false");
      activeStatus.clear(); ["exact", "derived", "declared", "uncertain", "missing", "wrapper"].forEach(s => activeStatus.add(s));
      document.querySelectorAll(".chip.filter").forEach(b => b.setAttribute("aria-pressed", "true"));
      applyFilters(); applyHighlight(); renderInspector();
    });
    document.getElementById("canvas").addEventListener("click", (e) => {
      if (e.target.closest(".node")) return;
      if (selectedId) { selectedId = null; applyHighlight(); renderInspector(); }
    });
    // ---- inspector expand / collapse ----
    const inspector = document.getElementById("inspector");
    const backdrop = document.getElementById("insp-backdrop");
    const expandBtn = document.getElementById("insp-expand");
    function setMax(v) {
      inspectorMax = v;
      inspector.classList.toggle("max", v);
      backdrop.hidden = !v;
      expandBtn.textContent = v ? "⤡" : "⤢";
      expandBtn.title = v ? "收起详情（E / Esc）" : "展开详情（E）";
      renderInspector();
    }
    expandBtn.addEventListener("click", () => setMax(!inspectorMax));
    backdrop.addEventListener("click", () => setMax(false));

    // ---- divider drag (resize the docked inspector) ----
    const splitEl = document.querySelector(".split");
    const divider = document.getElementById("divider");
    const WKEY = "forge-audit-insp-w";
    function setInspW(px, persist) {
      const max = Math.min(window.innerWidth * 0.72, 1120);
      const w = Math.max(360, Math.min(px, max));
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
      drawLinks();
    });
    divider.addEventListener("pointerup", () => {
      if (!dragging) return;
      dragging = false; divider.classList.remove("drag"); document.body.classList.remove("dragging");
      setInspW(inspectorEl.getBoundingClientRect().width, true);
      renderInspector(); drawLinks();
    });
    divider.addEventListener("dblclick", () => { setInspW(620, true); renderInspector(); drawLinks(); });

    document.addEventListener("keydown", (e) => {
      if (e.key === "/" && document.activeElement !== input) { e.preventDefault(); input.focus(); input.select(); }
      if ((e.key === "e" || e.key === "E") && document.activeElement !== input) { e.preventDefault(); setMax(!inspectorMax); }
      if (e.key === "Escape") {
        if (document.activeElement === input) { input.blur(); }
        else if (inspectorMax) { setMax(false); }
        else if (selectedId) { selectedId = null; applyHighlight(); renderInspector(); }
      }
    });
    let rt;
    window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { renderInspector(); drawLinks(); }, 120); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => drawLinks());
  })();
  </script>
</body>
</html>
"""
