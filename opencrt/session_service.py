from __future__ import annotations
from .events import EventBus, FavoriteChanged, SessionCreated, SessionDeleted, SessionMoved, SessionUpdated
from .models import Session
from .storage import SessionStore

class SessionService:
    def __init__(self, store: SessionStore, event_bus: EventBus) -> None:
        self.store = store
        self.event_bus = event_bus

    def list_sessions(self) -> list[Session]:
        return self.store.sessions

    def get_session(self, session_id: str) -> Session | None:
        return next((session for session in self.store.sessions if session.id == session_id), None)

    def save_session(self, session: Session) -> Session:
        self.store.upsert(session)
        self.event_bus.publish(SessionUpdated(session.id))
        return session

    def create_session(self, session: Session) -> Session:
        self.store.upsert(session)
        self.event_bus.publish(SessionCreated(session.id))
        return session

    def delete_session(self, session_id: str) -> None:
        self.store.delete(session_id)
        self.event_bus.publish(SessionDeleted(session_id))

    def rename_session(self, session_id: str, name: str) -> Session | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.name = name
        self.store.upsert(session)
        self.event_bus.publish(SessionUpdated(session.id))
        return session

    def duplicate_session(self, session_id: str) -> Session | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        clone = Session.from_dict({**session.to_dict(), "id": ""})
        clone.name = f"{session.name} Copy"
        self.store.upsert(clone)
        self.event_bus.publish(SessionCreated(clone.id))
        return clone

    def move_session(self, session_id: str, group: str) -> Session | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.group = group or "Ungrouped"
        self.store.upsert(session)
        self.event_bus.publish(SessionMoved(session.id, session.group))
        return session

    def favorite_session(self, session_id: str, favorite: bool) -> Session | None:
        session = self.get_session(session_id)
        if session is None:
            return None
        session.favorite = favorite
        self.store.set_favorite(session_id, favorite)
        self.event_bus.publish(FavoriteChanged(session.id, favorite))
        return session
