"""TUI for `forge review --tui` — keyboard-driven review screen.

For users in their own terminal. Not callable from agent's Bash tool (no real
TTY). Agent uses `forge review` (text panels) instead.

Layout:
    ┌─ forge review · <workspace> ──────────────────────────┐
    │ Source / Touched (left)        │  Affects (right)     │
    ├────────────────────────────────┴───────────────────────┤
    │ Bench                                                  │
    ├────────────────────────────────────────────────────────┤
    │ Diff (scrollable, syntax-colored +/-)                  │
    └────────────────────────────────────────────────────────┘
      [a] approve  [r] reject  [e] edit  [d] diff  [q] quit

Approve flow: prompt for commit message → call gate.approve.
Reject flow: confirm → call gate.reject.
Edit flow: list sections → user picks → spawn $EDITOR.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, Static

from forge.gate import actions as gate
from forge.gate.review import ReviewSummary, build_review


class ReviewApp(App):
    """Single-screen review TUI: panels + diff + actions."""

    CSS = """
    #panels {
        height: auto;
        max-height: 50%;
        border: round $primary;
        padding: 0 1;
    }
    #panels-row {
        height: auto;
    }
    .panel {
        width: 1fr;
        padding: 0 1;
        height: auto;
    }
    .panel-title {
        color: $accent;
        text-style: bold;
    }
    .warn {
        color: $warning;
        text-style: bold;
    }
    .empty-msg {
        color: $text-muted;
        padding: 2 4;
    }
    #diff-container {
        border: round $primary;
        padding: 0 1;
    }
    #diff-title {
        color: $accent;
        text-style: bold;
    }
    .diff-add {
        color: $success;
    }
    .diff-del {
        color: $error;
    }
    .diff-hunk {
        color: $accent;
    }
    .diff-file {
        color: $text;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("a", "approve", "Approve"),
        Binding("r", "reject", "Reject"),
        Binding("e", "edit_section", "Edit section"),
        Binding("d", "toggle_diff_only", "Diff only"),
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
    ]

    diff_only = reactive(False)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = root
        self.review: ReviewSummary | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        if self.diff_only:
            yield from self._compose_diff_only()
        else:
            yield from self._compose_full()
        yield Footer()

    def _compose_full(self) -> ComposeResult:
        with Vertical(id="panels"):
            with Horizontal(id="panels-row"):
                yield Static(self._source_panel_text(), classes="panel", id="source-panel")
                yield Static(self._affects_panel_text(), classes="panel", id="affects-panel")
            yield Static(self._bench_panel_text(), classes="panel", id="bench-panel")
        with VerticalScroll(id="diff-container"):
            yield Static("── Diff ──", id="diff-title")
            yield Static(self._diff_text(), id="diff-body", markup=False)

    def _compose_diff_only(self) -> ComposeResult:
        with VerticalScroll(id="diff-container"):
            yield Static("── Diff (full screen, press d to return) ──", id="diff-title")
            yield Static(self._diff_text(), id="diff-body", markup=False)

    def on_mount(self) -> None:
        self.title = "forge review"
        self.sub_title = str(self.root)
        self.review = build_review(self.root)
        if not self.review.has_changes:
            self.notify("No changes since last approve", severity="information")
            self.exit()
            return

    # ---------- panels ----------

    def _source_panel_text(self) -> str:
        if not self.review:
            return ""
        lines = ["[bold]── Source ──[/bold]"]
        if self.review.origin_events:
            for ev in self.review.origin_events:
                lines.append(f"[bold]Origin[/bold]:  {ev.summary}")
                ts = ev.at.replace("T", " ").rsplit("+", 1)[0]
                lines.append(f"           {ts} UTC")
        else:
            lines.append("[bold]Origin[/bold]:  hand edit (no recorded ingest/event)")
        n = len(self.review.section_changes)
        lines.append(f"[bold]Touched[/bold]: {n} section{'s' if n != 1 else ''}")
        lines.append("")
        for sc in self.review.section_changes:
            sign = "+" if sc.bytes_delta >= 0 else ""
            warn = ""
            if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
                warn = f" [bold yellow]⚠ {sc.growth_pct:+.0f}%[/bold yellow]"
            lines.append(f"  • {sc.name}: {sign}{sc.bytes_delta}B{warn}")
            lines.append(f"      {sc.summary}")
        return "\n".join(lines)

    def _affects_panel_text(self) -> str:
        if not self.review:
            return ""
        lines = ["[bold]── Affects ──[/bold]"]
        if self.review.output_changes:
            lines.append("[bold]Outputs[/bold] (rebuild on approve):")
            for oc in self.review.output_changes:
                sign = "+" if oc.bytes_delta >= 0 else ""
                lines.append(f"  • output/{oc.filename} ({sign}{oc.bytes_delta}B)")
                lines.append(f"      ← {oc.runtime_description}")
        else:
            lines.append("(no output changes)")
        lines.append("")
        if self.review.target_bindings:
            lines.append("[bold]Targets[/bold] (auto-sync):")
            for tb in self.review.target_bindings:
                lines.append(f"  • {tb.path}  [{tb.mode}]")
        else:
            lines.append("[yellow]No external target bound.[/yellow]")
            lines.append("(approve only updates output/)")
        return "\n".join(lines)

    def _bench_panel_text(self) -> str:
        if not self.review:
            return ""
        lines = ["[bold]── Bench ──[/bold]"]
        if not self.review.section_changes:
            lines.append("(no section-level changes)")
        for sc in self.review.section_changes:
            sign = "+" if sc.bytes_delta >= 0 else ""
            line = f"  {sc.name:18} {sign}{sc.bytes_delta:>6}B  ({sc.bytes_before} → {sc.bytes_after})"
            if abs(sc.growth_pct) >= 50 and sc.bytes_before > 0:
                line += f"  [bold yellow]⚠ {sc.growth_pct:+.0f}%[/bold yellow]"
            lines.append(line)
        return "\n".join(lines)

    def _diff_text(self) -> str:
        if not self.review or not self.review.diff_result:
            return "(no diff)"
        diff = self.review.diff_result
        out: list[str] = []
        out.append("--- source diff (sp/) ---")
        if diff.source_diff_lines:
            out.extend(diff.source_diff_lines)
        else:
            out.append("(no source changes)")
        out.append("")
        out.append("--- output diff (per config) ---")
        for cname, lines in diff.output_diffs.items():
            out.append(f"▸ {cname}")
            out.extend(lines)
            out.append("")
        return "\n".join(out)

    # ---------- actions ----------

    def action_approve(self) -> None:
        self.push_screen(ApproveScreen(), self._after_approve)

    def _after_approve(self, message: str | None) -> None:
        if not message:
            return
        try:
            result = gate.approve(self.root, note=message)
        except RuntimeError as e:
            self.notify(f"approve failed: {e}", severity="error")
            return
        msg = f"approved {result.approved_hash[:7]} · {len(result.outputs_written)} output(s)"
        if result.targets_synced:
            msg += f" · {len(result.targets_synced)} target(s) synced"
        self.notify(msg, severity="information", timeout=6)
        self.exit(message=msg)

    def action_reject(self) -> None:
        self.push_screen(ConfirmScreen("Discard all working-tree changes? [y/N]"), self._after_reject)

    def _after_reject(self, confirmed: bool | None) -> None:
        if not confirmed:
            return
        try:
            gate.reject(self.root)
        except RuntimeError as e:
            self.notify(f"reject failed: {e}", severity="error")
            return
        self.notify("rejected — sp/ + output/ restored from HEAD", severity="warning")
        self.exit(message="rejected")

    def action_edit_section(self) -> None:
        if not self.review:
            return
        names = sorted({sc.name for sc in self.review.section_changes})
        if not names:
            self.notify("No changed section to edit", severity="warning")
            return
        self.push_screen(SectionPickerScreen(names), self._after_pick_section)

    def _after_pick_section(self, name: str | None) -> None:
        if not name:
            return
        path = self.root / "sp" / "section" / f"{name}.md"
        editor = os.environ.get("EDITOR", "vi")
        with self.suspend():
            subprocess.run([editor, str(path)])
        # rebuild review after edit
        self.review = build_review(self.root)
        self._refresh_all()

    def action_toggle_diff_only(self) -> None:
        self.diff_only = not self.diff_only
        self._refresh_all()

    def _refresh_all(self) -> None:
        # remount the body
        self.refresh(layout=True, recompose=True)


