from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

try:
    import keyring  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    keyring = None

from cryptography.fernet import Fernet


@dataclass(slots=True)
class CredentialRecord:
    id: str
    username: str = ""
    password: str = ""
    private_key_path: str = ""
    passphrase: str = ""
    use_ssh_agent: bool = False
    remember_username: bool = False
    remember_password: bool = False
    remember_key: bool = False


class CredentialVault:
    def __init__(self, vault_path: Path, metadata_path: Path | None = None) -> None:
        self.vault_path = vault_path
        self.metadata_path = metadata_path or vault_path.with_suffix(".json")
        self._cache: dict[str, CredentialRecord] = {}
        self._fernet = Fernet(self._load_or_create_key())
        self._load()

    def save(self, record: CredentialRecord) -> str:
        credential_id = record.id or self._new_id(record.username or record.private_key_path or "credential")
        record.id = credential_id
        if keyring is not None and record.password:
            try:
                keyring.set_password("OpenCRT", credential_id, json.dumps(asdict(record), ensure_ascii=False))
                self._cache[credential_id] = record
                self._save_local()
                return credential_id
            except Exception:
                pass
        self._cache[credential_id] = record
        self._save_local()
        return credential_id

    def get(self, credential_id: str) -> CredentialRecord | None:
        if credential_id in self._cache:
            return self._cache[credential_id]
        if keyring is not None:
            try:
                payload = keyring.get_password("OpenCRT", credential_id)
                if payload:
                    try:
                        record_data = json.loads(payload)
                    except json.JSONDecodeError:
                        return None
                    if not isinstance(record_data, dict):
                        return None
                    record = CredentialRecord(**record_data)
                    self._cache[credential_id] = record
                    return record
            except Exception:
                pass
        return None

    def delete(self, credential_id: str) -> None:
        self._cache.pop(credential_id, None)
        if keyring is not None:
            try:
                keyring.delete_password("OpenCRT", credential_id)
            except Exception:
                pass
        self._save_local()

    def resolve(self, credential_id: str | None, defaults: CredentialRecord | None = None) -> CredentialRecord | None:
        if credential_id:
            record = self.get(credential_id)
            if record is not None:
                return record
        return defaults

    def _load(self) -> None:
        if not self.metadata_path.exists():
            return
        raw_text = self.metadata_path.read_text(encoding="utf-8")
        data: dict[str, Any] | None = None
        try:
            loaded = json.loads(raw_text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict):
            data = loaded
        else:
            try:
                decrypted = self._fernet.decrypt(raw_text.encode("utf-8"))
                loaded = json.loads(decrypted.decode("utf-8"))
            except Exception:
                loaded = None
            if isinstance(loaded, dict):
                data = loaded
        if data is None:
            return
        for credential_id, payload in data.items():
            if isinstance(payload, dict):
                try:
                    self._cache[credential_id] = CredentialRecord(**payload)
                except TypeError:
                    continue

    def _save_local(self) -> None:
        payload = {credential_id: asdict(record) for credential_id, record in self._cache.items()}
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        token = self._fernet.encrypt(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        self.metadata_path.write_text(token.decode("utf-8"), encoding="utf-8")

    def _load_or_create_key(self) -> bytes:
        key_file = self.vault_path.with_suffix(".key")
        if key_file.exists():
            raw = key_file.read_bytes()
        else:
            seed = f"{os.getenv('USER', '')}:{os.getenv('USERNAME', '')}:{Path.home()}:OpenCRT".encode("utf-8")
            raw = hashlib.sha256(seed).digest()
            key_file.parent.mkdir(parents=True, exist_ok=True)
            key_file.write_bytes(raw)
        return base64.urlsafe_b64encode(raw[:32])

    @staticmethod
    def _new_id(seed: str) -> str:
        return hashlib.sha1(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


class CredentialResolver:
    def __init__(self, vault: CredentialVault) -> None:
        self.vault = vault

    def resolve_for_session(self, session) -> CredentialRecord:
        credential = self.vault.resolve(getattr(session, "credential_id", ""))
        if credential is not None:
            return credential
        return CredentialRecord(
            id="",
            username=getattr(session, "username", ""),
            password=getattr(session, "password", ""),
            private_key_path=getattr(session, "private_key_path", ""),
            passphrase=getattr(session, "passphrase", ""),
            use_ssh_agent=getattr(session, "use_ssh_agent", False),
        )
