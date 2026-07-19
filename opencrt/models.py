
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any
import uuid

@dataclass
class Session:
    name: str
    protocol: str = "ssh"
    host: str = ""
    port: int = 22
    username: str = ""
    password: str = ""
    group: str = "Ungrouped"
    alias: str = ""
    serial_port: str = ""
    baudrate: int = 9600
    databits: int = 8
    parity: str = "N"
    stopbits: float = 1
    keyboard_profile: str = "linux"
    credential_id: str = ""
    reconnect_policy: str = "exponential"
    reconnect_max_retries: int = 3
    reconnect_delay_seconds: int = 2
    keepalive_seconds: int = 60
    favorite: bool = False
    source: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        self.keyboard_profile = (self.keyboard_profile or "linux").strip().casefold() or "linux"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{k: v for k, v in data.items() if k in allowed})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
