"""
Windows 입력 주입 레이어.

텍스트는 유니코드 SendInput으로, 백스페이스는 keyboard 경로로 전송한다.
"""

import ctypes
import time

import keyboard

from .logger import log


user32 = ctypes.windll.user32
user32.SendInput.argtypes = [ctypes.c_uint, ctypes.c_void_p, ctypes.c_int]
user32.SendInput.restype = ctypes.c_uint


ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_short),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("union", _INPUTUNION),
    ]


def _build_unicode_inputs(ch: str) -> tuple[INPUT, INPUT]:
    code = ord(ch)
    key_down = INPUT()
    key_down.type = 1
    key_down.union.ki = KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)

    key_up = INPUT()
    key_up.type = 1
    key_up.union.ki = KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
    return key_down, key_up


def _send_unicode_char(ch: str) -> None:
    if not ch:
        return

    log("Send unicode char:", ch, hex(ord(ch)))
    key_down, key_up = _build_unicode_inputs(ch)

    batch = (INPUT * 2)()
    batch[0] = key_down
    batch[1] = key_up

    sent = user32.SendInput(2, batch, ctypes.sizeof(INPUT))
    if sent != 2:
        log("SendInput failed (unicode): sent", sent)


def send_text(text: str, delay_per_char: float = 0.0) -> None:
    """문자열 전체를 유니코드 키 입력으로 전송."""
    if not text:
        return

    log("send_text:", repr(text))
    if delay_per_char <= 0:
        max_chars_per_batch = 32
        for start in range(0, len(text), max_chars_per_batch):
            chunk = text[start:start + max_chars_per_batch]
            batch = (INPUT * (len(chunk) * 2))()
            idx = 0
            for ch in chunk:
                key_down, key_up = _build_unicode_inputs(ch)
                batch[idx] = key_down
                batch[idx + 1] = key_up
                idx += 2
            sent = user32.SendInput(len(batch), batch, ctypes.sizeof(INPUT))
            if sent != len(batch):
                log("SendInput failed (batch text): sent", sent, "expected", len(batch))
        return

    for ch in text:
        _send_unicode_char(ch)
        if delay_per_char > 0:
            time.sleep(delay_per_char)


def send_backspaces(n: int, delay_sec: float = 0.0) -> None:
    """백스페이스 키를 n번 보낸다."""
    if n <= 0:
        return

    log("send_backspaces:", n)
    for _ in range(n):
        keyboard.send("backspace")
        if delay_sec > 0:
            time.sleep(delay_sec)

