from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor


@dataclass(frozen=True, slots=True)
class TextStyle:
    foreground: QColor | None = None
    background: QColor | None = None
    bold: bool = False
    underline: bool = False
    reverse: bool = False


@dataclass(slots=True)
class BufferCell:
    char: str
    style: TextStyle


@dataclass(slots=True)
class BufferLine:
    cells: list[BufferCell]
    wrapped: bool = False

    def text(self) -> str:
        return "".join(cell.char for cell in self.cells)


class ScreenBuffer:
    def __init__(self, rows: int = 40, columns: int = 140, history_limit: int = 50_000) -> None:
        self.rows = max(1, rows)
        self.columns = max(1, columns)
        self.history_limit = max(1, history_limit)
        self.history: list[BufferLine] = [BufferLine([])]
        self.history_offset = 0
        self.revision = 0
        self.cursor_row = 0
        self.cursor_column = 0
        self.viewport_top = 0
        self.follow_bottom = True
        self.current_style = TextStyle()
        self._saved_cursor: tuple[int, int, TextStyle] | None = None
        self._trim_history()
        self.jump_bottom()

    def write_text(self, text: str) -> None:
        for char in text:
            if char == "\n":
                self.newline()
            elif char == "\r":
                self.carriage_return()
            elif char == "\b":
                self.backspace()
            else:
                self._write_char(char)
        self._follow_if_needed()

    def newline(self) -> None:
        self.cursor_column = 0
        if self.cursor_row < len(self.history) - 1:
            self.cursor_row += 1
        else:
            self.history.append(BufferLine([], wrapped=True))
            self.cursor_row = len(self.history) - 1
            self._trim_history()
        self._touch()
        self._follow_if_needed()

    def carriage_return(self) -> None:
        self.cursor_column = 0

    def backspace(self) -> None:
        line = self._current_line()
        if self.cursor_column > 0:
            index = self.cursor_column - 1
            if index < len(line.cells):
                del line.cells[index]
            self.cursor_column = max(0, self.cursor_column - 1)
            self._touch()
            return
        if self.cursor_row > 0:
            self.cursor_row -= 1
            prev_line = self._current_line()
            self.cursor_column = len(prev_line.cells)
            if prev_line.cells:
                prev_line.cells.pop()
            self._touch()
        self._follow_if_needed()

    def clear_line(self, mode: int) -> None:
        line = self._current_line()
        if mode == 2:
            line.cells.clear()
            self.cursor_column = 0
            self._touch()
            return
        if mode == 0:
            del line.cells[self.cursor_column :]
            self._touch()
            return
        if mode == 1:
            del line.cells[: self.cursor_column + 1]
            self.cursor_column = 0
            self._touch()

    def clear_screen(self, mode: int) -> None:
        if mode == 2:
            self.history = [BufferLine([])]
            self.history_offset = 0
            self.revision += 1
            self.cursor_row = 0
            self.cursor_column = 0
            self.viewport_top = 0
            self.follow_bottom = True
            self.current_style = TextStyle()
            self._saved_cursor = None
            return
        if mode == 0:
            self.clear_line(0)
            for line in self.history[self.cursor_row + 1 :]:
                line.cells.clear()
            self._touch()
            return
        if mode == 1:
            for line in self.history[: self.cursor_row]:
                line.cells.clear()
            self.clear_line(1)
            self._touch()

    def resize(self, rows: int, columns: int) -> None:
        self.rows = max(1, rows)
        self.columns = max(1, columns)
        if self.follow_bottom:
            self.jump_bottom()
        else:
            self.viewport_top = min(self.viewport_top, self.max_viewport_top())
        self.cursor_column = min(self.cursor_column, self.columns - 1)
        self.cursor_row = min(self.cursor_row, len(self.history) - 1)

    def scroll_up(self, amount: int = 1) -> None:
        self.follow_bottom = False
        self.viewport_top = max(0, self.viewport_top - max(1, amount))

    def scroll_down(self, amount: int = 1) -> None:
        self.viewport_top = min(self.max_viewport_top(), self.viewport_top + max(1, amount))
        self.follow_bottom = self.viewport_top >= self.max_viewport_top()

    def jump_top(self) -> None:
        self.follow_bottom = False
        self.viewport_top = 0

    def jump_bottom(self) -> None:
        self.follow_bottom = True
        self.viewport_top = self.max_viewport_top()

    def move_cursor(self, direction: str, amount: int) -> None:
        amount = max(1, amount)
        if direction == "A":
            self.cursor_row = max(0, self.cursor_row - amount)
        elif direction == "B":
            self.cursor_row = min(len(self.history) - 1, self.cursor_row + amount)
        elif direction == "C":
            self.cursor_column = min(self.columns - 1, self.cursor_column + amount)
        elif direction == "D":
            self.cursor_column = max(0, self.cursor_column - amount)

    def position_cursor(self, row: int, column: int) -> None:
        self.cursor_row = max(0, min(len(self.history) - 1, row - 1))
        self.cursor_column = max(0, min(self.columns - 1, column - 1))

    def save_cursor(self) -> None:
        self._saved_cursor = (self.cursor_row, self.cursor_column, self.current_style)

    def restore_cursor(self) -> None:
        if self._saved_cursor is not None:
            self.cursor_row, self.cursor_column, self.current_style = self._saved_cursor

    def set_style(self, style: TextStyle) -> None:
        self.current_style = style

    def clone_style(self) -> TextStyle:
        return TextStyle(
            foreground=self.current_style.foreground,
            background=self.current_style.background,
            bold=self.current_style.bold,
            underline=self.current_style.underline,
            reverse=self.current_style.reverse,
        )

    def visible_lines(self) -> list[BufferLine]:
        if not self.history:
            return [BufferLine([])]
        start = min(self.viewport_top, self.max_viewport_top())
        end = min(len(self.history), start + self.rows)
        lines = self.history[start:end]
        return lines or [BufferLine([])]

    def history_count(self) -> int:
        return len(self.history)

    def max_viewport_top(self) -> int:
        return max(0, len(self.history) - self.rows)

    def _write_char(self, char: str) -> None:
        if self.cursor_row >= len(self.history):
            self.history.append(BufferLine([]))
        if self.cursor_column >= self.columns:
            self.newline()
        line = self._current_line()
        cell = BufferCell(char=char, style=self.clone_style())
        if self.cursor_column < len(line.cells):
            line.cells[self.cursor_column] = cell
        else:
            while len(line.cells) < self.cursor_column:
                line.cells.append(BufferCell(" ", self.clone_style()))
            line.cells.append(cell)
        self.cursor_column += 1
        if self.cursor_column >= self.columns:
            line.wrapped = True
            self.newline()
        self._follow_if_needed()
        self._touch()

    def _trim_history(self) -> None:
        while len(self.history) > self.history_limit:
            self.history.pop(0)
            self.history_offset += 1
            if self.cursor_row > 0:
                self.cursor_row -= 1
            if self.viewport_top > 0:
                self.viewport_top -= 1
        self.viewport_top = min(self.viewport_top, self.max_viewport_top())
        self.cursor_row = max(0, min(self.cursor_row, len(self.history) - 1))
        self._touch()

    def _follow_if_needed(self) -> None:
        if self.follow_bottom:
            self.jump_bottom()
        else:
            self.viewport_top = min(self.viewport_top, self.max_viewport_top())

    def _current_line(self) -> BufferLine:
        if not self.history:
            self.history = [BufferLine([])]
        self.cursor_row = max(0, min(self.cursor_row, len(self.history) - 1))
        return self.history[self.cursor_row]

    def all_lines(self) -> list[BufferLine]:
        return list(self.history)

    def cursor_index(self) -> int:
        index = 0
        for row, line in enumerate(self.history):
            if row < self.cursor_row:
                index += len(line.cells) + 1
            elif row == self.cursor_row:
                index += min(self.cursor_column, len(line.cells))
                break
        return index

    def _touch(self) -> None:
        self.revision += 1
