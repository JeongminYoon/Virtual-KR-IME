"""
Windows 입력 주입 레이어.

한글 문자열(유니코드)을 활성 윈도우(예: 게임 채팅창)에 전송하고,
필요한 경우 백스페이스를 여러 번 보내는 기능을 제공한다.
"""

import time
import ctypes

import keyboard

from .logger import log


user32 = ctypes.windll.user32


ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


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


KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_KEYUP = 0x0002


def _send_unicode_char(ch: str) -> None:
    """단일 유니코드 문자 입력."""
    if not ch:
        return

    code = ord(ch)
    log("Send unicode char:", ch, hex(code))

    ki_down = KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)
    ki_up = KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)

    inp_down = INPUT()
    inp_down.type = 1  # INPUT_KEYBOARD
    inp_down.union.ki = ki_down

    inp_up = INPUT()
    inp_up.type = 1  # INPUT_KEYBOARD
    inp_up.union.ki = ki_up

    # 일부 게임에서는 인자로 INPUT 구조체의 포인터 배열을 기대하는 경우가 있어
    # 단일 구조체가 아니라 길이 1의 배열을 만들어 전달한다.
    arr = (INPUT * 2)()
    arr[0] = inp_down
    arr[1] = inp_up

    n = user32.SendInput(2, ctypes.byref(arr), ctypes.sizeof(INPUT))
    if n != 2:
        log("SendInput failed (unicode): sent", n)


def send_text(text: str, delay_per_char: float = 0.0) -> None:
    """문자열 전체를 유니코드 키 입력으로 전송."""
    if not text:
        return

    log("send_text:", repr(text))
    for ch in text:
        _send_unicode_char(ch)
        if delay_per_char > 0:
            time.sleep(delay_per_char)


def send_backspaces(n: int, delay_sec: float = 0.0) -> None:
    """백스페이스 키를 n번 보낸다. delay_sec > 0 이면 각 키 사이에 대기(게임 채팅 호환)."""
    if n <= 0:
        return
    log("send_backspaces:", n)
    for i in range(n):
        keyboard.send("backspace")
        if delay_sec > 0 and i < n - 1:
            time.sleep(delay_sec)

