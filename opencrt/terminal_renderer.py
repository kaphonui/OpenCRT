from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit

from .screen_buffer import BufferLine, ScreenBuffer, TextStyle
from .selection import SelectionEngine
from .hyperlink import HyperlinkEngine
from .terminal_search import TerminalSearchEngine


class TerminalRenderer:
    def __init__(
        self,
        widget: QPlainTextEdit,
        selection_engine: SelectionEngine | None = None,
        search_engine: TerminalSearchEngine | None = None,
        hyperlink_engine: HyperlinkEngine | None = None,
    ) -> None:
        self.widget = widget
        self.selection_engine = selection_engine
        self.search_engine = search_engine
        self.hyperlink_engine = hyperlink_engine

    def render(self, buffer: ScreenBuffer) -> None:
        lines = buffer.visible_lines()
        self.widget.blockSignals(True)
        try:
            QPlainTextEdit.clear(self.widget)
            cursor = self.widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            base_line = buffer.history_offset + buffer.viewport_top
            for index, line in enumerate(lines):
                abs_line = base_line + index
                self._insert_line(cursor, buffer, abs_line, line)
                if index < len(lines) - 1:
                    cursor.insertBlock()
            self.widget.setTextCursor(cursor)
        finally:
            self.widget.blockSignals(False)

    def _insert_line(self, cursor: QTextCursor, buffer: ScreenBuffer, abs_line: int, line: BufferLine) -> None:
        if not line.cells:
            cursor.insertText("")
            return
        for column, cell in enumerate(line.cells):
            cursor.insertText(cell.char, self._format_for_style(cell.style, buffer, abs_line, column))

    def _format_for_style(self, style: TextStyle, buffer: ScreenBuffer, abs_line: int, column: int) -> QTextCharFormat:
        fmt = QTextCharFormat()
        base_fg = self.widget.palette().text().color()
        base_bg = self.widget.palette().base().color()
        foreground = style.foreground or base_fg
        background = style.background or base_bg
        if style.reverse:
            foreground, background = background, foreground
        selected = self.selection_engine.contains(buffer, abs_line, column) if self.selection_engine else False
        hyperlink_style = self._hyperlink_style(buffer, abs_line, column)
        if hyperlink_style is not None:
            foreground, underline = hyperlink_style
            fmt.setFontUnderline(underline)
        search_style = self._search_style(buffer, abs_line, column)
        if search_style is not None and not selected:
            foreground, background = search_style
        if selected:
            foreground, background = QColor("#ffffff"), QColor("#2f81f7")
        fmt.setForeground(foreground)
        fmt.setBackground(background)
        if style.bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if style.underline:
            fmt.setFontUnderline(True)
        return fmt

    def _hyperlink_style(self, buffer: ScreenBuffer, abs_line: int, column: int) -> tuple[QColor, bool] | None:
        if self.hyperlink_engine is None:
            return None
        link = self.hyperlink_engine.link_at(buffer, abs_line, column)
        if link is None:
            return None
        color = QColor("#b48ead") if self.hyperlink_engine.is_visited(buffer, link) else QColor("#61afef")
        return color, self.hyperlink_engine.is_hovered(link)

    def _search_style(self, buffer: ScreenBuffer, abs_line: int, column: int) -> tuple[QColor, QColor] | None:
        if self.search_engine is None:
            return None
        matches = self.search_engine.matches_for_line(abs_line)
        current = self.search_engine.current_match()
        for match in matches:
            if match.start <= column < match.end:
                if current == match:
                    return QColor("#0e1116"), QColor("#ffb86c")
                return QColor("#0e1116"), QColor("#f5d76e")
        return None
