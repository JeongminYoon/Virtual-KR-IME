from __future__ import annotations

import ctypes
import time

from .logger import log


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

CF_UNICODETEXT = 13

user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = ctypes.c_bool
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = ctypes.c_bool
user32.IsClipboardFormatAvailable.argtypes = [ctypes.c_uint]
user32.IsClipboardFormatAvailable.restype = ctypes.c_bool
user32.GetClipboardData.argtypes = [ctypes.c_uint]
user32.GetClipboardData.restype = ctypes.c_void_p

kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = ctypes.c_bool


def get_clipboard_text(retries: int = 5, retry_delay_sec: float = 0.01) -> str:
    """윈도우 클립보드의 유니코드 텍스트를 읽어 반환한다."""
    for _ in range(retries):
        if user32.OpenClipboard(None):
            break
        time.sleep(retry_delay_sec)
    else:
        log("OpenClipboard failed")
        return ""

    try:
        if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
            return ""

        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return ""

        locked = kernel32.GlobalLock(handle)
        if not locked:
            return ""

        try:
            text = ctypes.wstring_at(locked) or ""
        finally:
            kernel32.GlobalUnlock(handle)

        return text.replace("\r\n", "\n").replace("\r", "\n")
    finally:
        user32.CloseClipboard()
