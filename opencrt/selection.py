from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .screen_buffer import ScreenBuffer


class SelectionMode(Enum):
    NORMAL = auto()
    WORD = auto()
    LINE = auto()
    COLUMN = auto()


@dataclass(frozen=True, slots=True)
class SelectionPoint:
    line: int
    column: int


@dataclass(slots=True)
class Selection:
    anchor: SelectionPoint
    active: SelectionPoint
    mode: SelectionMode


class SelectionEngine:
    def __init__(self) -> None:
        self.selection: Selection | None = None

    def clear(self) -> None:
        self.selection = None

    def begin(self, point: SelectionPoint, mode: SelectionMode = SelectionMode.NORMAL) -> None:
        self.selection = Selection(anchor=point, active=point, mode=mode)

    def update(self, point: SelectionPoint) -> None:
        if self.selection is None:
            self.begin(point)
            return
        self.selection.active = point

    def select_all(self, buffer: ScreenBuffer) -> None:
        if buffer.history_count() == 0:
            self.selection = None
            return
        start = SelectionPoint(buffer.history_offset, 0)
        last_line = buffer.history_offset + buffer.history_count() - 1
        last_text = buffer.history[-1].text() if buffer.history else ""
        end = SelectionPoint(last_line, len(last_text))
        self.selection = Selection(anchor=start, active=end, mode=SelectionMode.NORMAL)

    def select_line(self, buffer: ScreenBuffer, line: int) -> None:
        line = self._clamp_line(buffer, line)
        text = self._line_text(buffer, line)
        start = SelectionPoint(line, 0)
        end = SelectionPoint(line, len(text))
        self.selection = Selection(anchor=start, active=end, mode=SelectionMode.LINE)

    def select_word(self, buffer: ScreenBuffer, line: int, column: int) -> None:
        line = self._clamp_line(buffer, line)
        text = self._line_text(buffer, line)
        if not text:
            self.select_line(buffer, line)
            return
        column = max(0, min(column, len(text)))
        if column == len(text):
            column = max(0, len(text) - 1)
        if text[column].isspace():
            left = column
            while left > 0 and text[left - 1].isspace():
                left -= 1
            right = column
            while right < len(text) and text[right].isspace():
                right += 1
            self.selection = Selection(
                anchor=SelectionPoint(line, left),
                active=SelectionPoint(line, right),
                mode=SelectionMode.WORD,
            )
            return
        left = column
        while left > 0 and not text[left - 1].isspace():
            left -= 1
        right = column
        while right < len(text) and not text[right].isspace():
            right += 1
        self.selection = Selection(
            anchor=SelectionPoint(line, left),
            active=SelectionPoint(line, right),
            mode=SelectionMode.WORD,
        )

    def move_active(self, buffer: ScreenBuffer, line_delta: int = 0, column_delta: int = 0) -> None:
        if self.selection is None:
            self.begin(self._current_point(buffer))
        assert self.selection is not None
        point = self.selection.active
        line = self._clamp_line(buffer, point.line + line_delta)
        text = self._line_text(buffer, line)
        column = max(0, min(point.column + column_delta, len(text)))
        self.selection.active = SelectionPoint(line, column)
        self.selection.mode = SelectionMode.NORMAL

    def contains(self, buffer: ScreenBuffer, abs_line: int, column: int) -> bool:
        if self.selection is None:
            return False
        start, end = self._normalized(buffer)
        if start is None or end is None:
            return False
        if self.selection.mode == SelectionMode.COLUMN:
            left = min(start.column, end.column)
            right = max(start.column, end.column)
            return start.line <= abs_line <= end.line and left <= column < right
        if abs_line < start.line or abs_line > end.line:
            return False
        if start.line == end.line:
            return start.column <= column < end.column
        if abs_line == start.line:
            return column >= start.column
        if abs_line == end.line:
            return column < end.column
        return True

    def line_selection_range(self, buffer: ScreenBuffer, abs_line: int) -> tuple[int, int] | None:
        if self.selection is None:
            return None
        start, end = self._normalized(buffer)
        if start is None or end is None:
            return None
        if abs_line < start.line or abs_line > end.line:
            return None
        line_text = self._line_text(buffer, abs_line)
        line_len = len(line_text)
        if self.selection.mode == SelectionMode.COLUMN:
            left = min(start.column, end.column)
            right = max(start.column, end.column)
            return left, right
        if start.line == end.line:
            return start.column, end.column
        if abs_line == start.line:
            return start.column, line_len
        if abs_line == end.line:
            return 0, end.column
        return 0, line_len

    def selected_text(self, buffer: ScreenBuffer) -> str:
        if self.selection is None:
            return ""
        start, end = self._normalized(buffer)
        if start is None or end is None:
            return ""
        lines: list[str] = []
        if self.selection.mode == SelectionMode.COLUMN:
            left = min(start.column, end.column)
            right = max(start.column, end.column)
            for abs_line in range(start.line, end.line + 1):
                text = self._line_text(buffer, abs_line)
                segment = text[left:right]
                if len(segment) < right - left:
                    segment = segment.ljust(right - left)
                lines.append(segment)
            return "\n".join(lines)

        for abs_line in range(start.line, end.line + 1):
            text = self._line_text(buffer, abs_line)
            if start.line == end.line:
                lines.append(text[start.column:end.column])
            elif abs_line == start.line:
                lines.append(text[start.column:])
            elif abs_line == end.line:
                lines.append(text[:end.column])
            else:
                lines.append(text)
        return "\n".join(lines)

    def has_selection(self) -> bool:
        if self.selection is None:
            return False
        return self.selection.anchor != self.selection.active

    def _normalized(self, buffer: ScreenBuffer) -> tuple[SelectionPoint | None, SelectionPoint | None]:
        if self.selection is None:
            return None, None
        start = self.selection.anchor
        end = self.selection.active
        if self.selection.mode == SelectionMode.COLUMN:
            return self._clamp_point(buffer, start), self._clamp_point(buffer, end)
        if (end.line, end.column) < (start.line, start.column):
            start, end = end, start
        return self._clamp_point(buffer, start), self._clamp_point(buffer, end)

    def _clamp_point(self, buffer: ScreenBuffer, point: SelectionPoint) -> SelectionPoint:
        line = self._clamp_line(buffer, point.line)
        text = self._line_text(buffer, line)
        column = max(0, min(point.column, len(text)))
        return SelectionPoint(line, column)

    def _clamp_line(self, buffer: ScreenBuffer, line: int) -> int:
        if buffer.history_count() == 0:
            return buffer.history_offset
        minimum = buffer.history_offset
        maximum = buffer.history_offset + buffer.history_count() - 1
        return max(minimum, min(maximum, line))

    def _line_text(self, buffer: ScreenBuffer, line: int) -> str:
        index = line - buffer.history_offset
        if index < 0 or index >= buffer.history_count():
            return ""
        return buffer.history[index].text()

    def _current_point(self, buffer: ScreenBuffer) -> SelectionPoint:
        if buffer.history_count() == 0:
            return SelectionPoint(buffer.history_offset, 0)
        abs_line = buffer.history_offset + buffer.viewport_top
        return SelectionPoint(abs_line, 0)
