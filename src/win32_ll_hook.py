"""
Windows Low-Level Keyboard Hook (WH_KEYBOARD_LL).

모든 키 입력을 한 곳에서 받아, 대상 창·IME 상태에 따라 활성/끄기/토글/글자만 처리.
다른 창에서는 키를 통과시켜 입력이 정상 동작하도록 함.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import queue
import threading
from typing import Callable

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
HC_ACTION = 0
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_SHIFT = 0x10
VK_BACK = 0x08
LLKHF_INJECTED = 0x10  # 우리가 SendInput 등으로 보낸 키는 통과
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_HANGUL = 0x15  # 한/영 키(물리 키가 이 코드를 보내는 경우)
MAPVK_VK_TO_CHAR = 2

# IME 제어용 키: keyboard 라이브러리와 동일한 이름 사용 (동시입력 시 훅이 놓치지 않도록 LL에서 처리)
_VK_TO_CONTROL_NAME: dict[int, str] = {
    VK_RETURN: "enter",
    VK_ESCAPE: "esc",
    VK_LMENU: "left alt",
    VK_RMENU: "right alt",
    VK_HANGUL: "right alt",  # 한/영 키를 config의 right alt와 동일하게 취급
}

# KBDLLHOOKSTRUCT
class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

LRESULT = ctypes.c_long
HHOOK = ctypes.c_void_p
HINSTANCE = ctypes.c_void_p

# SetWindowsHookExW(idHook, lpfn, hMod, dwThreadId)
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

# GetMessageW
class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.wintypes.HWND),
        ("message", ctypes.wintypes.UINT),
        ("wParam", ctypes.wintypes.WPARAM),
        ("lParam", ctypes.wintypes.LPARAM),
        ("time", ctypes.wintypes.DWORD),
        ("pt", ctypes.wintypes.POINT),
    ]

user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.wintypes.HWND, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
user32.GetMessageW.restype = ctypes.wintypes.BOOL

user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.TranslateMessage.restype = ctypes.wintypes.BOOL

user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.restype = LRESULT

user32.PostThreadMessageW.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.UINT, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM]
user32.PostThreadMessageW.restype = ctypes.wintypes.BOOL

# 키보드 상태·ToUnicodeEx (특수문자 시프트 반영)
user32.GetKeyboardState.argtypes = [ctypes.POINTER(ctypes.c_ubyte)]
user32.GetKeyboardState.restype = ctypes.wintypes.BOOL

user32.ToUnicodeEx.argtypes = [
    ctypes.c_uint, ctypes.c_uint,
    ctypes.POINTER(ctypes.c_ubyte), ctypes.POINTER(ctypes.wintypes.WCHAR),
    ctypes.c_int, ctypes.c_uint, ctypes.wintypes.HKL,
]
user32.ToUnicodeEx.restype = ctypes.c_int

user32.GetKeyboardLayout.argtypes = [ctypes.wintypes.DWORD]
user32.GetKeyboardLayout.restype = ctypes.wintypes.HKL


def _is_shift_pressed() -> bool:
    return (user32.GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0


_SHIFT_DIGIT = ")!@#$%^&*("

def _vk_scan_to_char(vk: int, scan: int, shifted: bool) -> str | None:
    """ToUnicodeEx로 실제 입력될 문자 반환 (시프트·레이아웃 반영)."""
    state = (ctypes.c_ubyte * 256)()
    state_p = ctypes.cast(ctypes.byref(state), ctypes.POINTER(ctypes.c_ubyte))
    user32.GetKeyboardState(state_p)
    state[vk] = 0x80
    if shifted:
        state[VK_SHIFT] = 0x80
    buf = (ctypes.wintypes.WCHAR * 2)()
    n = user32.ToUnicodeEx(vk, scan, state_p, buf, 2, 0, user32.GetKeyboardLayout(0))
    if n == 1 and buf[0]:
        return buf[0]
    if n == 2 and buf[0]:
        return buf[0] + (buf[1] if buf[1] else "")
    return None


def _vk_to_key_name(vk: int, shifted: bool, scan: int = 0) -> str | None:
    """가상키 코드를 우리가 쓰는 키 이름으로 변환. intercept 대상이 아니면 None."""
    if vk in _VK_TO_CONTROL_NAME:
        return _VK_TO_CONTROL_NAME[vk]
    if 0x41 <= vk <= 0x5A:
        return chr(ord("a") + (vk - 0x41))
    if 0x30 <= vk <= 0x39:
        if shifted:
            return _SHIFT_DIGIT[vk - 0x30]
        return chr(ord("0") + (vk - 0x30))
    if vk == VK_BACK:
        return "backspace"
    # 특수문자: ToUnicodeEx로 시프트 반영 (?, ! 등)
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
    decision_callback: Callable[[], tuple[bool, bool]],  # (is_target_window, ime_enabled)
    key_queue: queue.Queue[tuple[str, bool]],
    deactivate_key_names: set[str],
    activate_key: str,
    toggle_key: str,
) -> tuple[Callable[[], None], threading.Thread]:
    """Low-level 훅 스레드 시작. 반환: (stop_fn, thread). key_queue에는 (key_name, shifted) 또는 제어용 (__deactivate__:key 등)이 들어감."""

    hook_handle: HHOOK | None = None
    thread_id: list[int] = []
    blocked_keyups: set[int] = set()
    pending_activation: list[bool] = [False]

    def hook_proc(nCode: int, wParam: int, lParam: int) -> int:
        nonlocal hook_handle
        def next_() -> int:
            return int(user32.CallNextHookEx(hook_handle, nCode, wParam, lParam))

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
                return 1  # block key up
            return next_()

        shifted = _is_shift_pressed()
        scan = struct_ptr.contents.scanCode
        key_name = _vk_to_key_name(vk, shifted, scan)
        if key_name is None:
            return next_()

        is_target, ime_on = decision_callback()
        if ime_on and pending_activation[0]:
            pending_activation[0] = False
        effective_ime_on = ime_on or pending_activation[0]

        # IME 제어 키: keyboard 라이브러리는 동시입력 시 이벤트를 놓칠 수 있으므로 LL에서 처리
        if key_name in deactivate_key_names and is_target and effective_ime_on:
            pending_activation[0] = False
            blocked_keyups.add(vk)
            try:
                key_queue.put_nowait((f"__deactivate__:{key_name}", False))
            except queue.Full:
                pass
            return 1
        if key_name == toggle_key and is_target and effective_ime_on:
            blocked_keyups.add(vk)
            try:
                key_queue.put_nowait(("__toggle__", False))
            except queue.Full:
                pass
            return 1
        if key_name == activate_key and is_target and not effective_ime_on:
            # Enter로 채팅을 열자마자 바로 타이핑해도 다음 키들이
            # 활성화 이벤트 처리 전 유실되지 않도록 훅 단계에서 즉시 반영한다.
            pending_activation[0] = True
            try:
                key_queue.put_nowait(("__activate__", False))
            except queue.Full:
                pass
            return next_()  # 키는 게임으로 통과 (채팅창 열기 등)

        if key_name == "backspace":
            pass
        elif key_name == " ":
            pass  # 스페이스: 대상+IME일 때 가로채서 큐에 넣고 우리가 전송 (순서 보장)
        elif len(key_name) == 1:
            if key_name not in intercept_letters and key_name not in intercept_punctuations:
                return next_()
        else:
            return next_()

        if not (is_target and effective_ime_on):
            return next_()

        blocked_keyups.add(vk)
        try:
            key_queue.put_nowait((key_name, shifted))
        except queue.Full:
            pass
        return 1  # block key (반드시 Python int로 반환해야 훅이 정상 동작)

    # CFUNCTYPE: 반환을 c_long으로 받되 콜백 내부에서는 int 반환
    CBFUNC = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
    hook_cb = CBFUNC(hook_proc)

    def run_loop() -> None:
        nonlocal hook_handle
        thread_id.append(threading.get_ident())
        hmod = kernel32.GetModuleHandleW(None)
        hook_handle = user32.SetWindowsHookExW(WH_KEYBOARD_LL, hook_cb, hmod, 0)
        if not hook_handle:
            return
        msg = MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook_handle)
        hook_handle = None

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    def stop() -> None:
        if thread_id and thread.is_alive():
            user32.PostThreadMessageW(thread_id[0], WM_QUIT, 0, 0)

    return stop, thread
