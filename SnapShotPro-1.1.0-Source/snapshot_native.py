"""OS integration without polling or an always-running Windows key listener."""
from __future__ import annotations

import ctypes
import os
import platform

from PyQt6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, pyqtSignal


def qt_to_pynput_key(sequence: str) -> str:
    mapping = {"ctrl": "<ctrl>", "control": "<ctrl>", "shift": "<shift>",
               "alt": "<alt>", "meta": "<cmd>", "cmd": "<cmd>",
               "print": "<print_screen>", "printscreen": "<print_screen>",
               "sysreq": "<print_screen>", "space": "<space>", "esc": "<esc>",
               "enter": "<enter>", "return": "<enter>"}
    return "+".join(mapping.get(part.strip().lower(), part.strip().lower()
                    if len(part.strip()) == 1 else "<" + part.strip().lower() + ">")
                    for part in sequence.split("+") if part.strip())


def windows_hotkey(sequence: str) -> tuple[int, int]:
    """Translate a single Qt shortcut into RegisterHotKey modifiers + VK."""
    modifiers = 0x4000  # MOD_NOREPEAT
    vk = None
    for part in sequence.lower().split("+"):
        part = part.strip()
        if part in {"ctrl", "control", "alt", "shift", "meta", "cmd"}:
            modifiers |= {"ctrl": 2, "control": 2, "alt": 1, "shift": 4,
                          "meta": 8, "cmd": 8}[part]
        elif part in {"print", "printscreen", "sysreq"}:
            vk = 0x2C
        elif part == "space":
            vk = 0x20
        elif part.startswith("f") and part[1:].isdigit() and 1 <= int(part[1:]) <= 24:
            vk = 0x70 + int(part[1:]) - 1
        elif len(part) == 1 and part.isascii() and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError(f"Unsupported global shortcut: {sequence}")
    if vk is None:
        raise ValueError("A shortcut needs a key as well as modifiers.")
    return modifiers, vk


class _WindowsEvents(QAbstractNativeEventFilter):
    def __init__(self, callbacks):
        super().__init__()
        self.callbacks = callbacks

    def nativeEventFilter(self, event_type, message):
        if event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            from ctypes.wintypes import MSG
            msg = MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.callbacks:  # WM_HOTKEY
                self.callbacks[msg.wParam]()
                return True, 0
        return False, 0


class GlobalHotkeyManager(QObject):
    trigger_region = pyqtSignal()
    trigger_fullscreen = pyqtSignal()
    trigger_multicapture = pyqtSignal()
    qt_to_pynput_key = staticmethod(qt_to_pynput_key)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._listener = None
        self._native_filter = None
        self._registered = []
        self.failures = []
        self.available = False
        self.reload_hotkeys()

    def reload_hotkeys(self):
        self.stop()
        self.failures = []
        if os.environ.get("SNAPSHOT_DISABLE_HOTKEYS") == "1":
            return
        bindings = [(self.config.hotkey_region, self.trigger_region.emit),
                    (self.config.hotkey_secondary, self.trigger_region.emit),
                    (self.config.hotkey_fullscreen, self.trigger_fullscreen.emit),
                    (self.config.hotkey_multicapture, self.trigger_multicapture.emit)]
        if platform.system() == "Windows":
            callbacks = {}
            for index, (sequence, callback) in enumerate(bindings, 0x5A00):
                try:
                    modifiers, vk = windows_hotkey(sequence)
                    if not ctypes.windll.user32.RegisterHotKey(None, index, modifiers, vk):
                        raise ValueError(f"{sequence} is already in use by Windows or another app.")
                    self._registered.append(index)
                    callbacks[index] = callback
                except Exception as error:
                    self.failures.append(str(error))
            self._native_filter = _WindowsEvents(callbacks)
            QCoreApplication.instance().installNativeEventFilter(self._native_filter)
            self.available = bool(callbacks)
            return
        try:
            from pynput import keyboard
            self._listener = keyboard.GlobalHotKeys({qt_to_pynput_key(seq): callback
                                                     for seq, callback in bindings})
            self._listener.daemon = True
            self._listener.start()
            self.available = True
        except Exception as error:
            self._listener = None
            self.failures.append(f"Global keys unavailable: {error}")

    def stop(self):
        self.available = False
        if self._listener:
            self._listener.stop()
            self._listener = None
        if self._native_filter:
            QCoreApplication.instance().removeNativeEventFilter(self._native_filter)
            self._native_filter = None
        if platform.system() == "Windows":
            for identifier in self._registered:
                ctypes.windll.user32.UnregisterHotKey(None, identifier)
        self._registered.clear()


def scroll_down(x: int, y: int, steps: int = 4):
    if platform.system() == "Windows":
        user32 = ctypes.windll.user32
        user32.SetCursorPos(x, y)
        user32.mouse_event(0x0800, 0, 0, -120 * steps, 0)
    else:
        from pynput.mouse import Controller
        mouse = Controller()
        mouse.position = (x, y)
        mouse.scroll(0, -steps)
