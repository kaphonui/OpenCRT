from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ipaddress
import re

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from .screen_buffer import ScreenBuffer


class HyperlinkType(str, Enum):
    URL = "url"
    EMAIL = "email"
    FILE = "file"
    IP = "ip"
    INTERFACE = "interface"
    HOSTNAME = "hostname"


@dataclass(frozen=True, slots=True)
class Hyperlink:
    line: int
    start: int
    end: int
    kind: HyperlinkType


class HyperlinkEngine(QObject):
    activated = Signal(str, str)
    ip_activated = Signal(str)
    interface_activated = Signal(str)
    hostname_activated = Signal(str)

    _TRAILING_PUNCTUATION = ".,;:)]}>"

    def __init__(self) -> None:
        super().__init__()
        self._cache_key: tuple[int, int, int, int, int] | None = None
        self._links: list[Hyperlink] = []
        self._links_by_line: dict[int, list[Hyperlink]] = {}
        self._hovered: Hyperlink | None = None
        self._visited: set[tuple[HyperlinkType, str]] = set()

    def ensure(self, buffer: ScreenBuffer) -> list[Hyperlink]:
        key = (
            buffer.revision,
            buffer.history_offset,
            buffer.viewport_top,
            buffer.rows,
            buffer.columns,
        )
        if self._cache_key == key:
            return self._links
        self._cache_key = key
        self._links = self._parse_visible(buffer)
        self._links_by_line = self._index_by_line(self._links)
        if self._hovered not in self._links:
            self._hovered = None
        return self._links

    def links_for_line(self, buffer: ScreenBuffer, abs_line: int) -> list[Hyperlink]:
        self.ensure(buffer)
        return self._links_by_line.get(abs_line, [])

    def link_at(self, buffer: ScreenBuffer, abs_line: int, column: int) -> Hyperlink | None:
        for link in self.links_for_line(buffer, abs_line):
            if link.start <= column < link.end:
                return link
        return None

    def update_hover(self, buffer: ScreenBuffer, abs_line: int, column: int) -> bool:
        link = self.link_at(buffer, abs_line, column)
        if link == self._hovered:
            return False
        self._hovered = link
        return True

    def clear_hover(self) -> bool:
        if self._hovered is None:
            return False
        self._hovered = None
        return True

    def is_hovered(self, link: Hyperlink) -> bool:
        return self._hovered == link

    def is_visited(self, buffer: ScreenBuffer, link: Hyperlink) -> bool:
        return (link.kind, self.target_for(buffer, link)) in self._visited

    def activate(self, buffer: ScreenBuffer, link: Hyperlink) -> None:
        target = self.target_for(buffer, link)
        if not target:
            return
        self._visited.add((link.kind, target))
        if link.kind == HyperlinkType.URL:
            QDesktopServices.openUrl(QUrl(target))
        elif link.kind == HyperlinkType.EMAIL:
            QDesktopServices.openUrl(QUrl(f"mailto:{target}"))
        elif link.kind == HyperlinkType.FILE:
            QDesktopServices.openUrl(QUrl.fromLocalFile(target))
        elif link.kind == HyperlinkType.IP:
            self.ip_activated.emit(target)
        elif link.kind == HyperlinkType.INTERFACE:
            self.interface_activated.emit(target)
        elif link.kind == HyperlinkType.HOSTNAME:
            self.hostname_activated.emit(target)
        self.activated.emit(link.kind.value, target)

    def target_for(self, buffer: ScreenBuffer, link: Hyperlink) -> str:
        index = link.line - buffer.history_offset
        if index < 0 or index >= buffer.history_count():
            return ""
        return buffer.history[index].text()[link.start:link.end]

    def _parse_visible(self, buffer: ScreenBuffer) -> list[Hyperlink]:
        links: list[Hyperlink] = []
        base_line = buffer.history_offset + buffer.viewport_top
        for visible_row, line in enumerate(buffer.visible_lines()):
            abs_line = base_line + visible_row
            links.extend(self._parse_line(abs_line, line.text()))
        return links

    def _parse_line(self, abs_line: int, text: str) -> list[Hyperlink]:
        links: list[Hyperlink] = []
        occupied: list[tuple[int, int]] = []

        def add(kind: HyperlinkType, pattern: str, flags: int = 0, validator=None) -> None:
            for match in re.finditer(pattern, text, flags):
                start, end = self._trim_span(text, match.start(), match.end())
                if start >= end:
                    continue
                target = text[start:end]
                if validator is not None and not validator(target):
                    continue
                if self._overlaps(start, end, occupied):
                    continue
                links.append(Hyperlink(line=abs_line, start=start, end=end, kind=kind))
                occupied.append((start, end))

        add(HyperlinkType.URL, r"\b(?:https?|ftp)://[^\s<>\"']+")
        add(HyperlinkType.EMAIL, r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
        add(HyperlinkType.FILE, r"\b[A-Za-z]:\\[^\s<>\"|?*]+")
        add(HyperlinkType.FILE, r"(?<!\S)/(?:[A-Za-z0-9._-]+/)*[A-Za-z0-9._-]+")
        add(HyperlinkType.IP, r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])", validator=self._valid_ipv4)
        add(HyperlinkType.IP, r"(?<![\w:])(?=[0-9A-Fa-f:]*:)[0-9A-Fa-f:]{3,}(?![\w:])", validator=self._valid_ipv6)
        add(HyperlinkType.INTERFACE, r"\b(?:Gi|Te|Eth)\d+(?:/\d+){1,3}\b|\b(?:xe|ge)-\d+/\d+/\d+\b", re.IGNORECASE)
        add(HyperlinkType.HOSTNAME, r"\b(?=[A-Za-z0-9-]*[0-9-])[A-Za-z][A-Za-z0-9-]{1,62}\b")
        links.sort(key=lambda link: (link.line, link.start, link.end))
        return links

    def _trim_span(self, text: str, start: int, end: int) -> tuple[int, int]:
        while end > start and text[end - 1] in self._TRAILING_PUNCTUATION:
            end -= 1
        return start, end

    @staticmethod
    def _overlaps(start: int, end: int, occupied: list[tuple[int, int]]) -> bool:
        return any(start < used_end and end > used_start for used_start, used_end in occupied)

    @staticmethod
    def _valid_ipv4(value: str) -> bool:
        try:
            return ipaddress.ip_address(value).version == 4
        except ValueError:
            return False

    @staticmethod
    def _valid_ipv6(value: str) -> bool:
        try:
            return ipaddress.ip_address(value).version == 6
        except ValueError:
            return False

    @staticmethod
    def _index_by_line(links: list[Hyperlink]) -> dict[int, list[Hyperlink]]:
        indexed: dict[int, list[Hyperlink]] = {}
        for link in links:
            indexed.setdefault(link.line, []).append(link)
        return indexed
