from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from typing import Callable

from .credential_vault import CredentialResolver, CredentialVault
from .models import Session
from .reconnect import KnownHostsManager


class BaseConnection:
    def __init__(
        self,
        session: Session,
        output: Callable[[str], None],
        closed: Callable[[str], None],
    ) -> None:
        self.session = session
        self.output = output
        self.closed = closed
        self.running = False

    def connect(self) -> None:
        raise NotImplementedError

    def send(self, data: str) -> None:
        raise NotImplementedError

    def close(self) -> None:
        self.running = False


class SSHConnection(BaseConnection):
    def __init__(
        self,
        *args,
        credential_vault: CredentialVault | None = None,
        known_hosts: KnownHostsManager | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.client = None
        self.channel = None
        self.credential_vault = credential_vault
        self.known_hosts = known_hosts

    def connect(self) -> None:
        def worker() -> None:
            try:
                import paramiko

                self.output(f"[Đang SSH tới {self.session.host}:{self.session.port}...]\n")
                self.client = paramiko.SSHClient()
                self.client.load_system_host_keys()
                if self.known_hosts is not None:
                    self.client.set_missing_host_key_policy(self._host_key_policy(paramiko, self.known_hosts))
                else:
                    self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                credentials = self._resolve_credentials()
                kwargs = {
                    "hostname": self.session.host,
                    "port": self.session.port,
                    "username": credentials.username or None,
                    "timeout": 12,
                    "banner_timeout": 30,
                    "auth_timeout": 30,
                    "look_for_keys": not bool(credentials.password),
                    "allow_agent": credentials.use_ssh_agent or not bool(credentials.password),
                }
                if credentials.password:
                    kwargs["password"] = credentials.password
                if credentials.private_key_path:
                    kwargs["key_filename"] = credentials.private_key_path
                if credentials.passphrase:
                    kwargs["passphrase"] = credentials.passphrase
                self.client.connect(**kwargs)
                self.channel = self.client.invoke_shell(term="xterm-256color", width=140, height=40)
                self.channel.settimeout(0.2)
                self.running = True
                self.output("[Đã kết nối SSH]\n")
                while self.running:
                    try:
                        if self.channel.recv_ready():
                            data = self.channel.recv(65535)
                            if not data:
                                break
                            self.output(data.decode("utf-8", errors="replace"))
                        else:
                            time.sleep(0.02)
                    except socket.timeout:
                        continue
                self.closed("closed")
            except Exception as exc:
                self.output(f"\n[Lỗi SSH: {exc}]\n")
                self.closed("error")
            finally:
                self.close()
        threading.Thread(target=worker, daemon=True).start()

    def _resolve_credentials(self):
        if self.credential_vault is None:
            return CredentialResolver(CredentialVault(Path.home() / ".opencrt_credentials")).resolve_for_session(self.session)
        return CredentialResolver(self.credential_vault).resolve_for_session(self.session)

    @staticmethod
    def _host_key_policy(paramiko_module, manager: KnownHostsManager | None):
        class Policy(paramiko_module.MissingHostKeyPolicy):
            def __init__(self, manager: KnownHostsManager | None):
                self.manager = manager

            def missing_host_key(self, client, hostname, key):
                fingerprint = key.get_fingerprint().hex()
                if self.manager is None:
                    raise paramiko_module.SSHException("Unknown host key")
                if self.manager.is_trusted(hostname, fingerprint):
                    return
                if self.manager.has_host(hostname):
                    raise paramiko_module.SSHException("Host key changed")
                self.manager.trust_once(hostname, fingerprint)

        return Policy(manager)

    def send(self, data: str) -> None:
        if self.running and self.channel:
            self.channel.send(data)

    def close(self) -> None:
        self.running = False
        try:
            if self.channel:
                self.channel.close()
        except Exception:
            pass
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass


class TelnetConnection(BaseConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sock = None

    @staticmethod
    def strip_iac(data: bytes) -> tuple[bytes, bytes]:
        out = bytearray()
        reply = bytearray()
        i = 0
        IAC, DO, DONT, WILL, WONT = 255, 253, 254, 251, 252
        while i < len(data):
            if data[i] == IAC and i + 2 < len(data):
                cmd, opt = data[i + 1], data[i + 2]
                if cmd in (DO, DONT):
                    reply.extend((IAC, WONT, opt))
                elif cmd in (WILL, WONT):
                    reply.extend((IAC, DONT, opt))
                i += 3
            else:
                out.append(data[i])
                i += 1
        return bytes(out), bytes(reply)

    def connect(self) -> None:
        def worker() -> None:
            try:
                self.output(f"[Đang Telnet tới {self.session.host}:{self.session.port}...]\n")
                self.sock = socket.create_connection((self.session.host, self.session.port), timeout=12)
                self.sock.settimeout(0.3)
                self.running = True
                self.output("[Đã kết nối Telnet]\n")
                while self.running:
                    try:
                        data = self.sock.recv(65535)
                        if not data:
                            break
                        clean, reply = self.strip_iac(data)
                        if reply:
                            self.sock.sendall(reply)
                        if clean:
                            self.output(clean.decode("utf-8", errors="replace"))
                    except socket.timeout:
                        continue
                self.closed("closed")
            except Exception as exc:
                self.output(f"\n[Lỗi Telnet: {exc}]\n")
                self.closed("error")
            finally:
                self.close()
        threading.Thread(target=worker, daemon=True).start()

    def send(self, data: str) -> None:
        if self.running and self.sock:
            self.sock.sendall(data.encode("utf-8", errors="replace"))

    def close(self) -> None:
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass


class SerialConnection(BaseConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.serial = None

    def connect(self) -> None:
        def worker() -> None:
            try:
                import serial
                self.output(f"[Đang mở {self.session.serial_port} @ {self.session.baudrate}...]\n")
                self.serial = serial.Serial(
                    self.session.serial_port,
                    self.session.baudrate,
                    timeout=0.2,
                )
                self.running = True
                self.output("[Đã kết nối Serial]\n")
                while self.running:
                    data = self.serial.read(4096)
                    if data:
                        self.output(data.decode("utf-8", errors="replace"))
                self.closed("closed")
            except Exception as exc:
                self.output(f"\n[Lỗi Serial: {exc}]\n")
                self.closed("error")
            finally:
                self.close()
        threading.Thread(target=worker, daemon=True).start()

    def send(self, data: str) -> None:
        if self.running and self.serial:
            self.serial.write(data.encode("utf-8", errors="replace"))

    def close(self) -> None:
        self.running = False
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
