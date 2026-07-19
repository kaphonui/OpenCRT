from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QKeyEvent, QTextCursor
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QMenu, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget, QApplication

from .actions import Action, ActionContext, ActionDispatcher, ActionRegistry, default_action_registry
from .ansi_parser import ANSIParser
from .clipboard import ClipboardEngine
from .credential_vault import CredentialVault
from .command_tools import HistoryManager
from .reconnect import ConnectionEventBus, ConnectionEventType, KnownHostsManager, ReconnectManager
from .hyperlink import HyperlinkEngine
from .keyboard_mapper import KeyboardAction, KeyboardMapper
from .models import Session
from .protocols import SSHConnection, SerialConnection, TelnetConnection
from .screen_buffer import ScreenBuffer
from .selection import SelectionEngine, SelectionMode, SelectionPoint
from .terminal_search import SearchLineEdit, SearchOptions, TerminalSearchEngine
from .session_productivity import SessionProductivityPack
from .terminal_renderer import TerminalRenderer


class TerminalView(QPlainTextEdit):
    send_text = Signal(str)
    search_requested = Signal()
    history_requested = Signal()
    display_refreshed = Signal()
    action_requested = Signal(object, object)

    def __init__(
        self,
        keyboard_mapper: KeyboardMapper,
        action_registry: ActionRegistry | None = None,
        action_dispatcher: ActionDispatcher | None = None,
    ) -> None:
        super().__init__()
        self.keyboard_mapper = keyboard_mapper
        self.ansi_parser = ANSIParser()
        self.buffer = ScreenBuffer()
        self.selection_engine = SelectionEngine()
        self.clipboard_engine = ClipboardEngine(self.selection_engine)
        self.search_engine = TerminalSearchEngine()
        self.hyperlink_engine = HyperlinkEngine()
        self.action_registry = action_registry or default_action_registry()
        self.action_dispatcher = action_dispatcher or ActionDispatcher()
        self.action_dispatcher.action_requested.connect(self.action_requested.emit)
        self.renderer = TerminalRenderer(self, self.selection_engine, self.search_engine, self.hyperlink_engine)
        self._syncing_scrollbar = False
        self._dragging_selection = False
        self._last_click_at = 0.0
        self._last_click_pos: tuple[int, int] | None = None
        self._click_count = 0
        self.setReadOnly(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setMouseTracking(True)
        font = QFont("Cascadia Mono", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setStyleSheet("background:#0e1116;color:#d9e2ec;border:0;padding:8px;")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalScrollBar().valueChanged.connect(self._on_scrollbar_changed)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.search_requested.emit()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_R:
            self.history_requested.emit()
            return
        if self._handle_selection_shortcut(event):
            return
        action = self.keyboard_mapper.translate(event, self.selection_engine.has_selection())
        if action is None:
            return
        self.handle_keyboard_action(action)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            point = self._point_from_mouse(event)
            if self._show_action_menu(event, point):
                return
            paste = self.clipboard_engine.paste_from_clipboard()
            if paste:
                self.send_text.emit(paste)
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            paste = self.clipboard_engine.paste_from_clipboard()
            if paste:
                self.send_text.emit(paste)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            point = self._point_from_mouse(event)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                link = self.hyperlink_engine.link_at(self.buffer, point.line, point.column)
                if link is not None:
                    self.hyperlink_engine.activate(self.buffer, link)
                    self.refresh_display()
                    return
            click_count = self._update_click_count(event)
            if click_count >= 3:
                self.selection_engine.select_line(self.buffer, point.line)
                self._dragging_selection = False
            elif click_count == 2:
                self.selection_engine.select_word(self.buffer, point.line, point.column)
                self._dragging_selection = False
            else:
                mode = SelectionMode.COLUMN if event.modifiers() & Qt.KeyboardModifier.AltModifier else SelectionMode.NORMAL
                self.selection_engine.begin(point, mode)
                self._dragging_selection = True
            self.refresh_display()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging_selection and event.buttons() & Qt.MouseButton.LeftButton:
            self.selection_engine.update(self._point_from_mouse(event))
            self.refresh_display()
            return
        point = self._point_from_mouse(event)
        changed = self.hyperlink_engine.update_hover(self.buffer, point.line, point.column)
        if self.hyperlink_engine.link_at(self.buffer, point.line, point.column) is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.unsetCursor()
        if changed:
            self.refresh_display()
            return
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self.hyperlink_engine.clear_hover():
            self.unsetCursor()
            self.refresh_display()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging_selection = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            point = self._point_from_mouse(event)
            self.selection_engine.select_word(self.buffer, point.line, point.column)
            self._click_count = 2
            self._last_click_pos = (event.position().x(), event.position().y())
            self._last_click_at = time.monotonic()
            self.refresh_display()
            return
        super().mouseDoubleClickEvent(event)

    def handle_keyboard_action(self, action: KeyboardAction) -> None:
        if action.copy_selection:
            self.clipboard_engine.copy_selection(self.buffer)
            return
        if action.paste_clipboard:
            text = self.clipboard_engine.paste_from_clipboard()
            if text:
                self.send_text.emit(text)
            return
        if action.text:
            self.send_text.emit(action.text)

    def append_output(self, text: str) -> None:
        self.ansi_parser.feed(text, self.buffer)
        self.refresh_display()

    def clear(self) -> None:
        self.buffer.clear_screen(2)
        self.selection_engine.clear()
        self.refresh_display()

    def scroll_up(self, amount: int = 1) -> None:
        self.buffer.scroll_up(amount)
        self.refresh_display()

    def scroll_down(self, amount: int = 1) -> None:
        self.buffer.scroll_down(amount)
        self.refresh_display()

    def jump_top(self) -> None:
        self.buffer.jump_top()
        self.refresh_display()

    def jump_bottom(self) -> None:
        self.buffer.jump_bottom()
        self.refresh_display()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        metrics = self.fontMetrics()
        char_width = max(1, metrics.horizontalAdvance("M"))
        line_height = max(1, metrics.lineSpacing())
        columns = max(1, (self.viewport().width() - 16) // char_width)
        rows = max(1, self.viewport().height() // line_height)
        self.buffer.resize(rows, columns)
        self.refresh_display()

    def refresh_display(self) -> None:
        self.search_engine.ensure(self.buffer)
        self.hyperlink_engine.ensure(self.buffer)
        self.renderer.render(self.buffer)
        self._sync_scrollbar_state()
        self.display_refreshed.emit()

    def copy_selection(self) -> None:
        self.clipboard_engine.copy_selection(self.buffer)

    def _show_action_menu(self, event, point: SelectionPoint) -> bool:
        context = self._action_context_at(point)
        if context is None:
            return False
        groups = self.action_registry.groups_for(context)
        if not groups:
            return False
        menu = QMenu(self)
        first_group = True
        for group in groups:
            if not first_group:
                menu.addSeparator()
            first_group = False
            if len(groups) > 1:
                menu.addSection(group.label)
            for action in group.actions:
                menu_action = menu.addAction(action.label)
                menu_action.triggered.connect(
                    lambda checked=False, selected_action=action: self._dispatch_action(context, selected_action)
                )
        menu.exec(event.globalPosition().toPoint())
        return True

    def _dispatch_action(self, context: ActionContext, action: Action) -> None:
        self.action_dispatcher.dispatch(context, action)

    def _action_context_at(self, point: SelectionPoint) -> ActionContext | None:
        if self.selection_engine.has_selection() and self.selection_engine.contains(self.buffer, point.line, point.column):
            selection = self.selection_engine.selection
            mode = selection.mode.name.lower() if selection else "normal"
            return ActionContext(
                type="selection",
                value=self.selection_engine.selected_text(self.buffer),
                source="terminal",
                metadata={"line": point.line, "column": point.column, "mode": mode},
            )
        link = self.hyperlink_engine.link_at(self.buffer, point.line, point.column)
        if link is None:
            return None
        return ActionContext(
            type=link.kind.value,
            value=self.hyperlink_engine.target_for(self.buffer, link),
            source="hyperlink",
            metadata={"line": point.line, "column": point.column, "start": link.start, "end": link.end},
        )

    def _handle_selection_shortcut(self, event: QKeyEvent) -> bool:
        modifiers = event.modifiers()
        key = event.key()
        if modifiers == Qt.KeyboardModifier.ControlModifier and key == Qt.Key.Key_A:
            self.selection_engine.select_all(self.buffer)
            self.refresh_display()
            return True
        if modifiers & Qt.KeyboardModifier.ShiftModifier and key in {
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        }:
            if self.selection_engine.selection is None:
                self.selection_engine.begin(self._current_cursor_point())
            line_delta = 0
            column_delta = 0
            if key == Qt.Key.Key_Left:
                column_delta = -1
            elif key == Qt.Key.Key_Right:
                column_delta = 1
            elif key == Qt.Key.Key_Up:
                line_delta = -1
            elif key == Qt.Key.Key_Down:
                line_delta = 1
            self.selection_engine.move_active(self.buffer, line_delta=line_delta, column_delta=column_delta)
            self.refresh_display()
            return True
        return False

    def _current_cursor_point(self) -> SelectionPoint:
        cursor = self.textCursor()
        line = self.buffer.history_offset + self.buffer.viewport_top + cursor.blockNumber()
        column = cursor.positionInBlock()
        return SelectionPoint(line, column)

    def _point_from_mouse(self, event) -> SelectionPoint:
        cursor = self.cursorForPosition(event.position().toPoint())
        line = self.buffer.history_offset + self.buffer.viewport_top + cursor.blockNumber()
        column = cursor.positionInBlock()
        return SelectionPoint(line, column)

    def _update_click_count(self, event) -> int:
        now = time.monotonic()
        pos = (int(event.position().x()), int(event.position().y()))
        if self._last_click_pos == pos and now - self._last_click_at <= 0.45:
            self._click_count += 1
        else:
            self._click_count = 1
        self._last_click_pos = pos
        self._last_click_at = now
        return self._click_count

    def _sync_scrollbar_state(self) -> None:
        scrollbar = self.verticalScrollBar()
        maximum = self.buffer.max_viewport_top()
        self._syncing_scrollbar = True
        try:
            scrollbar.setRange(0, maximum)
            scrollbar.setPageStep(max(1, self.buffer.rows))
            scrollbar.setValue(self.buffer.viewport_top)
        finally:
            self._syncing_scrollbar = False

    def _on_scrollbar_changed(self, value: int) -> None:
        if self._syncing_scrollbar:
            return
        if value <= 0:
            self.buffer.jump_top()
        elif value >= self.buffer.max_viewport_top():
            self.buffer.jump_bottom()
        else:
            self.buffer.follow_bottom = False
            self.buffer.viewport_top = value
        self.refresh_display()


class TerminalTab(QWidget):
    output_signal = Signal(str)
    closed_signal = Signal(str)
    action_requested = Signal(object, object)

    def __init__(self, session: Session, log_dir: Path, parent=None, productivity: SessionProductivityPack | None = None, credential_vault: CredentialVault | None = None, reconnect_manager: ReconnectManager | None = None, known_hosts: KnownHostsManager | None = None, history_manager: HistoryManager | None = None) -> None:
        super().__init__(parent)
        self.session = session
        self.log_dir = log_dir
        self.productivity = productivity
        self.credential_vault = credential_vault
        self.known_hosts = known_hosts
        self.history_manager = history_manager
        self.reconnect_manager = reconnect_manager or ReconnectManager(event_bus=ConnectionEventBus())
        self._pending_command = ""
        self.connection = None
        self.log_file = None
        self._connection_started_at: float | None = None
        self._cleaned_up = False
        self.reconnect_manager.reconnect_requested.connect(self._on_reconnect_requested)
        self.reconnect_manager.status_requested.connect(self._update_reconnect_status)

        self.status = QLabel()
        reconnect = QPushButton("Reconnect")
        disconnect = QPushButton("Disconnect")
        clear = QPushButton("Clear")
        self.keyboard_mapper = KeyboardMapper(session.keyboard_profile)
        bar = QHBoxLayout()
        bar.addWidget(self.status)
        bar.addStretch()
        bar.addWidget(clear)
        bar.addWidget(disconnect)
        bar.addWidget(reconnect)

        self.terminal = TerminalView(self.keyboard_mapper)
        self.search_engine = self.terminal.search_engine
        self.search_bar = QWidget()
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(6)
        self.search_input = SearchLineEdit()
        self.search_case = QCheckBox("Case")
        self.search_word = QCheckBox("Word")
        self.search_regex = QCheckBox("Regex")
        self.search_counter = QLabel("0 / 0")
        search_layout.addWidget(QLabel("Search"))
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_case)
        search_layout.addWidget(self.search_word)
        search_layout.addWidget(self.search_regex)
        search_layout.addWidget(self.search_counter)
        self.search_bar.setVisible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.search_bar)
        layout.addWidget(self.terminal)

        clear.clicked.connect(self.terminal.clear)
        disconnect.clicked.connect(self.disconnect)
        reconnect.clicked.connect(self.connect)
        self.terminal.send_text.connect(self.send)
        self.terminal.history_requested.connect(self._show_quick_commands)
        self.terminal.action_requested.connect(self.action_requested.emit)
        self.terminal.search_requested.connect(self.show_search_bar)
        self.search_input.textChanged.connect(self.update_search)
        self.search_case.toggled.connect(self.update_search)
        self.search_word.toggled.connect(self.update_search)
        self.search_regex.toggled.connect(self.update_search)
        self.search_input.next_requested.connect(self.search_next)
        self.search_input.previous_requested.connect(self.search_previous)
        self.search_input.closed_requested.connect(self.hide_search_bar)
        self.terminal.display_refreshed.connect(self.sync_search_counter)
        self.output_signal.connect(self.on_output)
        self.closed_signal.connect(self.on_closed)

    def focus_terminal(self) -> None:
        self.terminal.setFocus(Qt.FocusReason.OtherFocusReason)
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.terminal.setTextCursor(cursor)

    def show_search_bar(self) -> None:
        self.search_bar.setVisible(True)
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()
        self.update_search()

    def hide_search_bar(self) -> None:
        self.search_bar.setVisible(False)
        self.focus_terminal()

    def current_search_options(self) -> SearchOptions:
        return SearchOptions(
            query=self.search_input.text(),
            case_sensitive=self.search_case.isChecked(),
            whole_word=self.search_word.isChecked(),
            regex=self.search_regex.isChecked(),
        )

    def update_search(self, *args) -> None:
        options = self.current_search_options()
        self.search_engine.search(self.terminal.buffer, options)
        self.search_engine.set_current_first()
        self.terminal.refresh_display()

    def search_next(self) -> None:
        self.search_engine.next_match()
        self.terminal.refresh_display()

    def search_previous(self) -> None:
        self.search_engine.previous_match()
        self.terminal.refresh_display()

    def sync_search_counter(self) -> None:
        self.search_counter.setText(self.search_engine.counter_text())

    def connect(self) -> None:
        self.disconnect()
        self._connection_started_at = time.monotonic()
        self.status.setText(f"CONNECTING  {self.session.name}")
        if self.reconnect_manager is not None:
            self.reconnect_manager.clear_manual_disconnect(self.session.id)
        safe = re.sub(r'[<>:"/\\|?*]+', "_", self.session.name)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = (self.log_dir / f"{safe}_{stamp}.log").open("a", encoding="utf-8", errors="replace")
        output = lambda text: self.output_signal.emit(text)
        closed = lambda reason: self.closed_signal.emit(reason)
        event_bus = self.reconnect_manager.event_bus if self.reconnect_manager is not None else None
        if self.session.protocol == "ssh":
            self.connection = SSHConnection(
                self.session,
                output,
                closed,
                event_bus=event_bus,
                credential_vault=self.credential_vault,
                known_hosts=self.known_hosts,
            )
        elif self.session.protocol == "telnet":
            self.connection = TelnetConnection(self.session, output, closed, event_bus=event_bus)
        else:
            self.connection = SerialConnection(self.session, output, closed, event_bus=event_bus)
        self.connection.connect()

    def send(self, text: str) -> None:
        if self.connection:
            try:
                self._record_command_text(text)
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
            if self.productivity is not None:
                self.productivity.record_recent(self.session)
            self.focus_terminal()



    def _record_command_text(self, text: str) -> None:
        self._pending_command += text
        while "\r" in self._pending_command or "\n" in self._pending_command:
            for sep in ("\r", "\n"):
                if sep in self._pending_command:
                    command, remainder = self._pending_command.split(sep, 1)
                    self._pending_command = remainder
                    command = command.strip()
                    if command and self.history_manager is not None:
                        self.history_manager.record(self.session.id, self.session.protocol, self.session.host or self.session.serial_port, command)
                    break

    def _show_quick_commands(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "show_command_panel"):
            parent.show_command_panel()

    def _on_reconnect_requested(self, session_id: str) -> None:
        if session_id == self.session.id and self.connection is not None:
            self.connect()

    def _update_reconnect_status(self, text: str) -> None:
        self.status.setText(text)

    def on_closed(self, reason: str) -> None:
        self.status.setText(f"DISCONNECTED  {self.session.name}")

    def disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None
        if self.reconnect_manager is not None:
            self.reconnect_manager.event_bus.emit_event(ConnectionEvent(self.session.id, ConnectionEventType.MANUAL_DISCONNECT, self.session.protocol, "manual disconnect"))
        if self.productivity is not None and self._connection_started_at is not None:
            duration = max(0.0, time.monotonic() - self._connection_started_at)
            self.productivity.record_connection(self.session, duration)
        self._connection_started_at = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None

    def cleanup(self) -> None:
        if self._cleaned_up:
            return
        self._cleaned_up = True
        try:
            self.reconnect_manager.reconnect_requested.disconnect(self._on_reconnect_requested)
        except (TypeError, RuntimeError):
            pass
        try:
            self.reconnect_manager.status_requested.disconnect(self._update_reconnect_status)
        except (TypeError, RuntimeError):
            pass
