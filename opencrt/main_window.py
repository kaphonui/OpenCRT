
from __future__ import annotations
from pathlib import Path
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QPainter
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLineEdit, QMainWindow, QStyledItemDelegate,
    QMessageBox, QSplitter, QTabWidget, QToolBar, QTreeWidget,
    QTreeWidgetItem, QStyleOptionViewItem, QVBoxLayout, QWidget
)
from .command_tools import HistoryManager, QuickCommandPanel, SnippetManager
from .dialogs import AuthDialog, SessionDialog
from .importer import import_folder, import_zip
from .events import EventBus, FavoriteChanged, SessionEvent
from .models import Session
from .credential_vault import CredentialRecord, CredentialVault
from .quick_connect import QuickConnectEngine
from .reconnect import KnownHostsManager, ReconnectManager
from .search_service import SearchService
from .session_productivity import SessionProductivityPack
from .session_service import SessionService
from .terminal import TerminalTab

SESSION_ROLE = Qt.ItemDataRole.UserRole + 1
GROUP_ROLE = Qt.ItemDataRole.UserRole + 2
FAVORITE_ROLE = Qt.ItemDataRole.UserRole + 3

class FavoriteDelegate(QStyledItemDelegate):
    def __init__(self, toggle_favorite, parent=None) -> None:
        super().__init__(parent)
        self.toggle_favorite = toggle_favorite

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if index.data(GROUP_ROLE):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        star_rect = self.star_rect(opt)
        favorite = bool(index.data(FAVORITE_ROLE))
        text = opt.text
        opt.text = ""
        super().paint(painter, opt, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.GlobalColor.yellow if favorite else option.palette.mid().color())
        painter.drawText(star_rect, Qt.AlignmentFlag.AlignCenter, "★" if favorite else "☆")
        painter.restore()
        text_rect = opt.rect.adjusted(26, 0, -8, 0)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    @staticmethod
    def star_rect(option: QStyleOptionViewItem):
        return option.rect.adjusted(6, 4, -option.rect.width() + 22, -4)

class SessionTreeWidget(QTreeWidget):
    def __init__(self, toggle_favorite, parent=None) -> None:
        super().__init__(parent)
        self.toggle_favorite = toggle_favorite

    def mouseReleaseEvent(self, event) -> None:
        index = self.indexAt(event.position().toPoint())
        if index.isValid() and not index.data(GROUP_ROLE):
            option = QStyleOptionViewItem()
            self.initViewItemOption(option)
            option.rect = self.visualRect(index)
            if FavoriteDelegate.star_rect(option).contains(event.position().toPoint()):
                session_id = index.data(SESSION_ROLE)
                if session_id:
                    self.toggle_favorite(session_id)
                    return
        super().mouseReleaseEvent(event)

