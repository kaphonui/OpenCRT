from __future__ import annotations
from dataclasses import dataclass
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent

@dataclass(frozen=True, slots=True)
class KeyboardAction:
    text: str | None = None
    copy_selection: bool = False
    paste_clipboard: bool = False

class KeyboardMapper:
    _PROFILES: dict[str, dict[str, str]] = {
        "linux": {
            "backspace": "\x7f",
            "delete": "\x1b[3~",
            "insert": "\x1b[2~",
            "home": "\x1b[H",
            "end": "\x1b[F",
            "pageup": "\x1b[5~",
            "pagedown": "\x1b[6~",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "left": "\x1b[D",
            "right": "\x1b[C",
        },
        "cisco": {
            "backspace": "\x08",
            "delete": "\x1b[3~",
            "insert": "\x1b[2~",
            "home": "\x1b[H",
            "end": "\x1b[F",
            "pageup": "\x1b[5~",
            "pagedown": "\x1b[6~",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "left": "\x1b[D",
            "right": "\x1b[C",
        },
        "windows": {
            "backspace": "\x08",
            "delete": "\x1b[3~",
            "insert": "\x1b[2~",
            "home": "\x1b[H",
            "end": "\x1b[F",
            "pageup": "\x1b[5~",
            "pagedown": "\x1b[6~",
            "up": "\x1b[A",
            "down": "\x1b[B",
            "left": "\x1b[D",
            "right": "\x1b[C",
        },
    }

    _FUNCTION_KEYS = {
        Qt.Key.Key_F1: "\x1bOP",
        Qt.Key.Key_F2: "\x1bOQ",
        Qt.Key.Key_F3: "\x1bOR",
        Qt.Key.Key_F4: "\x1bOS",
        Qt.Key.Key_F5: "\x1b[15~",
        Qt.Key.Key_F6: "\x1b[17~",
        Qt.Key.Key_F7: "\x1b[18~",
        Qt.Key.Key_F8: "\x1b[19~",
        Qt.Key.Key_F9: "\x1b[20~",
        Qt.Key.Key_F10: "\x1b[21~",
        Qt.Key.Key_F11: "\x1b[23~",
        Qt.Key.Key_F12: "\x1b[24~",
    }

    def __init__(self, profile: str = "linux") -> None:
        self.profile = self.normalize_profile(profile)

    @classmethod
    def normalize_profile(cls, profile: str) -> str:
        profile = (profile or "linux").strip().casefold()
        return profile if profile in cls._PROFILES else "linux"

    def translate(self, event: QKeyEvent, has_selection: bool = False) -> KeyboardAction | None:
        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(modifiers & Qt.KeyboardModifier.AltModifier)
        meta = bool(modifiers & Qt.KeyboardModifier.MetaModifier)

        if ctrl and key == Qt.Key.Key_Insert:
            return KeyboardAction(copy_selection=True)
        if ctrl and shift and key in (Qt.Key.Key_C, Qt.Key.Key_Insert):
            return KeyboardAction(copy_selection=True)
        if (shift and key == Qt.Key.Key_Insert) or (ctrl and key == Qt.Key.Key_V):
            return KeyboardAction(paste_clipboard=True)
        if ctrl and shift and key == Qt.Key.Key_V:
            return KeyboardAction(paste_clipboard=True)
        if ctrl and key == Qt.Key.Key_C:
            if has_selection:
                return KeyboardAction(copy_selection=True)
            return KeyboardAction(text="\x03")

        if ctrl and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            return KeyboardAction(text=chr(ord("A") + (key - Qt.Key.Key_A) + 1))

        if key in self._FUNCTION_KEYS and not (ctrl or shift or alt or meta):
            return KeyboardAction(text=self._FUNCTION_KEYS[key])

        profile_map = self._PROFILES[self.profile]
        key_map = {
            Qt.Key.Key_Backspace: profile_map["backspace"],
            Qt.Key.Key_Delete: profile_map["delete"],
            Qt.Key.Key_Insert: profile_map["insert"],
            Qt.Key.Key_Home: profile_map["home"],
            Qt.Key.Key_End: profile_map["end"],
            Qt.Key.Key_PageUp: profile_map["pageup"],
            Qt.Key.Key_PageDown: profile_map["pagedown"],
            Qt.Key.Key_Up: profile_map["up"],
            Qt.Key.Key_Down: profile_map["down"],
            Qt.Key.Key_Left: profile_map["left"],
            Qt.Key.Key_Right: profile_map["right"],
            Qt.Key.Key_Return: "\r",
            Qt.Key.Key_Enter: "\r",
            Qt.Key.Key_Tab: "\t",
            Qt.Key.Key_Escape: "\x1b",
        }
        if key in key_map and not (ctrl or alt or meta):
            return KeyboardAction(text=key_map[key])

        text = event.text()
        if text and not (ctrl or alt or meta):
            return KeyboardAction(text=text)
        return None