class ApproveScreen(ModalScreen[str]):
    """Modal: enter commit message, [Enter] confirms, [Escape] cancels."""

    BINDINGS = [Binding("escape", "dismiss", "Cancel")]

    CSS = """
    ApproveScreen {
        align: center middle;
    }
    #approve-box {
        width: 70;
        height: 7;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="approve-box"):
            yield Label("commit message (Enter to approve, Esc to cancel):")
            yield Input(placeholder="e.g. add no-emoji preference", id="msg-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value or None)


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [
        Binding("y", "yes", "Yes"),
        Binding("n", "no", "No"),
        Binding("escape", "no", "Cancel"),
    ]

    CSS = """
    ConfirmScreen {
        align: center middle;
    }
    #confirm-box {
        width: 60;
        height: 5;
        border: round $error;
        padding: 1 2;
        background: $surface;
    }
    """

    def __init__(self, prompt: str) -> None:
        super().__init__()
        self.prompt = prompt

    def compose(self) -> ComposeResult:
        with Vertical(id="confirm-box"):
            yield Label(self.prompt)
            yield Label("(press y or n)")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class SectionPickerScreen(ModalScreen[str]):
    """Picker: arrow up/down through changed sections, Enter to edit."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
        Binding("enter", "select", "Select"),
        Binding("up,k", "cursor_up", "Up"),
        Binding("down,j", "cursor_down", "Down"),
    ]

    CSS = """
    SectionPickerScreen {
        align: center middle;
    }
    #picker-box {
        width: 60;
        height: auto;
        max-height: 20;
        border: round $primary;
        padding: 1 2;
        background: $surface;
    }
    .picker-item {
        padding: 0 1;
    }
    .picker-item-selected {
        background: $primary;
        color: $text;
        text-style: bold;
        padding: 0 1;
    }
    """

    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self.names = names
        self.cursor = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Label("Edit which section? (↑/↓, Enter, Esc)")
            for i, name in enumerate(self.names):
                cls = "picker-item-selected" if i == self.cursor else "picker-item"
                yield Static(f"  {name}.md", classes=cls, id=f"item-{i}")

    def action_select(self) -> None:
        self.dismiss(self.names[self.cursor])

    def action_cursor_up(self) -> None:
        if self.cursor > 0:
            self.cursor -= 1
            self.refresh(recompose=True)

    def action_cursor_down(self) -> None:
        if self.cursor < len(self.names) - 1:
            self.cursor += 1
            self.refresh(recompose=True)


def run(root: Path) -> int:
    """Entry point called from `forge review --tui`. Returns process exit code."""
    import sys

    if not sys.stdout.isatty() or not sys.stdin.isatty():
        print(
            "error: --tui requires a real terminal. Run `forge review --tui` "
            "in your own terminal (not via an agent's Bash tool).",
            file=sys.stderr,
        )
        return 2

    app = ReviewApp(root)
    app.run()
    return 0