class MainWindow(QMainWindow):
    def __init__(self, session_service: SessionService, search_service: SearchService, event_bus: EventBus, log_dir: Path, quick_connect: QuickConnectEngine | None = None, productivity: SessionProductivityPack | None = None, credential_vault: CredentialVault | None = None, reconnect_manager: ReconnectManager | None = None, known_hosts: KnownHostsManager | None = None, history_manager: HistoryManager | None = None, snippet_manager: SnippetManager | None = None) -> None:
        super().__init__()
        self.session_service = session_service
        self.search_service = search_service
        self.event_bus = event_bus
        self.log_dir = log_dir
        self.quick_connect = quick_connect
        self.productivity = productivity or SessionProductivityPack(session_service)
        self.credential_vault = credential_vault
        self.reconnect_manager = reconnect_manager
        self.known_hosts = known_hosts
        self.history_manager = history_manager
        self.snippet_manager = snippet_manager
        self.filter_mode = "all"
        self.setWindowTitle("OpenCRT 0.3.0")
        self.resize(1360, 820)
        self.session_items: dict[int, Session] = {}
        self.event_bus.subscribe_session_events(self._on_session_event)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sessions...")
        self.search.textChanged.connect(self.refresh_tree)
        self.search.returnPressed.connect(self.connect_first_search_result)
        self.search.installEventFilter(self)

        self.tree = SessionTreeWidget(self.toggle_favorite)
        self.tree.setHeaderHidden(True)
        self.tree.setItemDelegate(FavoriteDelegate(self.toggle_favorite, self.tree))
        self.tree.itemDoubleClicked.connect(lambda *_: self.connect_selected())
        self.tree.itemActivated.connect(lambda *_: self.connect_selected())
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.context_menu)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.tree)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(self.tabs)
        splitter.setSizes([320, 1040])
        self.setCentralWidget(splitter)

        self.build_toolbar()
        self.build_filters()
        self.build_menu()
        self.build_command_dock()
        self.statusBar().showMessage("Ready")
        self.refresh_tree()

    def _on_session_event(self, event: SessionEvent) -> None:
        self.refresh_tree()
        if isinstance(event, FavoriteChanged):
            self.reselect_session(event.session_id)

    def build_toolbar(self) -> None:
        toolbar = QToolBar()
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        new_action = QAction("New", self)
        new_action.triggered.connect(self.new_session)
        connect_action = QAction("Connect", self)
        connect_action.triggered.connect(self.connect_selected)
        import_action = QAction("Import ZIP", self)
        import_action.triggered.connect(self.import_zip_action)
        toolbar.addAction(new_action)
        toolbar.addAction(connect_action)
        toolbar.addAction(import_action)

    def build_filters(self) -> None:
        toolbar = QToolBar("Filters")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        self.filter_group = QActionGroup(self)
        self.filter_group.setExclusive(True)
        for label, mode in [("All", "all"), ("Favorites", "favorites"), ("Recent", "recent"), ("Pinned", "pinned"), ("SSH", "ssh"), ("Telnet", "telnet"), ("Serial", "serial")]:
            action = QAction(label, self, checkable=True)
            action.setChecked(mode == "all")
            action.triggered.connect(lambda checked=False, selected_mode=mode: self.set_filter_mode(selected_mode))
            self.filter_group.addAction(action)
            toolbar.addAction(action)

    def build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        import_zip_action = file_menu.addAction("Import SecureCRT ZIP...")
        import_zip_action.triggered.connect(self.import_zip_action)
        import_folder_action = file_menu.addAction("Import SecureCRT folder...")
        import_folder_action.triggered.connect(self.import_folder_action)
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)

        session_menu = self.menuBar().addMenu("Session")
        session_menu.addAction("New", self.new_session)
        session_menu.addAction("Edit", self.edit_selected)
        session_menu.addAction("Delete", self.delete_selected)
        session_menu.addSeparator()
        session_menu.addAction("Connect", self.connect_selected)

    def refresh_tree(self) -> None:
        self.tree.clear()
        self.session_items.clear()
        results = self.search_service.search(self.session_service.list_sessions(), self.search.text(), self.filter_mode)
        first_session_item = None
        for group in results.groups:
            first_session_item = self.add_group(group.name, group.sessions, group.expanded, first_session_item)

        if self.search.text().strip() and results.first_session_id is not None:
            self.reselect_session(results.first_session_id)

        self.statusBar().showMessage(
            f"{len(self.session_service.list_sessions())} sessions • showing {results.visible_count}"
        )

    def add_group(self, group_name: str, sessions: list[Session], expanded: bool, first_session_item):
        group_item = QTreeWidgetItem([group_name])
        group_item.setData(0, GROUP_ROLE, True)
        group_item.setExpanded(expanded)
        self.tree.addTopLevelItem(group_item)
        for session in sorted(sessions, key=lambda s: s.name.casefold()):
            endpoint = session.host if session.protocol != "serial" else session.serial_port
            item = QTreeWidgetItem([f"{session.name}    {endpoint}"])
            item.setData(0, SESSION_ROLE, session.id)
            item.setData(0, FAVORITE_ROLE, session.favorite)
            item.setToolTip(0, f"{session.protocol.upper()}  {endpoint}:{session.port}\nUser: {session.username}")
            group_item.addChild(item)
            self.session_items[id(item)] = session
            if first_session_item is None:
                first_session_item = item
        return first_session_item

    def set_filter_mode(self, mode: str) -> None:
        self.filter_mode = mode
        self.productivity.set_filter_mode(mode)
        self.refresh_tree()

    def connect_first_search_result(self) -> None:
        """Enter trong ô search sẽ kết nối session đang chọn/kết quả đầu tiên."""
        session = self.current_session()
        if session is None:
            results = self.search_service.search(self.session_service.list_sessions(), self.search.text())
            session = self.session_by_id(results.first_session_id) if results.first_session_id else None
        if session is not None:
            self.reselect_session(session.id)
            self.connect_selected()

    def eventFilter(self, watched, event):
        """Điều hướng nhanh từ ô search sang cây session."""
        if watched is self.search and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down:
                if self.current_session() is not None:
                    self.tree.setFocus()
                    return True
                results = self.search_service.search(self.session_service.list_sessions(), self.search.text())
                if results.first_session_id is not None and self.reselect_session(results.first_session_id) is not None:
                    self.tree.setFocus()
                    return True
            if event.key() == Qt.Key.Key_Escape:
                self.search.clear()
                return True
        return super().eventFilter(watched, event)

    def current_session(self) -> Session | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        session_id = item.data(0, SESSION_ROLE)
        if not session_id:
            return None
        return self.session_by_id(session_id)

    def session_by_id(self, session_id: str | None) -> Session | None:
        if session_id is None:
            return None
        return self.session_service.get_session(session_id)

    def toggle_favorite(self, session: Session | str) -> None:
        if isinstance(session, str):
            session = self.session_by_id(session)
        if session is None:
            return
        self.session_service.favorite_session(session.id, not session.favorite)

    def toggle_pin(self, session: Session | str) -> None:
        if isinstance(session, str):
            session = self.session_by_id(session)
        if session is None:
            return
        self.productivity.set_pinned(session.id, not self.session_service.store.metadata_for(session.id).get("pinned", False))
        self.refresh_tree()

    def reselect_session(self, session_id: str) -> QTreeWidgetItem | None:
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                if child.data(0, SESSION_ROLE) == session_id:
                    self.tree.setCurrentItem(child)
                    self.tree.scrollToItem(child)
                    return child
        return None

    def new_session(self) -> None:
        session = Session(name="")
        dialog = SessionDialog(session, self)
        if dialog.exec():
            self.session_service.create_session(dialog.apply())

    def edit_selected(self) -> None:
        session = self.current_session()
        if not session:
            return
        clone = Session.from_dict(session.to_dict())
        dialog = SessionDialog(clone, self)
        if dialog.exec():
            self.session_service.save_session(dialog.apply())

    def delete_selected(self) -> None:
        session = self.current_session()
        if session and QMessageBox.question(self, "OpenCRT", f"Delete '{session.name}'?") == QMessageBox.StandardButton.Yes:
            self.session_service.delete_session(session.id)

    def connect_selected(self) -> None:
        session = self.current_session()
        if session is not None:
            self.open_session(session)

    def open_session(self, session: Session) -> None:
        if session.protocol == "ssh" and not session.password:
            dialog = AuthDialog(session, self)
            if not dialog.exec():
                return
            session.username = dialog.username.text().strip()
            session.password = dialog.password.text()
            session.private_key_path = dialog.private_key.text().strip()
            session.passphrase = dialog.passphrase.text()
            if self.credential_vault is not None and (
                dialog.remember_username.isChecked()
                or dialog.remember_password.isChecked()
                or dialog.remember_key.isChecked()
            ):
                credential_id = self.credential_vault.save(
                    CredentialRecord(
                        id=session.credential_id,
                        username=session.username if dialog.remember_username.isChecked() else "",
                        password=session.password if dialog.remember_password.isChecked() else "",
                        private_key_path=session.private_key_path if dialog.remember_key.isChecked() else "",
                        passphrase=session.passphrase if dialog.remember_key.isChecked() else "",
                    )
                )
                session.credential_id = credential_id
                session.password = ""
                if self.session_service.get_session(session.id) is not None:
                    self.session_service.save_session(session)
        tab = TerminalTab(session, self.log_dir, self, self.productivity, self.credential_vault, self.reconnect_manager, self.known_hosts, self.history_manager)
        if self.quick_connect is not None:
            tab.action_requested.connect(self.quick_connect.handle_action)
        index = self.tabs.addTab(tab, session.name)
        self.tabs.setCurrentIndex(index)
        tab.connect()
        tab._focus_timers = []  # type: ignore[attr-defined]
        for delay in (0, 250):
            timer = QTimer(tab)
            timer.setSingleShot(True)
            timer.timeout.connect(tab.focus_terminal)
            timer.start(delay)
            tab._focus_timers.append(timer)  # type: ignore[attr-defined]

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, TerminalTab):
            widget.disconnect()
            widget.cleanup()
        self.tabs.removeTab(index)
        widget.deleteLater()

    def closeEvent(self, event) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            self.close_tab(index)
        self.event_bus.unsubscribe_session_events(self._on_session_event)
        super().closeEvent(event)

    def context_menu(self, pos) -> None:
        session = self.current_session()
        if session is None:
            return
        menu = self.productivity.menu_builder.build_menu(
            self,
            session,
            {
                "open": lambda: self.open_session(session),
                "duplicate": self._duplicate_selected,
                "rename": self._rename_selected,
                "favorite": lambda: self.toggle_favorite(session),
                "pin": lambda: self.toggle_pin(session),
                "copy_host": lambda: QApplication.clipboard().setText(session.host),
                "copy_ip": lambda: QApplication.clipboard().setText(session.host),
                "copy_username": lambda: QApplication.clipboard().setText(session.username),
                "properties": lambda: QMessageBox.information(self, "OpenCRT", self.session_properties_text(session)),
                "delete": self.delete_selected,
            },
        )
        menu.exec(self.tree.viewport().mapToGlobal(pos))


    def build_command_dock(self) -> None:
        if self.history_manager is None or self.snippet_manager is None:
            return
        self.command_panel = QuickCommandPanel(self.history_manager, self.snippet_manager, self)
        self.command_panel.command_requested.connect(self.send_current_command)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.command_panel)
        self.command_panel.hide()

    def show_command_panel(self) -> None:
        if hasattr(self, "command_panel"):
            self.command_panel.show()
            self.command_panel.raise_()
            self.command_panel.activateWindow()

    def send_current_command(self, command: str) -> None:
        tab = self.current_tab()
        if tab is not None:
            tab.send(command + "\r")

    def current_tab(self):
        widget = self.tabs.currentWidget()
        if isinstance(widget, TerminalTab):
            return widget
        return None


    def import_zip_action(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "SecureCRT ZIP", "", "ZIP (*.zip)")
        if filename:
            self.finish_import(import_zip(filename))

    def import_folder_action(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "SecureCRT Sessions folder")
        if folder:
            self.finish_import(import_folder(folder))

    def _duplicate_selected(self) -> None:
        session = self.current_session()
        if session is not None:
            self.session_service.duplicate_session(session.id)

    def _rename_selected(self) -> None:
        session = self.current_session()
        if session is None:
            return
        dialog = SessionDialog(Session.from_dict(session.to_dict()), self)
        if dialog.exec():
            updated = dialog.apply()
            updated.id = session.id
            self.session_service.save_session(updated)

    def session_properties_text(self, session: Session) -> str:
        meta = self.session_service.store.metadata_for(session.id)
        tags = ", ".join(meta.get("tags", [])) or "—"
        stats = meta.get("statistics", {})
        return (
            f"Name: {session.name}\n"
            f"Protocol: {session.protocol}\n"
            f"Host: {session.host or session.serial_port}\n"
            f"Username: {session.username}\n"
            f"Tags: {tags}\n"
            f"Pinned: {meta.get('pinned', False)}\n"
            f"Favorite: {meta.get('favorite', False)}\n"
            f"Connect count: {stats.get('connect_count', 0)}"
        )

    def finish_import(self, imported: list[Session]) -> None:
        existing = {(s.group.casefold(), s.name.casefold(), s.protocol) for s in self.session_service.list_sessions()}
        added = 0
        for session in imported:
            key = (session.group.casefold(), session.name.casefold(), session.protocol)
            if key not in existing:
                self.session_service.create_session(session)
                existing.add(key)
                added += 1
        QMessageBox.information(self, "OpenCRT", f"Imported {added}/{len(imported)} sessions.")
