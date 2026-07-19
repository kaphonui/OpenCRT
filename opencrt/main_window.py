
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QInputDialog, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QSplitter, QTabWidget, QToolBar, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget
)
from .dialogs import AuthDialog, SessionDialog
from .importer import import_folder, import_zip
from .models import Session
from .storage import SessionStore
from .terminal import TerminalTab

class MainWindow(QMainWindow):
    def __init__(self, store: SessionStore, log_dir: Path) -> None:
        super().__init__()
        self.store = store
        self.log_dir = log_dir
        self.setWindowTitle("OpenCRT 0.3.0")
        self.resize(1360, 820)
        self.session_items: dict[int, Session] = {}

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search sessions...")
        self.search.textChanged.connect(self.refresh_tree)
        self.search.returnPressed.connect(self.connect_first_search_result)
        self.search.installEventFilter(self)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
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
        self.build_menu()
        self.statusBar().showMessage("Ready")
        self.refresh_tree()

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
        query = self.search.text().strip().casefold()
        groups: dict[str, list[Session]] = {}
        for session in self.store.sessions:
            haystack = f"{session.name} {session.host} {session.username} {session.group} {session.protocol}".casefold()
            if query and query not in haystack:
                continue
            groups.setdefault(session.group or "Ungrouped", []).append(session)

        first_session_item = None
        for group_name in sorted(groups, key=str.casefold):
            group_item = QTreeWidgetItem([group_name])
            # Khi đang search, luôn bung group để thấy kết quả ngay.
            group_item.setExpanded(bool(query))
            self.tree.addTopLevelItem(group_item)
            for session in sorted(groups[group_name], key=lambda s: s.name.casefold()):
                endpoint = session.host if session.protocol != "serial" else session.serial_port
                item = QTreeWidgetItem([f"{session.name}    {endpoint}"])
                item.setToolTip(0, f"{session.protocol.upper()}  {endpoint}:{session.port}\nUser: {session.username}")
                group_item.addChild(item)
                self.session_items[id(item)] = session
                if first_session_item is None:
                    first_session_item = item

        # Search xong tự chọn kết quả đầu tiên. Chỉ cần Enter là kết nối.
        if query and first_session_item is not None:
            self.tree.setCurrentItem(first_session_item)
            self.tree.scrollToItem(first_session_item)

        self.statusBar().showMessage(f"{len(self.store.sessions)} sessions • showing {len(self.session_items)}")

    def connect_first_search_result(self) -> None:
        """Enter trong ô search sẽ kết nối session đang chọn/kết quả đầu tiên."""
        if not self.current_session():
            # Trường hợp selection chưa được Qt cập nhật, chọn child đầu tiên.
            for index in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(index)
                if group.childCount():
                    self.tree.setCurrentItem(group.child(0))
                    break
        if self.current_session():
            self.connect_selected()

    def eventFilter(self, watched, event):
        """Điều hướng nhanh từ ô search sang cây session."""
        if watched is self.search and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Down:
                current = self.tree.currentItem()
                if current is not None:
                    self.tree.setFocus()
                    self.tree.setCurrentItem(current)
                    return True
            if event.key() == Qt.Key.Key_Escape:
                self.search.clear()
                return True
        return super().eventFilter(watched, event)

    def current_session(self) -> Session | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return self.session_items.get(id(item))

    def new_session(self) -> None:
        session = Session(name="")
        dialog = SessionDialog(session, self)
        if dialog.exec():
            self.store.upsert(dialog.apply())
            self.refresh_tree()

    def edit_selected(self) -> None:
        session = self.current_session()
        if not session:
            return
        clone = Session.from_dict(session.to_dict())
        dialog = SessionDialog(clone, self)
        if dialog.exec():
            self.store.upsert(dialog.apply())
            self.refresh_tree()

    def delete_selected(self) -> None:
        session = self.current_session()
        if session and QMessageBox.question(self, "OpenCRT", f"Delete '{session.name}'?") == QMessageBox.StandardButton.Yes:
            self.store.delete(session.id)
            self.refresh_tree()

    def connect_selected(self) -> None:
        session = self.current_session()
        if not session:
            return
        if session.protocol == "ssh" and not session.password:
            dialog = AuthDialog(session, self)
            if not dialog.exec():
                return
            session.username = dialog.username.text().strip()
            session.password = dialog.password.text()
            if dialog.remember.isChecked():
                self.store.upsert(session)
        tab = TerminalTab(session, self.log_dir, self)
        index = self.tabs.addTab(tab, session.name)
        self.tabs.setCurrentIndex(index)
        tab.connect()
        # Sau khi mở kết nối, chuyển con trỏ khỏi ô Search vào terminal.
        QTimer.singleShot(0, tab.focus_terminal)
        QTimer.singleShot(250, tab.focus_terminal)

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if isinstance(widget, TerminalTab):
            widget.disconnect()
        self.tabs.removeTab(index)
        widget.deleteLater()

    def context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction("Connect", self.connect_selected)
        menu.addAction("Edit", self.edit_selected)
        menu.addAction("Delete", self.delete_selected)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def import_zip_action(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(self, "SecureCRT ZIP", "", "ZIP (*.zip)")
        if filename:
            self.finish_import(import_zip(filename))

    def import_folder_action(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "SecureCRT Sessions folder")
        if folder:
            self.finish_import(import_folder(folder))

    def finish_import(self, imported: list[Session]) -> None:
        existing = {(s.group.casefold(), s.name.casefold(), s.protocol) for s in self.store.sessions}
        added = 0
        for session in imported:
            key = (session.group.casefold(), session.name.casefold(), session.protocol)
            if key not in existing:
                self.store.sessions.append(session)
                existing.add(key)
                added += 1
        self.store.save()
        self.refresh_tree()
        QMessageBox.information(self, "OpenCRT", f"Imported {added}/{len(imported)} sessions.")
