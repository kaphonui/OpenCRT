
from __future__ import annotations
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLineEdit, QSpinBox, QWidget
)
from .models import Session

class AuthDialog(QDialog):
    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"SSH Login - {session.name}")
        self.username = QLineEdit(session.username)
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.private_key = QLineEdit()
        self.passphrase = QLineEdit()
        self.passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.remember_username = QCheckBox("Remember username")
        self.remember_password = QCheckBox("Remember password")
        self.remember_key = QCheckBox("Remember key")
        layout = QFormLayout(self)
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        layout.addRow("Private Key", self.private_key)
        layout.addRow("Passphrase", self.passphrase)
        layout.addRow("", self.remember_username)
        layout.addRow("", self.remember_password)
        layout.addRow("", self.remember_key)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

class SessionDialog(QDialog):
    def __init__(self, session: Session, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.setWindowTitle("Session")
        self.name = QLineEdit(session.name)
        self.protocol = QComboBox()
        self.protocol.addItems(["ssh", "telnet", "serial"])
        self.protocol.setCurrentText(session.protocol)
        self.group = QLineEdit(session.group)
        self.host = QLineEdit(session.host)
        self.port = QSpinBox()
        self.port.setMaximum(65535)
        self.port.setValue(session.port)
        self.username = QLineEdit(session.username)
        self.serial_port = QLineEdit(session.serial_port)
        self.baudrate = QSpinBox()
        self.baudrate.setMaximum(4000000)
        self.baudrate.setValue(session.baudrate)
        self.keyboard_profile = QComboBox()
        self.keyboard_profile.addItems(["linux", "cisco", "windows"])
        self.keyboard_profile.setCurrentText(session.keyboard_profile)
        self.keepalive = QComboBox()
        self.keepalive.addItems(["30", "60", "120", "custom"])
        self.keepalive.setCurrentText(str(session.keepalive_seconds) if session.keepalive_seconds in {30, 60, 120} else "custom")
        self.max_retries = QSpinBox()
        self.max_retries.setMaximum(20)
        self.max_retries.setValue(session.reconnect_max_retries)
        self.reconnect_delay = QSpinBox()
        self.reconnect_delay.setMaximum(3600)
        self.reconnect_delay.setValue(session.reconnect_delay_seconds)

        layout = QFormLayout(self)
        layout.addRow("Name", self.name)
        layout.addRow("Protocol", self.protocol)
        layout.addRow("Group", self.group)
        layout.addRow("Host", self.host)
        layout.addRow("Port", self.port)
        layout.addRow("Username", self.username)
        layout.addRow("COM Port", self.serial_port)
        layout.addRow("Baudrate", self.baudrate)
        layout.addRow("Keyboard Profile", self.keyboard_profile)
        layout.addRow("KeepAlive", self.keepalive)
        layout.addRow("Max Retries", self.max_retries)
        layout.addRow("Reconnect Delay", self.reconnect_delay)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def apply(self) -> Session:
        self.session.name = self.name.text().strip()
        self.session.protocol = self.protocol.currentText()
        self.session.group = self.group.text().strip() or "Ungrouped"
        self.session.host = self.host.text().strip()
        self.session.port = self.port.value()
        self.session.username = self.username.text().strip()
        self.session.serial_port = self.serial_port.text().strip()
        self.session.baudrate = self.baudrate.value()
        self.session.keyboard_profile = self.keyboard_profile.currentText().strip().casefold() or "linux"
        self.session.keepalive_seconds = int(self.keepalive.currentText()) if self.keepalive.currentText().isdigit() else 60
        self.session.reconnect_max_retries = self.max_retries.value()
        self.session.reconnect_delay_seconds = self.reconnect_delay.value()
        return self.session
