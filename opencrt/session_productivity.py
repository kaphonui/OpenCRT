from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu

from .models import Session
from .session_service import SessionService
from .storage import SessionStore


@dataclass(slots=True)
class RecentSession:
    session_id: str
    timestamp: str
    protocol: str
    host: str


class FavoritesManager:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def toggle(self, session_id: str) -> None:
        self.store.set_favorite(session_id, session_id not in self.store.favorite_session_ids())


class RecentManager:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def record(self, session_id: str, protocol: str, host: str) -> None:
        self.store.record_recent(session_id, protocol, host)

    def recent_ids(self) -> list[str]:
        return [entry["session_id"] for entry in self.store.recent_entries()]


class SessionStatistics:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def record_connection(self, session_id: str, protocol: str, host: str, duration_seconds: float) -> None:
        self.store.record_statistics(session_id, protocol, host, duration_seconds)

    def statistics_for(self, session_id: str) -> dict[str, Any]:
        return self.store.statistics_for(session_id)


class TagManager:
    def __init__(self, store: SessionStore) -> None:
        self.store = store

    def tags_for(self, session_id: str) -> list[str]:
        return self.store.tags_for(session_id)

    def set_tags(self, session_id: str, tags: list[str]) -> None:
        self.store.set_tags(session_id, tags)


class SessionFilter:
    def __init__(self, store: SessionStore) -> None:
        self.store = store
        self.mode = "all"

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def apply(self, sessions: list[Session]) -> list[Session]:
        if self.mode == "all":
            return sessions
        if self.mode == "favorites":
            favorites = self.store.favorite_session_ids()
            return [session for session in sessions if session.id in favorites]
        if self.mode == "recent":
            recent = {entry["session_id"] for entry in self.store.recent_entries()}
            return [session for session in sessions if session.id in recent]
        if self.mode == "pinned":
            pinned = self.store.pinned_session_ids()
            return [session for session in sessions if session.id in pinned]
        return [session for session in sessions if session.protocol == self.mode]


class SessionMenuBuilder:
    def build_menu(
        self,
        parent,
        session: Session,
        handlers: dict[str, Callable[[], None]],
    ) -> QMenu:
        menu = QMenu(parent)
        for label, key in (
            ("Open in New Tab", "open"),
            ("Duplicate", "duplicate"),
            ("Rename", "rename"),
            ("Favorite", "favorite"),
            ("Pin", "pin"),
            ("Copy Host", "copy_host"),
            ("Copy IP", "copy_ip"),
            ("Copy Username", "copy_username"),
            ("Properties", "properties"),
            ("Delete", "delete"),
        ):
            action = menu.addAction(label)
            if key in handlers:
                action.triggered.connect(lambda checked=False, callback=handlers[key]: callback())
        return menu


class SessionProductivityPack:
    def __init__(self, session_service: SessionService) -> None:
        self.session_service = session_service
        self.store = session_service.store
        self.favorites = FavoritesManager(self.store)
        self.recent = RecentManager(self.store)
        self.statistics = SessionStatistics(self.store)
        self.tags = TagManager(self.store)
        self.filter = SessionFilter(self.store)
        self.menu_builder = SessionMenuBuilder()

    def set_filter_mode(self, mode: str) -> None:
        self.filter.set_mode(mode)

    def filtered_sessions(self, sessions: list[Session]) -> list[Session]:
        return self.filter.apply(sessions)

    def toggle_favorite(self, session_id: str) -> None:
        self.favorites.toggle(session_id)

    def set_pinned(self, session_id: str, pinned: bool) -> None:
        self.store.set_pinned(session_id, pinned)

    def pinned_ids(self) -> set[str]:
        return self.store.pinned_session_ids()

    def recent_ids(self) -> list[str]:
        return self.recent.recent_ids()

    def tags_for(self, session_id: str) -> list[str]:
        return self.tags.tags_for(session_id)

    def statistics_for(self, session_id: str) -> dict[str, Any]:
        return self.statistics.statistics_for(session_id)

    def record_connection(self, session: Session, duration_seconds: float) -> None:
        self.statistics.record_connection(session.id, session.protocol, session.host or session.serial_port, duration_seconds)

    def record_recent(self, session: Session) -> None:
        self.recent.record(session.id, session.protocol, session.host or session.serial_port)

    def matches(self, session: Session, query: str) -> bool:
        query = query.strip().casefold()
        if not query:
            return True
        haystack = " ".join(
            [
                session.name,
                session.host,
                session.serial_port,
                session.username,
                session.group,
                session.protocol,
                session.alias,
                getattr(session, "description", ""),
                " ".join(self.tags_for(session.id)),
                "favorite" if session.id in self.store.favorite_session_ids() else "",
                "pinned" if session.id in self.store.pinned_session_ids() else "",
                "recent" if self.store.is_recent(session.id) else "",
            ]
        ).casefold()
        return query in haystack
