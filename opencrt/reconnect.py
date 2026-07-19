from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, Signal, QTimer


class ConnectionEventType(str, Enum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CLOSED = "closed"
    ERROR = "error"
    TIMEOUT = "timeout"
    NETWORK_LOST = "network_lost"
    SSH_DISCONNECT = "ssh_disconnect"
    TELNET_DISCONNECT = "telnet_disconnect"
    MANUAL_DISCONNECT = "manual_disconnect"
    HOST_KEY_UNKNOWN = "host_key_unknown"
    HOST_KEY_CHANGED = "host_key_changed"


@dataclass(slots=True)
class ConnectionEvent:
    session_id: str
    type: ConnectionEventType
    protocol: str
    reason: str = ""
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class ReconnectPolicy:
    enabled: bool = True
    max_retries: int = 3
    base_delay_seconds: float = 2.0
    timeout_seconds: float = 12.0
    keepalive_seconds: int = 60


class ConnectionEventBus(QObject):
    event_emitted = Signal(object)

    def emit_event(self, event: ConnectionEvent) -> None:
        self.event_emitted.emit(event)


class KnownHostsManager:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._known: dict[str, str] = {}
        self._load()

    def is_trusted(self, host: str, fingerprint: str) -> bool:
        return self._known.get(host) == fingerprint

    def has_host(self, host: str) -> bool:
        return host in self._known

    def fingerprint_for(self, host: str) -> str | None:
        return self._known.get(host)

    def trust_once(self, host: str, fingerprint: str) -> None:
        self._known[host] = fingerprint
        self._save()

    def trust_always(self, host: str, fingerprint: str) -> None:
        self._known[host] = fingerprint
        self._save()

    def reject(self, host: str) -> None:
        self._known.pop(host, None)
        self._save()

    def _load(self) -> None:
        if self.path.exists():
            import json
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = {}
            if isinstance(raw, dict):
                self._known = {str(k): str(v) for k, v in raw.items()}

    def _save(self) -> None:
        import json
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._known, ensure_ascii=False, indent=2), encoding="utf-8")


class ReconnectManager(QObject):
    reconnect_requested = Signal(str)
    status_requested = Signal(str)

    def __init__(self, policy: ReconnectPolicy | None = None, event_bus: ConnectionEventBus | None = None) -> None:
        super().__init__()
        self.policy = policy or ReconnectPolicy()
        self._event_bus = event_bus or ConnectionEventBus()
        self._event_bus.event_emitted.connect(self._on_event)
        self._manual_disconnects: set[str] = set()
        self._attempts: dict[str, int] = {}

    @property
    def event_bus(self) -> ConnectionEventBus:
        return self._event_bus

    def mark_manual_disconnect(self, session_id: str) -> None:
        self._manual_disconnects.add(session_id)

    def clear_manual_disconnect(self, session_id: str) -> None:
        self._manual_disconnects.discard(session_id)

    def _on_event(self, event: ConnectionEvent) -> None:
        if event.type == ConnectionEventType.CONNECTED:
            self._attempts.pop(event.session_id, None)
            self.status_requested.emit(f"Connected: {event.protocol.upper()}")
            return
        if event.type == ConnectionEventType.MANUAL_DISCONNECT:
            self.mark_manual_disconnect(event.session_id)
            return
        if event.type not in {ConnectionEventType.CLOSED, ConnectionEventType.ERROR, ConnectionEventType.TIMEOUT, ConnectionEventType.NETWORK_LOST, ConnectionEventType.SSH_DISCONNECT, ConnectionEventType.TELNET_DISCONNECT}:
            return
        if event.session_id in self._manual_disconnects or not self.policy.enabled:
            return
        attempts = self._attempts.get(event.session_id, 0)
        if attempts >= self.policy.max_retries:
            self.status_requested.emit("Reconnect stopped")
            return
        delay = int(self.policy.base_delay_seconds * (2 ** attempts) * 1000)
        self._attempts[event.session_id] = attempts + 1
        self.status_requested.emit(f"Reconnecting in {delay // 1000}s...")
        QTimer.singleShot(delay, lambda sid=event.session_id: self.reconnect_requested.emit(sid))
