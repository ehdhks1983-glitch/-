"""Reusable CustomTkinter widgets (the only place that touches Tk geometry).

Generic, data-driven widgets keep the per-tab code tiny: a tab is just a list
of :class:`~core.forms.FieldSpec` plus a Save button.
"""

from __future__ import annotations

from typing import Dict, Tuple

import customtkinter as ctk

from core.forms import FieldSpec, default_for
from core.settings_store import SettingsStore
from core.ui_bridge import LogQueue

_TOAST_COLORS = {
    "info": "#2563eb",
    "success": "#16a34a",
    "error": "#dc2626",
    "warn": "#d97706",
}


class Toast(ctk.CTkToplevel):
    """A small, auto-dismissing notification near the top of the parent window."""

    def __init__(self, master, text: str, kind: str = "info", duration_ms: int = 2600) -> None:
        super().__init__(master)
        self.overrideredirect(True)
        try:
            self.attributes("-topmost", True)
        except Exception:  # pragma: no cover - platform dependent
            pass
        color = _TOAST_COLORS.get(kind, _TOAST_COLORS["info"])
        frame = ctk.CTkFrame(self, fg_color=color, corner_radius=8)
        frame.pack(fill="both", expand=True)
        ctk.CTkLabel(frame, text=text, text_color="white").pack(padx=16, pady=10)
        self.update_idletasks()
        try:
            px, py = master.winfo_rootx(), master.winfo_rooty()
            pw, w = master.winfo_width(), self.winfo_width()
            self.geometry(f"+{px + max(0, (pw - w) // 2)}+{py + 30}")
        except Exception:  # pragma: no cover
            pass
        self.after(duration_ms, self.destroy)


class LogPanel(ctk.CTkFrame):
    """Read-only, auto-scrolling log view fed by a :class:`LogQueue`.

    Drains the queue on a Tk ``after`` timer (main thread only) so worker
    threads never touch widgets.  Old lines are trimmed to keep memory bounded.
    """

    def __init__(self, master, log_queue: LogQueue, poll_ms: int = 250, max_lines: int = 2000) -> None:
        super().__init__(master)
        self._q = log_queue
        self._poll_ms = poll_ms
        self._max_lines = max_lines
        self._lines = 0
        self._running = False

        ctk.CTkLabel(self, text="실시간 로그 / Live Log", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
        self._box = ctk.CTkTextbox(self, wrap="word", activate_scrollbars=True)
        self._box.configure(state="disabled")
        self._box.pack(fill="both", expand=True, padx=10, pady=8)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._tick()

    def stop(self) -> None:
        self._running = False

    def _tick(self) -> None:
        if not self._running:
            return
        lines = self._q.drain()
        if lines:
            self._append(lines)
        self.after(self._poll_ms, self._tick)

    def _append(self, lines) -> None:
        self._box.configure(state="normal")
        for ln in lines:
            self._box.insert("end", ln + "\n")
            self._lines += 1
        if self._lines > self._max_lines:
            remove = self._lines - self._max_lines
            self._box.delete("1.0", f"{remove + 1}.0")
            self._lines = self._max_lines
        self._box.see("end")
        self._box.configure(state="disabled")


class FormFrame(ctk.CTkScrollableFrame):
    """Builds labelled inputs from a tuple of :class:`FieldSpec` and binds them
    to a :class:`SettingsStore` (load on build, collect on demand)."""

    def __init__(self, master, fields: Tuple[FieldSpec, ...], store: SettingsStore) -> None:
        super().__init__(master)
        self._fields = fields
        self._store = store
        self._inputs: Dict[str, Tuple[str, object]] = {}
        self._build()

    def _build(self) -> None:
        for spec in self._fields:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=6, pady=6)
            ctk.CTkLabel(row, text=spec.label, width=260, anchor="w").pack(side="left", padx=(2, 8))
            self._make_input(row, spec)
            if spec.help:
                ctk.CTkLabel(self, text=spec.help, anchor="w", text_color="#8b95a7",
                             font=ctk.CTkFont(size=11)).pack(fill="x", padx=(270, 6))

    def _make_input(self, parent, spec: FieldSpec) -> None:
        cur = self._store.get_str(spec.key)
        if spec.options:
            var = ctk.StringVar(value=cur or default_for(spec))
            ctk.CTkOptionMenu(parent, values=list(spec.options), variable=var).pack(
                side="left", fill="x", expand=True)
            self._inputs[spec.key] = ("option", var)
        elif spec.multiline:
            box = ctk.CTkTextbox(parent, height=72, wrap="word")
            if cur:
                box.insert("1.0", cur)
            box.pack(side="left", fill="x", expand=True)
            self._inputs[spec.key] = ("multiline", box)
        else:
            entry = ctk.CTkEntry(parent, show="*" if spec.secret else "")
            if spec.placeholder:
                entry.configure(placeholder_text=spec.placeholder)
            if cur:
                entry.insert(0, cur)
            entry.pack(side="left", fill="x", expand=True)
            self._inputs[spec.key] = ("entry", entry)

    def collect(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, (kind, widget) in self._inputs.items():
            if kind == "option":
                out[key] = widget.get()                       # type: ignore[union-attr]
            elif kind == "multiline":
                out[key] = widget.get("1.0", "end").strip()   # type: ignore[union-attr]
            else:
                out[key] = widget.get().strip()               # type: ignore[union-attr]
        return out

    def apply_to_store(self) -> None:
        self._store.update(self.collect())


class SettingsTab(ctk.CTkFrame):
    """A titled settings page: heading + scrollable form + Save button."""

    def __init__(self, master, title: str, subtitle: str, fields: Tuple[FieldSpec, ...],
                 store: SettingsStore, on_saved=None) -> None:
        super().__init__(master)
        self._store = store
        self._on_saved = on_saved

        ctk.CTkLabel(self, text=title, anchor="w",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(fill="x", padx=16, pady=(16, 0))
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, anchor="w", text_color="#8b95a7").pack(
                fill="x", padx=16, pady=(0, 8))

        self.form = FormFrame(self, fields, store)
        self.form.pack(fill="both", expand=True, padx=10, pady=6)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=16, pady=(0, 14))
        ctk.CTkButton(bar, text="저장 / Save", command=self._save).pack(side="right")

    def _save(self) -> None:
        self.form.apply_to_store()
        try:
            self._store.save()
            Toast(self.winfo_toplevel(), "설정이 저장되었습니다 / Saved", kind="success")
        except Exception as exc:  # pragma: no cover - disk error path
            Toast(self.winfo_toplevel(), f"저장 실패: {exc}", kind="error")
            return
        if self._on_saved:
            self._on_saved()
