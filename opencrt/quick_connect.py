from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from .actions import Action, ActionContext
from .models import Session
from .session_service import SessionService


@dataclass(frozen=True, slots=True)
class QuickConnectMatch:
    session: Session
    reason: str


class SessionResolver:
    def __init__(self, session_service: SessionService) -> None:
        self.session_service = session_service

    def resolve(self, context: ActionContext, protocol: str) -> Session:
        value = context.value.strip()
        match = self.find_match(value)
        if match is not None:
            return match.session
        return self.create_temporary_session(value, protocol)

    def find_match(self, value: str) -> QuickConnectMatch | None:
        sessions = self.session_service.list_sessions()
        normalized = value.casefold()
        for reason, predicate in (
            ("host", lambda session: session.host.casefold() == normalized),
            ("ip", lambda session: session.host.casefold() == normalized),
            ("alias", lambda session: session.alias.casefold() == normalized),
            ("display_name", lambda session: session.name.casefold() == normalized),
        ):
            for session in sessions:
                if predicate(session):
                    return QuickConnectMatch(session=session, reason=reason)
        return None

    @staticmethod
    def create_temporary_session(value: str, protocol: str) -> Session:
        if protocol == "telnet":
            return Session(name=value or "Temporary Session", protocol=protocol, host=value, port=23, source="quick-connect")
        return Session(name=value or "Temporary Session", protocol=protocol, host=value, source="quick-connect")


class QuickConnectEngine(QObject):
    open_session = Signal(object)

    def __init__(self, session_service: SessionService) -> None:
        super().__init__()
        self.session_service = session_service
        self.resolver = SessionResolver(session_service)

    def handle_action(self, context: ActionContext, action: Action) -> None:
        protocol = self._protocol_for_action(context, action)
        if protocol is None:
            return
        session = self.resolver.resolve(context, protocol)
        self.open_session.emit(session)

    @staticmethod
    def _protocol_for_action(context: ActionContext, action: Action) -> str | None:
        if context.type not in {"ip", "hostname"}:
            return None
        if action.id in {"ip.ssh", "hostname.ssh", "ssh"} or action.label.casefold() == "ssh":
            return "ssh"
        if action.id in {"ip.telnet", "hostname.telnet", "telnet"} or action.label.casefold() == "telnet":
            return "telnet"
        return None
