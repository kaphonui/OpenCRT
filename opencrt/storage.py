from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Session


class SessionStore:
    def __init__(self, path: Path, config_path: Path | None = None, bundled_path: Path | None = None) -> None:
        self.path = path
        self.config_path = config_path or path.with_name("config.json")
        self.bundled_path = bundled_path
        self.sessions: list[Session] = []
        self.config_revision = 0
        self._config: dict[str, Any] = self._default_config()
        self.load()

    def load(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists() and self.bundled_path and self.bundled_path.exists():
            self.path.write_bytes(self.bundled_path.read_bytes())
        if not self.path.exists():
            self.sessions = []
        else:
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw = []
            self.sessions = [Session.from_dict(item) for item in raw if isinstance(item, dict)]
        self._load_config()
        self._sync_session_favorites()
        self._apply_metadata_to_sessions()

    def save(self) -> None:
        self._sync_session_favorites()
        self.path.write_text(
            json.dumps([s.to_dict() for s in self.sessions], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._save_config()

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
        self._remove_metadata(session_id)
        self.save()

    def set_favorite(self, session_id: str, favorite: bool) -> None:
        self._config.setdefault("favorites", [])
        favorites = set(str(item) for item in self._config["favorites"])
        if favorite:
            favorites.add(session_id)
        else:
            favorites.discard(session_id)
        self._config["favorites"] = sorted(favorites)
        for session in self.sessions:
            if session.id == session_id:
                session.favorite = favorite
        self._touch_config()
        self._save_config()

    def set_pinned(self, session_id: str, pinned: bool) -> None:
        self._config.setdefault("pinned", [])
        pinned_ids = set(str(item) for item in self._config["pinned"])
        if pinned:
            pinned_ids.add(session_id)
        else:
            pinned_ids.discard(session_id)
        self._config["pinned"] = sorted(pinned_ids)
        self._touch_config()
        self._save_config()

    def set_tags(self, session_id: str, tags: list[str]) -> None:
        clean = sorted({tag.strip() for tag in tags if tag.strip()}, key=str.casefold)
        tags_map = self._config.setdefault("tags", {})
        if clean:
            tags_map[session_id] = clean
        else:
            tags_map.pop(session_id, None)
        self._touch_config()
        self._save_config()

    def record_recent(self, session_id: str, protocol: str, host: str) -> None:
        entries = [item for item in self._config.setdefault("recent", []) if item.get("session_id") != session_id]
        entries.insert(0, {"session_id": session_id, "timestamp": self._now(), "protocol": protocol, "host": host})
        self._config["recent"] = entries[:20]
        self._touch_config()
        self._save_config()

    def record_statistics(self, session_id: str, protocol: str, host: str, duration_seconds: float) -> None:
        stats = self._config.setdefault("statistics", {})
        current = stats.setdefault(session_id, {"connect_count": 0, "last_connected": None, "total_connection_time": 0.0, "average_connection_time": 0.0, "last_protocol": "", "last_host": ""})
        current["connect_count"] = int(current.get("connect_count", 0)) + 1
        current["last_connected"] = self._now()
        current["total_connection_time"] = float(current.get("total_connection_time", 0.0)) + max(0.0, float(duration_seconds))
        current["average_connection_time"] = current["total_connection_time"] / max(1, current["connect_count"] )
        current["last_protocol"] = protocol
        current["last_host"] = host
        self._touch_config()
        self._save_config()

    def favorite_session_ids(self) -> set[str]:
        return set(self._config.get("favorites", []))

    def pinned_session_ids(self) -> set[str]:
        return set(self._config.get("pinned", []))

    def tags_for(self, session_id: str) -> list[str]:
        tags = self._config.get("tags", {}).get(session_id, [])
        return list(tags)

    def is_recent(self, session_id: str) -> bool:
        return any(item.get("session_id") == session_id for item in self._config.get("recent", []))

    def recent_entries(self) -> list[dict[str, Any]]:
        return list(self._config.get("recent", []))

    def statistics_for(self, session_id: str) -> dict[str, Any]:
        return dict(self._config.get("statistics", {}).get(session_id, {}))

    def metadata_for(self, session_id: str) -> dict[str, Any]:
        return {
            "favorite": session_id in self.favorite_session_ids(),
            "pinned": session_id in self.pinned_session_ids(),
            "tags": self.tags_for(session_id),
            "recent": self.is_recent(session_id),
            "statistics": self.statistics_for(session_id),
        }

    def _load_config(self) -> None:
        self._config = self._default_config()
        if not self.config_path.exists():
            return
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if isinstance(raw, list):
            self._config["favorites"] = [str(item) for item in raw if item]
            return
        if isinstance(raw, dict):
            for key in self._config:
                if key in raw:
                    self._config[key] = raw[key]
            if isinstance(raw.get("favorites"), list):
                self._config["favorites"] = [str(item) for item in raw["favorites"] if item]

    def _save_config(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self._config, ensure_ascii=False, indent=2), encoding="utf-8")

    def _sync_session_favorites(self) -> None:
        favorites = set(str(item) for item in self._config.get("favorites", []))
        for session in self.sessions:
            session.favorite = session.id in favorites or session.favorite
            if session.favorite:
                favorites.add(session.id)
        self._config["favorites"] = sorted(favorites)

    def _apply_metadata_to_sessions(self) -> None:
        for session in self.sessions:
            session.alias = self._config.get("aliases", {}).get(session.id, session.alias)
            setattr(session, "description", self._config.get("descriptions", {}).get(session.id, getattr(session, "description", "")))
            setattr(session, "tags", tuple(self.tags_for(session.id)))
            setattr(session, "pinned", session.id in self.pinned_session_ids())

    def _remove_metadata(self, session_id: str) -> None:
        for key in ("favorites", "pinned"):
            values = [item for item in self._config.get(key, []) if item != session_id]
            self._config[key] = values
        for key in ("tags", "statistics", "recent", "aliases", "descriptions"):
            value = self._config.get(key)
            if isinstance(value, dict):
                value.pop(session_id, None)
            elif isinstance(value, list):
                self._config[key] = [item for item in value if item.get("session_id") != session_id]
        self._touch_config()

    def _default_config(self) -> dict[str, Any]:
        return {"favorites": [], "pinned": [], "tags": {}, "recent": [], "statistics": {}, "aliases": {}, "descriptions": {}}

    def _touch_config(self) -> None:
        self.config_revision += 1

    @staticmethod
    def _now() -> str:
        from datetime import datetime

        return datetime.utcnow().isoformat(timespec="seconds") + "Z"
