from __future__ import annotations

from dataclasses import dataclass

from .events import EventBus, SessionEvent
from .models import Session
from .session_productivity import SessionProductivityPack


@dataclass(slots=True)
class SearchGroup:
    name: str
    sessions: list[Session]
    expanded: bool


@dataclass(slots=True)
class SearchResults:
    groups: list[SearchGroup]
    first_session_id: str | None
    visible_count: int


class SearchService:
    def __init__(self, event_bus: EventBus | None = None, productivity: SessionProductivityPack | None = None) -> None:
        self._revision = 0
        self._cache_key: tuple[object, ...] | None = None
        self._cache_result: SearchResults | None = None
        self.productivity = productivity
        if event_bus is not None:
            event_bus.subscribe_session_events(self._on_session_event)

    def _on_session_event(self, _: SessionEvent) -> None:
        self._revision += 1
        self._cache_key = None
        self._cache_result = None

    def search(self, sessions: list[Session], query_text: str, filter_mode: str = "all") -> SearchResults:
        productivity_revision = getattr(self.productivity.store, "config_revision", 0) if self.productivity else 0
        cache_key = (self._revision, productivity_revision, filter_mode, query_text, len(sessions))
        if cache_key == self._cache_key and self._cache_result is not None:
            return self._cache_result
        productivity = self.productivity
        filtered_sessions = sessions
        if productivity is not None:
            productivity.set_filter_mode(filter_mode)
            filtered_sessions = productivity.filtered_sessions(sessions)
        query = query_text.strip().casefold()
        favorite_sessions: list[Session] = []
        recent_sessions: list[Session] = []
        pinned_sessions: list[Session] = []
        groups: dict[str, list[Session]] = {}
        recent_ids = set(productivity.recent_ids()) if productivity is not None else set()
        pinned_ids = productivity.pinned_ids() if productivity is not None else set()
        for session in filtered_sessions:
            if productivity is not None and not productivity.matches(session, query):
                continue
            if session.favorite:
                favorite_sessions.append(session)
            elif session.id in recent_ids:
                recent_sessions.append(session)
            elif session.id in pinned_ids:
                pinned_sessions.append(session)
            else:
                groups.setdefault(session.group or "Ungrouped", []).append(session)

        ordered_groups: list[SearchGroup] = []
        if favorite_sessions and filter_mode in {"all", "favorites"}:
            ordered_groups.append(SearchGroup("Favorites", self._sort_sessions(favorite_sessions, pinned_ids, recent_ids), True))
        if recent_sessions and filter_mode in {"all", "recent"}:
            ordered_groups.append(SearchGroup("Recent Sessions", self._sort_sessions(recent_sessions, pinned_ids, recent_ids), True))
        if pinned_sessions and filter_mode in {"all", "pinned"}:
            ordered_groups.append(SearchGroup("Pinned Sessions", self._sort_sessions(pinned_sessions, pinned_ids, recent_ids), True))
        for group_name in sorted(groups, key=str.casefold):
            ordered_groups.append(SearchGroup(group_name, self._sort_sessions(groups[group_name], pinned_ids, recent_ids), bool(query)))

        visible_count = sum(len(group.sessions) for group in ordered_groups)
        first_session_id = None
        for group in ordered_groups:
            if group.sessions:
                first_session_id = group.sessions[0].id
                break
        result = SearchResults(ordered_groups, first_session_id, visible_count)
        self._cache_key = cache_key
        self._cache_result = result
        return result

    def matches(self, session: Session, query: str) -> bool:
        if self.productivity is not None:
            return self.productivity.matches(session, query)
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
            ]
        ).casefold()
        return query in haystack

    @staticmethod
    def _sort_sessions(sessions: list[Session], pinned_ids: set[str], recent_ids: set[str]) -> list[Session]:
        return sorted(
            sessions,
            key=lambda session: (session.id not in pinned_ids, session.id not in recent_ids, session.name.casefold()),
        )
