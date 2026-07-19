from __future__ import annotations
from dataclasses import dataclass
from .screen_buffer import ScreenBuffer, TextStyle

@dataclass(frozen=True, slots=True)
class PlainText:
    text: str

@dataclass(frozen=True, slots=True)
class EscapeSequence:
    sequence: str

@dataclass(frozen=True, slots=True)
class SGR:
    params: tuple[int, ...]

@dataclass(frozen=True, slots=True)
class CursorMove:
    direction: str
    amount: int

@dataclass(frozen=True, slots=True)
class CursorPosition:
    row: int
    column: int

@dataclass(frozen=True, slots=True)
class EraseLine:
    mode: int

@dataclass(frozen=True, slots=True)
class EraseDisplay:
    mode: int

@dataclass(frozen=True, slots=True)
class SaveCursor:
    pass

@dataclass(frozen=True, slots=True)
class RestoreCursor:
    pass

@dataclass(frozen=True, slots=True)
class CSI:
    final: str
    params: tuple[int, ...]
    raw: str

TerminalOperation = PlainText | EscapeSequence | SGR | CursorMove | CursorPosition | EraseLine | EraseDisplay | SaveCursor | RestoreCursor | CSI

class ANSIParser:
    def parse(self, data: bytes | str) -> list[TerminalOperation]:
        text = self._coerce_text(data)
        operations: list[TerminalOperation] = []
        buffer: list[str] = []
        index = 0
        length = len(text)

        while index < length:
            char = text[index]
            if char != "\x1b":
                buffer.append(char)
                index += 1
                continue

            if buffer:
                operations.append(PlainText("".join(buffer)))
                buffer.clear()

            if index + 1 >= length:
                operations.append(EscapeSequence("\x1b"))
                break

            next_char = text[index + 1]
            if next_char == "[":
                operation, new_index = self._parse_csi(text, index + 2)
                if operation is None:
                    operations.append(EscapeSequence(text[index:index + 2]))
                    index += 2
                    continue
                operations.append(operation)
                index = new_index
                continue
            if next_char == "7":
                operations.append(SaveCursor())
                index += 2
                continue
            if next_char == "8":
                operations.append(RestoreCursor())
                index += 2
                continue

            operations.append(EscapeSequence(text[index:index + 2]))
            index += 2

        if buffer:
            operations.append(PlainText("".join(buffer)))
        return operations

    def feed(self, data: bytes | str, buffer: ScreenBuffer) -> None:
        for operation in self.parse(data):
            self.apply_operation(buffer, operation)

    def apply_operation(self, buffer: ScreenBuffer, operation: TerminalOperation) -> None:
        if isinstance(operation, PlainText):
            buffer.write_text(operation.text)
        elif isinstance(operation, SGR):
            self.apply_sgr(buffer, operation.params)
        elif isinstance(operation, CursorMove):
            buffer.move_cursor(operation.direction, operation.amount)
        elif isinstance(operation, CursorPosition):
            buffer.position_cursor(operation.row, operation.column)
        elif isinstance(operation, EraseLine):
            buffer.clear_line(operation.mode)
        elif isinstance(operation, EraseDisplay):
            buffer.clear_screen(operation.mode)
        elif isinstance(operation, SaveCursor):
            buffer.save_cursor()
        elif isinstance(operation, RestoreCursor):
            buffer.restore_cursor()

    def apply_sgr(self, buffer: ScreenBuffer, params: tuple[int, ...]) -> None:
        style = buffer.clone_style()
        values = params or (0,)
        index = 0
        while index < len(values):
            code = values[index]
            if code == 0:
                style = TextStyle()
            elif code == 1:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=True,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif code == 4:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=style.bold,
                    underline=True,
                    reverse=style.reverse,
                )
            elif code == 7:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=True,
                )
            elif code == 22:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=False,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif code == 24:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=style.bold,
                    underline=False,
                    reverse=style.reverse,
                )
            elif code == 27:
                style = TextStyle(
                    foreground=style.foreground,
                    background=style.background,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=False,
                )
            elif code == 39:
                style = TextStyle(
                    foreground=None,
                    background=style.background,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif code == 49:
                style = TextStyle(
                    foreground=style.foreground,
                    background=None,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif 30 <= code <= 37:
                style = TextStyle(
                    foreground=self.color_from_index(code - 30),
                    background=style.background,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif 90 <= code <= 97:
                style = TextStyle(
                    foreground=self.color_from_index(code - 90, bright=True),
                    background=style.background,
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif 40 <= code <= 47:
                style = TextStyle(
                    foreground=style.foreground,
                    background=self.color_from_index(code - 40),
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif 100 <= code <= 107:
                style = TextStyle(
                    foreground=style.foreground,
                    background=self.color_from_index(code - 100, bright=True),
                    bold=style.bold,
                    underline=style.underline,
                    reverse=style.reverse,
                )
            elif code in (38, 48) and index + 2 < len(values):
                mode = values[index + 1]
                if mode == 5 and index + 2 < len(values):
                    color = self.color_from_index(values[index + 2])
                    if code == 38:
                        style = TextStyle(foreground=color, background=style.background, bold=style.bold, underline=style.underline, reverse=style.reverse)
                    else:
                        style = TextStyle(foreground=style.foreground, background=color, bold=style.bold, underline=style.underline, reverse=style.reverse)
                    index += 2
                elif mode == 2 and index + 4 < len(values):
                    color = self.rgb_color(values[index + 2], values[index + 3], values[index + 4])
                    if code == 38:
                        style = TextStyle(foreground=color, background=style.background, bold=style.bold, underline=style.underline, reverse=style.reverse)
                    else:
                        style = TextStyle(foreground=style.foreground, background=color, bold=style.bold, underline=style.underline, reverse=style.reverse)
                    index += 4
            index += 1
        buffer.set_style(style)

    def _parse_csi(self, text: str, start: int) -> tuple[TerminalOperation | None, int]:
        index = start
        length = len(text)
        if index >= length:
            return None, start

        intermediates = []
        while index < length:
            char = text[index]
            codepoint = ord(char)
            if 0x40 <= codepoint <= 0x7E:
                final = char
                raw = text[start - 2:index + 1]
                params = self._parse_params("".join(intermediates))
                return self._build_csi_operation(final, params, raw), index + 1
            intermediates.append(char)
            index += 1
        return None, start

    def _parse_params(self, payload: str) -> tuple[int, ...]:
        if not payload:
            return ()
        values = []
        for chunk in payload.split(";"):
            if not chunk:
                values.append(0)
                continue
            if chunk.startswith("?"):
                chunk = chunk[1:]
            try:
                values.append(int(chunk))
            except ValueError:
                values.append(0)
        return tuple(values)

    def _build_csi_operation(self, final: str, params: tuple[int, ...], raw: str) -> TerminalOperation:
        if final == "m":
            return SGR(params)
        if final in {"A", "B", "C", "D"}:
            amount = params[0] if params else 1
            return CursorMove(final, amount)
        if final in {"H", "f"}:
            row = params[0] if params else 1
            column = params[1] if len(params) > 1 else 1
            return CursorPosition(row, column)
        if final == "K":
            return EraseLine(params[0] if params else 0)
        if final == "J":
            return EraseDisplay(params[0] if params else 0)
        if final == "s":
            return SaveCursor()
        if final == "u":
            return RestoreCursor()
        return CSI(final=final, params=params, raw=raw)

    @staticmethod
    def _coerce_text(data: bytes | str) -> str:
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return data

    @staticmethod
    def color_from_index(index: int, bright: bool = False):
        from PySide6.QtGui import QColor
        palette = [
            QColor("#000000"),
            QColor("#cd3131"),
            QColor("#0dbc79"),
            QColor("#e5e510"),
            QColor("#2472c8"),
            QColor("#bc3fbc"),
            QColor("#11a8cd"),
            QColor("#e5e5e5"),
        ]
        bright_palette = [
            QColor("#666666"),
            QColor("#f14c4c"),
            QColor("#23d18b"),
            QColor("#f5f543"),
            QColor("#3b8eea"),
            QColor("#d670d6"),
            QColor("#29b8db"),
            QColor("#ffffff"),
        ]
        colors = bright_palette if bright else palette
        if 0 <= index < len(colors):
            return colors[index]
        return QColor("#d9e2ec")

    @staticmethod
    def rgb_color(r: int, g: int, b: int):
        from PySide6.QtGui import QColor
        return QColor(r, g, b)
