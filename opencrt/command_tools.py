from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (
    QDockWidget, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QPlainTextEdit, QVBoxLayout, QWidget, QLabel
)


@dataclass(slots=True)
class HistoryEntry:
    session_id: str
    protocol: str
    hostname: str
    command: str
    timestamp: str


@dataclass(slots=True)
class Snippet:
    id: str
    name: str
    body: str
    tags: list[str]
    description: str = ""
    favorite: bool = False


@dataclass(slots=True)
class BroadcastSession:
    session_id: str
    status: str = "pending"
    result: str = ""


class HistoryManager(QObject):
    changed = Signal()

    def __init__(self, history_path: Path, max_history: int = 100_000) -> None:
        super().__init__()
        self.history_path = history_path
        self.max_history = max_history
        self._entries: list[HistoryEntry] = []
        self._cache_key: tuple[str, str, str, str] | None = None
        self._cache_result: list[HistoryEntry] = []
        self.load()

    def load(self) -> None:
        if self.history_path.exists():
            try:
                raw = json.loads(self.history_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = []
            if isinstance(raw, list):
                self._entries = [HistoryEntry(**item) for item in raw if isinstance(item, dict)]

    def save(self) -> None:
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [asdict(entry) for entry in self._entries[-self.max_history :]]
        self.history_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.changed.emit()

    def record(self, session_id: str, protocol: str, hostname: str, command: str) -> None:
        command = command.strip()
        if not command:
            return
        from datetime import datetime

        self._entries.append(HistoryEntry(session_id=session_id, protocol=protocol, hostname=hostname, command=command, timestamp=datetime.utcnow().isoformat(timespec="seconds") + "Z"))
        if len(self._entries) > self.max_history:
            self._entries = self._entries[-self.max_history :]
        self._cache_key = None
        self.save()

    def search(self, query: str, *, session_id: str = "", protocol: str = "", hostname: str = "", date: str = "") -> list[HistoryEntry]:
        key = (query.strip().casefold(), session_id, protocol, hostname, date)
        if key == self._cache_key:
            return self._cache_result
        q = query.strip().casefold()
        result = [entry for entry in reversed(self._entries) if self._matches(entry, q, session_id, protocol, hostname, date)]
        self._cache_key = key
        self._cache_result = result
        return result

    @staticmethod
    def _matches(entry: HistoryEntry, q: str, session_id: str, protocol: str, hostname: str, date: str) -> bool:
        if session_id and entry.session_id != session_id:
            return False
        if protocol and entry.protocol.casefold() != protocol.casefold():
            return False
        if hostname and hostname.casefold() not in entry.hostname.casefold():
            return False
        if date and not entry.timestamp.startswith(date):
            return False
        if not q:
            return True
        haystack = f"{entry.command} {entry.protocol} {entry.hostname} {entry.timestamp}".casefold()
        return q in haystack


class HistorySearchEngine:
    def __init__(self, manager: HistoryManager) -> None:
        self.manager = manager
        self._results: list[HistoryEntry] = []

    def search(self, query: str, **filters: str) -> list[HistoryEntry]:
        self._results = self.manager.search(query, **filters)
        return self._results


class SnippetManager(QObject):
    changed = Signal()

    def __init__(self, snippet_path: Path) -> None:
        super().__init__()
        self.snippet_path = snippet_path
        self._snippets: list[Snippet] = []
        self.load()

    def load(self) -> None:
        if self.snippet_path.exists():
            try:
                raw = json.loads(self.snippet_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = []
            if isinstance(raw, list):
                self._snippets = [Snippet(**item) for item in raw if isinstance(item, dict)]

    def save(self) -> None:
        self.snippet_path.parent.mkdir(parents=True, exist_ok=True)
        self.snippet_path.write_text(json.dumps([asdict(snippet) for snippet in self._snippets], ensure_ascii=False, indent=2), encoding="utf-8")
        self.changed.emit()

    def all(self) -> list[Snippet]:
        return sorted(self._snippets, key=lambda snippet: (not snippet.favorite, snippet.name.casefold()))

    def add(self, snippet: Snippet) -> None:
        self._snippets.append(snippet)
        self.save()

    def expand(self, snippet: Snippet, values: dict[str, str]) -> str:
        text = snippet.body
        for key, value in values.items():
            text = text.replace(f"${{{key}}}", value)
        return text


class FavoriteCommandStore(QObject):
    changed = Signal()

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self._tags: dict[str, list[str]] = {}
        self._descriptions: dict[str, str] = {}
        self._favorites: set[str] = set()
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
            if isinstance(raw, dict):
                self._favorites = set(raw.get("favorites", []))
                self._tags = {k: list(v) for k, v in raw.get("tags", {}).items()}
                self._descriptions = {k: str(v) for k, v in raw.get("descriptions", {}).items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"favorites": sorted(self._favorites), "tags": self._tags, "descriptions": self._descriptions}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.changed.emit()

    def toggle_favorite(self, command: str) -> None:
        if command in self._favorites:
            self._favorites.remove(command)
        else:
            self._favorites.add(command)
        self.save()


class BroadcastManager(QObject):
    progress = Signal(str)
    completed = Signal()

    def broadcast(self, sessions: list[Any], command: str, sender: Callable[[Any, str], None]) -> list[BroadcastSession]:
        results: list[BroadcastSession] = []
        for session in sessions:
            result = BroadcastSession(session_id=getattr(session, "id", ""))
            try:
                sender(session, command)
                result.status = "sent"
                result.result = "ok"
            except Exception as exc:
                result.status = "failed"
                result.result = str(exc)
            results.append(result)
            self.progress.emit(f"{result.session_id}: {result.status}")
        self.completed.emit()
        return results


class QuickCommandPanel(QDockWidget):
    command_requested = Signal(str)
    _MAX_HISTORY_ITEMS = 200

    def __init__(self, history: HistoryManager, snippets: SnippetManager, parent=None) -> None:
        super().__init__("Quick Commands", parent)
        self.history = history
        self.snippets = snippets
        self.history_search = HistorySearchEngine(history)
        self.search = QLineEdit()
        self.list = QListWidget()
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self._emit_current)
        self.search.textChanged.connect(self.refresh)
        self.list.itemDoubleClicked.connect(lambda item: self.command_requested.emit(item.data(Qt.ItemDataRole.UserRole)))
        self.list.currentItemChanged.connect(self._update_preview_item)
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addWidget(QLabel("Preview"))
        layout.addWidget(self.preview, 1)
        layout.addWidget(self.send_button)
        self.setWidget(container)
        self.refresh()

    def refresh(self) -> None:
        query = self.search.text().strip().casefold()
        self.list.clear()
        seen_commands: set[str] = set()
        for entry in self.history_search.search(query)[: self._MAX_HISTORY_ITEMS]:
            command = entry.command
            if command in seen_commands:
                continue
            seen_commands.add(command)
            item = QListWidgetItem(f"{entry.command}   [{entry.protocol.upper()} {entry.hostname}]")
            item.setData(Qt.ItemDataRole.UserRole, command)
            item.setData(Qt.ItemDataRole.ToolTipRole, f"{entry.timestamp}\n{entry.protocol.upper()} {entry.hostname}")
            self.list.addItem(item)
        for snippet in self.snippets.all():
            haystack = " ".join([snippet.name, snippet.body, " ".join(snippet.tags), snippet.description]).casefold()
            if query and query not in haystack:
                continue
            if snippet.body in seen_commands:
                continue
            item = QListWidgetItem(snippet.name)
            item.setData(Qt.ItemDataRole.UserRole, snippet.body)
            item.setData(Qt.ItemDataRole.ToolTipRole, snippet.description or ", ".join(snippet.tags))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.preview.clear()

    def _update_preview_item(self, current: QListWidgetItem | None, previous: QListWidgetItem | None) -> None:
        if current is None:
            self.preview.clear()
            return
        self.preview.setPlainText(current.data(Qt.ItemDataRole.UserRole) or "")

    def _emit_current(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.command_requested.emit(item.data(Qt.ItemDataRole.UserRole))
