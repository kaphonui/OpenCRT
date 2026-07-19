from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QLineEdit

from .screen_buffer import ScreenBuffer


@dataclass(frozen=True, slots=True)
class SearchOptions:
    query: str = ""
    case_sensitive: bool = False
    whole_word: bool = False
    regex: bool = False


@dataclass(frozen=True, slots=True)
class SearchMatch:
    line: int
    start: int
    end: int


class TerminalSearchEngine:
    def __init__(self) -> None:
        self._options = SearchOptions()
        self._cache_revision = -1
        self._cache_key: tuple[str, bool, bool, bool] | None = None
        self._base_line = 0
        self._cached_lines: list[str] = []
        self._cached_lower_lines: list[str] = []
        self._matches: list[SearchMatch] = []
        self._matches_by_line: dict[int, list[SearchMatch]] = {}
        self._current_index = -1

    def search(self, buffer: ScreenBuffer, options: SearchOptions) -> list[SearchMatch]:
        self._options = options
        key = self._cache_key_for(options)
        if self._cache_revision == buffer.revision and self._cache_key == key:
            return self._matches

        self._cache_revision = buffer.revision
        self._cache_key = key
        self._snapshot(buffer)
        self._matches = self._collect_matches(options)
        self._matches_by_line = self._index_by_line(self._matches)
        if self._matches:
            self._current_index = min(max(self._current_index, 0), len(self._matches) - 1)
        else:
            self._current_index = -1
        return self._matches

    def ensure(self, buffer: ScreenBuffer) -> list[SearchMatch]:
        return self.search(buffer, self._options)

    @property
    def options(self) -> SearchOptions:
        return self._options

    def set_current_first(self) -> None:
        if self._matches:
            self._current_index = 0
        else:
            self._current_index = -1

    def next_match(self) -> SearchMatch | None:
        if not self._matches:
            return None
        self._current_index = (self._current_index + 1) % len(self._matches)
        return self.current_match()

    def previous_match(self) -> SearchMatch | None:
        if not self._matches:
            return None
        self._current_index = (self._current_index - 1) % len(self._matches)
        return self.current_match()

    def current_match(self) -> SearchMatch | None:
        if not self._matches or self._current_index < 0:
            return None
        return self._matches[self._current_index]

    def match_count(self) -> int:
        return len(self._matches)

    def counter_text(self) -> str:
        if not self._matches:
            return "0 / 0"
        return f"{self._current_index + 1} / {len(self._matches)}"

    def matches_for_line(self, abs_line: int) -> list[SearchMatch]:
        return self._matches_by_line.get(abs_line, [])

    def is_current_match(self, match: SearchMatch) -> bool:
        current = self.current_match()
        return current == match

    def _cache_key_for(self, options: SearchOptions) -> tuple[str, bool, bool, bool]:
        return (
            options.query,
            options.case_sensitive,
            options.whole_word,
            options.regex,
        )

    def _snapshot(self, buffer: ScreenBuffer) -> None:
        self._base_line = buffer.history_offset
        self._cached_lines = [line.text() for line in buffer.history]
        self._cached_lower_lines = [line.casefold() for line in self._cached_lines]

    def _collect_matches(self, options: SearchOptions) -> list[SearchMatch]:
        query = options.query
        if not query:
            return []
        if options.regex:
            return self._collect_regex_matches(query, options)
        if options.whole_word:
            return self._collect_regex_matches(rf"\b{re.escape(query)}\b", options, treat_as_regex=True)
        return self._collect_plain_matches(query, options)

    def _collect_plain_matches(self, query: str, options: SearchOptions) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        haystack = self._cached_lines if options.case_sensitive else self._cached_lower_lines
        needle = query if options.case_sensitive else query.casefold()
        for line_index, text in enumerate(haystack):
            start = 0
            while True:
                found = text.find(needle, start)
                if found < 0:
                    break
                matches.append(SearchMatch(line=self._base_line + line_index, start=found, end=found + len(needle)))
                start = found + max(1, len(needle))
        return matches

    def _collect_regex_matches(self, pattern: str, options: SearchOptions) -> list[SearchMatch]:
        flags = 0 if options.case_sensitive else re.IGNORECASE
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            return []
        matches: list[SearchMatch] = []
        for line_index, text in enumerate(self._cached_lines):
            for found in regex.finditer(text):
                matches.append(SearchMatch(line=self._base_line + line_index, start=found.start(), end=found.end()))
        return matches

    def _index_by_line(self, matches: list[SearchMatch]) -> dict[int, list[SearchMatch]]:
        indexed: dict[int, list[SearchMatch]] = {}
        for match in matches:
            indexed.setdefault(match.line, []).append(match)
        return indexed


class SearchLineEdit(QLineEdit):
    next_requested = Signal()
    previous_requested = Signal()
    closed_requested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.previous_requested.emit()
            else:
                self.next_requested.emit()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.closed_requested.emit()
            return
        super().keyPressEvent(event)
