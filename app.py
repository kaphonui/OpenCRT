
from __future__ import annotations
import os
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from opencrt.main_window import MainWindow
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
    store = SessionStore(DATA_DIR / "sessions.json", bundled)
    window = MainWindow(store, LOG_DIR)
    window.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())
