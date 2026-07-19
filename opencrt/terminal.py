
from __future__ import annotations
import re
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor, QKeySequence
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget
from .models import Session
from .protocols import SSHConnection, TelnetConnection, SerialConnection

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

class TerminalView(QPlainTextEdit):
    send_text = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Cascadia Mono", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("background:#0e1116;color:#d9e2ec;border:0;padding:8px;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.matches(QKeySequence.StandardKey.Copy):
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            text = QApplication.clipboard().text()
            if text:
                self.send_text.emit(text)
            return
        mapping = {
            Qt.Key.Key_Return: "\r",
            Qt.Key.Key_Enter: "\r",
            Qt.Key.Key_Backspace: "\x7f",
            Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Up: "\x1b[A",
            Qt.Key.Key_Down: "\x1b[B",
            Qt.Key.Key_Left: "\x1b[D",
            Qt.Key.Key_Right: "\x1b[C",
            Qt.Key.Key_Escape: "\x1b",
        }
        if event.key() in mapping:
            self.send_text.emit(mapping[event.key()])
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            if self.textCursor().hasSelection():
                self.copy()
            else:
                self.send_text.emit("\x03")
            return
        text = event.text()
        if text:
            self.send_text.emit(text)

    def append_output(self, text: str) -> None:
        cleaned = ANSI_RE.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(cleaned)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

class TerminalTab(QWidget):
    output_signal = Signal(str)
    closed_signal = Signal(str)

    def __init__(self, session: Session, log_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self.session = session
        self.log_dir = log_dir
        self.connection = None
        self.log_file = None

        self.status = QLabel()
        reconnect = QPushButton("Reconnect")
        disconnect = QPushButton("Disconnect")
        clear = QPushButton("Clear")
        bar = QHBoxLayout()
        bar.addWidget(self.status)
        bar.addStretch()
        bar.addWidget(clear)
        bar.addWidget(disconnect)
        bar.addWidget(reconnect)

        self.terminal = TerminalView()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.terminal)

        clear.clicked.connect(self.terminal.clear)
        disconnect.clicked.connect(self.disconnect)
        reconnect.clicked.connect(self.connect)
        self.terminal.send_text.connect(self.send)
        self.output_signal.connect(self.on_output)
        self.closed_signal.connect(self.on_closed)

    def focus_terminal(self) -> None:
        self.terminal.setFocus(Qt.FocusReason.OtherFocusReason)
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)

    def connect(self) -> None:
        self.disconnect()
        self.status.setText(f"CONNECTING  {self.session.name}")
        safe = re.sub(r'[<>:"/\\|?*]+', "_", self.session.name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = (self.log_dir / f"{safe}_{stamp}.log").open("a", encoding="utf-8", errors="replace")
        output = lambda text: self.output_signal.emit(text)
        closed = lambda reason: self.closed_signal.emit(reason)
        if self.session.protocol == "ssh":
            self.connection = SSHConnection(self.session, output, closed)
        elif self.session.protocol == "telnet":
            self.connection = TelnetConnection(self.session, output, closed)
        else:
            self.connection = SerialConnection(self.session, output, closed)
        self.connection.connect()

    def send(self, text: str) -> None:
        if self.connection:
            try:
                self.connection.send(text)
            except Exception as exc:
                self.on_output(f"\n[Lỗi gửi: {exc}]\n")

    def on_output(self, text: str) -> None:
        self.terminal.append_output(text)
        if self.log_file:
            self.log_file.write(text)
            self.log_file.flush()
        if "[Đã kết nối" in text:
            self.status.setText(f"CONNECTED  {self.session.protocol.upper()}  {self.session.host or self.session.serial_port}")
            self.focus_terminal()

    def on_closed(self, reason: str) -> None:
        self.status.setText(f"DISCONNECTED  {self.session.name}")

    def disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
