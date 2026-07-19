from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QApplication

from .screen_buffer import ScreenBuffer
from .selection import SelectionEngine


class ClipboardEngine:
    def __init__(
        self,
        selection_engine: SelectionEngine,
        *,
        bracketed_paste: bool = True,
        osc52_sink: Callable[[str], None] | None = None,
    ) -> None:
        self.selection_engine = selection_engine
        self.bracketed_paste = bracketed_paste
        self.osc52_sink = osc52_sink

    def copy_selection(self, buffer: ScreenBuffer) -> str:
        text = self.selection_engine.selected_text(buffer)
        if not text:
            return ""
        text = self.normalize_copied_text(text)
        QApplication.clipboard().setText(text)
        if self.osc52_sink is not None:
            self.osc52_sink(text)
        return text

    def paste_from_clipboard(self) -> str:
        return self.prepare_paste_text(QApplication.clipboard().text())

    def prepare_paste_text(self, text: str) -> str:
        text = self.normalize_pasted_text(text)
        if not text:
            return ""
        if self.bracketed_paste:
            return f"\x1b[200~{text}\x1b[201~"
        return text

    @staticmethod
    def normalize_copied_text(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def normalize_pasted_text(text: str) -> str:
        return text.replace("\r\n", "\n").replace("\r", "\n")
