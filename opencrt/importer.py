
from __future__ import annotations
from pathlib import Path
import re
import zipfile
from .models import Session

def decode_ini(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1258", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")

def parse_securecrt_ini(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        match = re.match(r'^[S]:\"([^\"]+)\"=(.*)$', line)
        if match:
            result[match.group(1)] = match.group(2).strip()
            continue
        match = re.match(r'^[D]:\"([^\"]+)\"=([0-9A-Fa-f]{8})$', line)
        if match:
            result[match.group(1)] = str(int(match.group(2), 16))
    return result

def parse_session(path_name: str, data: bytes) -> Session | None:
    path = Path(path_name)
    if path.name.lower().startswith("__folderdata__"):
        return None
    values = parse_securecrt_ini(decode_ini(data))
    protocol = values.get("Protocol Name", "").strip().upper()
    parts = path.parts
    relative = parts[1:] if len(parts) > 1 else parts
    group = " / ".join(relative[:-1]) or "Imported"
    name = path.stem

    if protocol in {"SSH2", "SSH"}:
        host = values.get("Hostname", "").strip()
        if not host:
            return None
        return Session(
            name=name,
            protocol="ssh",
            host=host,
            port=int(values.get("[SSH2] Port", "22") or 22),
            username=values.get("Username", "").strip(),
            group=group,
            source=path_name,
        )
    if protocol == "TELNET":
        host = values.get("Hostname", "").strip()
        if not host:
            return None
        return Session(
            name=name,
            protocol="telnet",
            host=host,
            port=int(values.get("Port", "23") or 23),
            username=values.get("Username", "").strip(),
            group=group,
            source=path_name,
        )
    if protocol in {"SERIAL", "SERIAL-COM"}:
        return Session(
            name=name,
            protocol="serial",
            group=group,
            serial_port=values.get("Com Port", values.get("Port", "COM1")),
            baudrate=int(values.get("Baud Rate", "9600") or 9600),
            source=path_name,
        )
    return None

def import_zip(filename: str) -> list[Session]:
    sessions: list[Session] = []
    with zipfile.ZipFile(filename) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".ini"):
                session = parse_session(name, archive.read(name))
                if session:
                    sessions.append(session)
    return sessions

def import_folder(folder: str) -> list[Session]:
    root = Path(folder)
    sessions: list[Session] = []
    for path in root.rglob("*.ini"):
        rel = str(path.relative_to(root.parent))
        session = parse_session(rel, path.read_bytes())
        if session:
            sessions.append(session)
    return sessions
