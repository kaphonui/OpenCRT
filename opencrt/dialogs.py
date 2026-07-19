
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
        self.remember = QCheckBox("Remember trong sessions.json (không mã hóa)")
        layout = QFormLayout(self)
        layout.addRow("Username", self.username)
        layout.addRow("Password", self.password)
        layout.addRow("", self.remember)
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

        layout = QFormLayout(self)
        layout.addRow("Name", self.name)
        layout.addRow("Protocol", self.protocol)
        layout.addRow("Group", self.group)
        layout.addRow("Host", self.host)
        layout.addRow("Port", self.port)
        layout.addRow("Username", self.username)
        layout.addRow("COM Port", self.serial_port)
        layout.addRow("Baudrate", self.baudrate)
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
        return self.session
