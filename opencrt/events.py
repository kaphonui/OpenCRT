from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable

@dataclass(frozen=True, slots=True)
class SessionCreated:
    session_id: str

@dataclass(frozen=True, slots=True)
class SessionDeleted:
    session_id: str

@dataclass(frozen=True, slots=True)
class SessionUpdated:
    session_id: str

@dataclass(frozen=True, slots=True)
class SessionMoved:
    session_id: str
    group: str

@dataclass(frozen=True, slots=True)
class FavoriteChanged:
    session_id: str
    favorite: bool

SessionEvent = SessionCreated | SessionDeleted | SessionUpdated | SessionMoved | FavoriteChanged

SESSION_EVENTS = (SessionCreated, SessionDeleted, SessionUpdated, SessionMoved, FavoriteChanged)

class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[type[object], list[Callable[[object], None]]] = {}

    def subscribe(self, event_type: type[object], callback: Callable[[object], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: type[object], callback: Callable[[object], None]) -> None:
        subscribers = self._subscribers.get(event_type)
        if not subscribers:
            return
        self._subscribers[event_type] = [subscriber for subscriber in subscribers if subscriber != callback]

    def subscribe_session_events(self, callback: Callable[[SessionEvent], None]) -> None:
        for event_type in SESSION_EVENTS:
            self.subscribe(event_type, callback)  # type: ignore[arg-type]

    def unsubscribe_session_events(self, callback: Callable[[SessionEvent], None]) -> None:
        for event_type in SESSION_EVENTS:
            self.unsubscribe(event_type, callback)  # type: ignore[arg-type]

    def publish(self, event: SessionEvent) -> None:
        for callback in self._subscribers.get(type(event), []):
            callback(event)
