
from __future__ import annotations
import json
from pathlib import Path
from .models import Session

class SessionStore:
    def __init__(self, path: Path, bundled_path: Path | None = None) -> None:
        self.path = path
        self.bundled_path = bundled_path
        self.sessions: list[Session] = []
        self.load()

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() and self.bundled_path and self.bundled_path.exists():
            self.path.write_bytes(self.bundled_path.read_bytes())
        if not self.path.exists():
            self.sessions = []
            return
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.sessions = [Session.from_dict(item) for item in raw]

    def save(self) -> None:
        self.path.write_text(
            json.dumps([s.to_dict() for s in self.sessions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def upsert(self, session: Session) -> None:
        for index, current in enumerate(self.sessions):
            if current.id == session.id:
                self.sessions[index] = session
                self.save()
                return
        self.sessions.append(session)
        self.save()

    def delete(self, session_id: str) -> None:
        self.sessions = [s for s in self.sessions if s.id != session_id]
        self.save()
