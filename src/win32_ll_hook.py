"""
Windows Low-Level Keyboard/Mouse Hook.

대상 창이 활성화되어 있을 때만 키를 가로채서
IME 활성/비활성/토글과 문자 입력을 직접 처리한다.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable

from .logger import warn

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_QUIT = 0x0012
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_BACK = 0x08
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_HANGUL = 0x15
LLKHF_INJECTED = 0x10
LLMHF_INJECTED = 0x01
MAPVK_VK_TO_CHAR = 2

_VK_TO_CONTROL_NAME: dict[int, str] = {
    VK_RETURN: "enter",
    VK_ESCAPE: "esc",
    VK_LMENU: "left alt",
    VK_RMENU: "right alt",
    VK_HANGUL: "right alt",
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", ctypes.wintypes.POINT),
        ("mouseData", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]


LRESULT = ctypes.c_long
HHOOK = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, HINSTANCE, ctypes.wintypes.DWORD]
user32.SetWindowsHookExW.restype = HHOOK
user32.CallNextHookEx.argtypes = [HHOOK, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [HHOOK]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.wintypes.SHORT
user32.MapVirtualKeyW.argtypes = [ctypes.c_uint, ctypes.c_uint]
user32.MapVirtualKeyW.restype = ctypes.c_uint
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel32.GetModuleHandleW.restype = HINSTANCE
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
user32.GetMessageW.restype = ctypes.wintypes.BOOL
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = ctypes.wintypes.BOOL
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.PostThreadMessageW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL
user32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
user32.GetKeyboardState.restype = ctypes.wintypes.BOOL
user32.ToUnicodeEx.argtypes = [
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.POINTER(ctypes.wintypes.WCHAR),
    ctypes.c_int,
    ctypes.c_uint,
    ctypes.wintypes.HKL,
]
user32.ToUnicodeEx.restype = ctypes.c_int
user32.GetKeyboardLayout.argtypes = [ctypes.wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.wintypes.HKL


def _is_shift_pressed() -> bool:
    return (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0


def _is_ctrl_pressed() -> bool:
    return (user32.GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0


_SHIFT_DIGIT = ")!@#$%^&*("


def _vk_scan_to_char(vk: int, scan: int, shifted: bool) -> str | None:
    state = (ctypes.c_ubyte * 256)()
    state_p = ctypes.cast(ctypes.byref(state), ctypes.POINTER(ctypes.c_ubyte))
    user32.GetKeyboardState(state_p)
    state[vk] = 0x80
    if shifted:
        state[VK_SHIFT] = 0x80
    buf = (ctypes.wintypes.WCHAR * 2)()
    count = user32.ToUnicodeEx(vk, scan, state_p, buf, 2, 0, user32.GetKeyboardLayout(0))
    if count == 1 and buf[0]:
        return buf[0]
    if count == 2 and buf[0]:
        return buf[0] + (buf[1] if buf[1] else "")
    return None


def _vk_to_key_name(vk: int, shifted: bool, scan: int) -> str | None:
    if vk in _VK_TO_CONTROL_NAME:
        return _VK_TO_CONTROL_NAME[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(ord("a") + (vk - 0x41))
    if 0x30 <= vk <= 0x39:
        return _SHIFT_DIGIT[vk - 0x30] if shifted else chr(ord("0") + (vk - 0x30))
    if vk == VK_BACK:
        return "backspace"
    ch = _vk_scan_to_char(vk, scan, shifted)
    if ch and len(ch) == 1 and ord(ch) >= 0x20:
        return ch
    ch = user32.MapVirtualKeyW(vk, MAPVK_VK_TO_CHAR) & 0xFFFF
    if ch and 0x20 <= ch < 0x10000:
        return chr(ch)
    return None


def start_ll_hook(
    intercept_letters: str,
    intercept_punctuations: str,
    decision_callback: Callable[[], tuple[bool, bool]],
    event_handler: Callable[[str, bool], None],
    deactivate_key_names: set[str],
    deactivate_mouse_names: set[str],
    activate_key: str,
    toggle_key: str,
    ime_off_block_key_names: set[str],
) -> tuple[Callable[[], None], threading.Thread]:
    keyboard_hook_handle: list[HHOOK | None] = [None]
    mouse_hook_handle: list[HHOOK | None] = [None]
    thread_id: list[int] = []
    blocked_keyups: set[int] = set()
    pending_activation = False

    def keyboard_hook_proc(nCode: int, wParam: int, lParam: int) -> int:
        nonlocal pending_activation

        def next_() -> int:
            return int(user32.CallNextHookEx(keyboard_hook_handle[0], nCode, wParam, lParam))

        if nCode != HC_ACTION:
            return next_()

        struct_ptr = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT))
        if struct_ptr.contents.flags & LLKHF_INJECTED:
            return next_()

        vk = struct_ptr.contents.vkCode
        is_keydown = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        if not is_keydown:
            if vk in blocked_keyups:
                blocked_keyups.discard(vk)
                return 1
            return next_()

        shifted = _is_shift_pressed()
        ctrl_held = _is_ctrl_pressed()
        key_name = _vk_to_key_name(vk, shifted, struct_ptr.contents.scanCode)
        if key_name is None:
            return next_()

        is_target, ime_on = decision_callback()
        if ime_on:
            pending_activation = False
        effective_ime_on = ime_on or pending_activation

        if key_name in deactivate_key_names and is_target and effective_ime_on:
            pending_activation = False
            blocked_keyups.add(vk)
            event_handler(f"__deactivate__:{key_name}", False)
            return 1

        if key_name == toggle_key and is_target and effective_ime_on:
            blocked_keyups.add(vk)
            event_handler("__toggle__", False)
            return 1

        if key_name == activate_key and is_target and not effective_ime_on:
            pending_activation = True
            event_handler("__activate__", False)
            return next_()

        # IME OFF(+ON 예정 아님)이고 대상 창일 때만: 게임 버그 회피용으로 특정 키를 통과시키지 않음.
        if (
            ime_off_block_key_names
            and key_name in ime_off_block_key_names
            and is_target
            and not effective_ime_on
        ):
            blocked_keyups.add(vk)
            return 1

        if ctrl_held and key_name == "v" and is_target and effective_ime_on:
            blocked_keyups.add(vk)
            event_handler("__paste__", False)
            return 1

        if ctrl_held:
            return next_()

        if key_name not in ("backspace", " ") and len(key_name) != 1:
            return next_()
        if key_name == " ":
            pass
        elif len(key_name) == 1 and key_name not in intercept_letters and key_name not in intercept_punctuations:
            return next_()
        if not (is_target and effective_ime_on):
            return next_()

        blocked_keyups.add(vk)
        event_handler(key_name, shifted)
        return 1

    def mouse_hook_proc(nCode: int, wParam: int, lParam: int) -> int:
        def next_() -> int:
            return int(user32.CallNextHookEx(mouse_hook_handle[0], nCode, wParam, lParam))

        if nCode != HC_ACTION:
            return next_()

        if wParam == WM_LBUTTONDOWN:
            key_name = "mouse left"
        elif wParam == WM_RBUTTONDOWN:
            key_name = "mouse right"
        else:
            return next_()

        if key_name not in deactivate_mouse_names:
            return next_()

        struct_ptr = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT))
        if struct_ptr.contents.flags & LLMHF_INJECTED:
            return next_()

        is_target, ime_on = decision_callback()
        if not (is_target and ime_on):
            return next_()

        event_handler(f"__deactivate__:{key_name}", False)
        return next_()

    callback_type = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
    keyboard_hook_cb = callback_type(keyboard_hook_proc)
    mouse_hook_cb = callback_type(mouse_hook_proc)

    def run_loop() -> None:
        thread_id.append(threading.get_ident())
        hmod = kernel32.GetModuleHandleW(None)
        keyboard_hook_handle[0] = user32.SetWindowsHookExW(WH_KEYBOARD_LL, keyboard_hook_cb, hmod, 0)
        if not keyboard_hook_handle[0]:
            warn("Failed to install WH_KEYBOARD_LL hook")
            return

        if deactivate_mouse_names:
            mouse_hook_handle[0] = user32.SetWindowsHookExW(WH_MOUSE_LL, mouse_hook_cb, hmod, 0)
            if not mouse_hook_handle[0]:
                warn("Failed to install WH_MOUSE_LL hook")
                user32.UnhookWindowsHookEx(keyboard_hook_handle[0])
                keyboard_hook_handle[0] = None
                return

        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if mouse_hook_handle[0]:
            user32.UnhookWindowsHookEx(mouse_hook_handle[0])
            mouse_hook_handle[0] = None
        if keyboard_hook_handle[0]:
            user32.UnhookWindowsHookEx(keyboard_hook_handle[0])
            keyboard_hook_handle[0] = None

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    def stop() -> None:
        if thread_id and thread.is_alive():
            user32.PostThreadMessageW(thread_id[0], WM_QUIT, 0, 0)

    return stop, thread
