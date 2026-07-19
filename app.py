
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from opencrt.events import EventBus
from opencrt.main_window import MainWindow
from opencrt.credential_vault import CredentialVault
from opencrt.command_tools import HistoryManager, SnippetManager
from opencrt.quick_connect import QuickConnectEngine
from opencrt.search_service import SearchService
from opencrt.reconnect import ConnectionEventBus, KnownHostsManager, ReconnectManager
from opencrt.session_productivity import SessionProductivityPack
from opencrt.session_service import SessionService
from opencrt.storage import SessionStore

APP_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
USER_DIR = Path(os.getenv("APPDATA", Path.home())) / "OpenCRT"
DATA_DIR = USER_DIR / "data"
LOG_DIR = USER_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("OpenCRT")
    app.setStyle("Fusion")
    app.setStyleSheet("""
        QMainWindow, QWidget { background:#181b20; color:#e6edf3; }
        QLineEdit, QTreeWidget, QPlainTextEdit, QSpinBox, QComboBox {
            background:#0f1318; color:#e6edf3; border:1px solid #30363d;
            border-radius:4px; padding:6px;
        }
        QTreeWidget::item { padding:5px; }
        QTreeWidget::item:selected { background:#1f6feb; }
        QPushButton { background:#21262d; border:1px solid #30363d; padding:6px 10px; border-radius:4px; }
        QPushButton:hover { background:#30363d; }
        QMenuBar, QMenu, QToolBar, QStatusBar { background:#161b22; color:#e6edf3; }
        QTabBar::tab { background:#21262d; padding:8px 12px; }
        QTabBar::tab:selected { background:#30363d; }
    """)
    bundled = APP_DIR / "data" / "sessions.json"
    store = SessionStore(DATA_DIR / "sessions.json", DATA_DIR / "config.json", bundled)
    event_bus = EventBus()
    session_service = SessionService(store, event_bus)
    productivity = SessionProductivityPack(session_service)
    search_service = SearchService(event_bus, productivity)
    quick_connect = QuickConnectEngine(session_service)
    credential_vault = CredentialVault(DATA_DIR / "credentials.bin", DATA_DIR / "credentials.json")
    reconnect_manager = ReconnectManager(event_bus=ConnectionEventBus())
    known_hosts = KnownHostsManager(DATA_DIR / "known_hosts.json")
    history_manager = HistoryManager(DATA_DIR / "command_history.json")
    snippet_manager = SnippetManager(DATA_DIR / "snippets.json")
    window = MainWindow(session_service, search_service, event_bus, LOG_DIR, quick_connect, productivity, credential_vault, reconnect_manager, known_hosts, history_manager, snippet_manager)
    quick_connect.open_session.connect(window.open_session)
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
