"""
전역 키 후킹 및 가상 한글 모드 제어.

LL 훅으로 대상 창의 키 입력만 가로채고,
현재 화면과의 diff를 기준으로 조합 결과를 다시 주입한다.
"""

from __future__ import annotations

import ctypes
import threading
import time
from typing import Callable

import keyboard

from . import win32_ll_hook
from .clipboard_windows import get_clipboard_text
from .config import settings
from .hangul_ime_core import HangulIMECore
from .injector_windows import send_backspaces, send_text
from .logger import log


class KeyboardManager:
    def __init__(self) -> None:
        self.ime_enabled = False
        self.korean_mode = False
        self.core = HangulIMECore()
        self.last_text = ""
        self._last_deactivate_by_activate_key = 0.0
        self._paste_in_progress = False
        self._ll_stop: Callable[[], None] | None = None
        self._update_screen_lock = threading.Lock()

    def _is_target_window(self) -> bool:
        raw = (settings.target_window_keywords or "").strip()
        if not raw:
            return True

        keywords = [part.strip().lower() for part in raw.split(",") if part.strip()]
        if not keywords:
            return True

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        buf = ctypes.create_unicode_buffer(256)
        if user32.GetWindowTextW(hwnd, buf, 256) == 0:
            return False
        title = buf.value.lower()
        return any(keyword in title for keyword in keywords)

    def _parse_deactivate_config(self) -> tuple[set[str], set[str], str, str]:
        raw_keys = [
            part.strip().lower()
            for part in (settings.ime_deactivate_keys or "").split(",")
            if part.strip()
        ]
        mouse_keys = {"mouse left", "mouse right"}
        deactivate_keys = {
            ("esc" if key == "escape" else key)
            for key in raw_keys
            if key not in mouse_keys
        }
        deactivate_mouse_keys = {key for key in raw_keys if key in mouse_keys}
        activate_key = (settings.ime_activate_key or "").strip().lower()
        toggle_key = (settings.language_toggle_key or "").strip().lower()
        return deactivate_keys, deactivate_mouse_keys, activate_key, toggle_key

    def _parse_ime_off_block_keys(self, activate_key: str) -> set[str]:
        """IME OFF일 때만 훅에서 막을 키 이름 집합. activate_key는 제외."""
        raw = (settings.ime_off_block_keys or "").strip()
        if not raw:
            return set()
        out: set[str] = set()
        for part in raw.split(","):
            k = part.strip().lower()
            if not k:
                continue
            k = "esc" if k == "escape" else k
            if k == activate_key:
                continue
            out.add(k)
        return out

    def activate_ime(self) -> None:
        if not self._is_target_window():
            return

        deactivate_keys, _, activate_key, _ = self._parse_deactivate_config()
        if self.ime_enabled:
            if activate_key in deactivate_keys:
                log("IME activate key pressed while ON -> treated as deactivate")
                self._deactivate_ime(reason=activate_key)
            return

        if self._last_deactivate_by_activate_key > 0:
            if time.time() - self._last_deactivate_by_activate_key < 0.08:
                return
            self._last_deactivate_by_activate_key = 0.0

        self.ime_enabled = True
        self.core.reset()
        self.last_text = ""
        log("Virtual Hangul IME ON (" + ("Korean" if self.korean_mode else "English") + " mode)")

    def toggle_language_mode(self) -> None:
        if not self._is_target_window() or not self.ime_enabled:
            return
        self.korean_mode = not self.korean_mode
        log("Language mode:", "Korean" if self.korean_mode else "English")

    def _normalize_paste_text(self, text: str) -> str:
        """단일 줄 채팅 입력에 맞게 붙여넣기 텍스트를 정리한다."""
        return text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ").replace("\t", " ")

    def _insert_text_chunked(
        self,
        text: str,
        *,
        write_delay_override: float = 0.0,
    ) -> None:
        chunk_size = max(1, settings.paste_chunk_size)
        self._paste_in_progress = True
        try:
            for start in range(0, len(text), chunk_size):
                chunk = text[start:start + chunk_size]
                self.core.insert_text(chunk)
                self._sync_output(write_delay_override=write_delay_override)
                if start + chunk_size < len(text):
                    time.sleep(settings.write_delay_sec)
        finally:
            self._paste_in_progress = False

    def _paste_text(self, text: str) -> None:
        self._insert_text_chunked(text)

    def _handle_hook_event(self, key_name: str, shifted: bool) -> None:
        if self._paste_in_progress:
            return

        if key_name.startswith("__deactivate__:"):
            reason = key_name.split(":", 1)[1]
            log("LL deactivate key:", reason)
            self._deactivate_ime(reason=reason)
            if not reason.startswith("mouse "):
                keyboard.send(reason)
            return

        if key_name == "__activate__":
            log("LL activate key")
            self.activate_ime()
            return

        if key_name == "__toggle__":
            log("LL toggle language")
            self.toggle_language_mode()
            return

        if key_name == "__paste__":
            text = self._normalize_paste_text(get_clipboard_text())
            if text:
                self._paste_text(text)
            return

        if key_name == "backspace":
            if not self.core.text:
                send_backspaces(1)
                return
            self.core.handle_backspace()
            self._sync_output()
            return

        if key_name == " ":
            self.core.handle_space()
            keyboard.send("space")
            self.last_text = self.core.text
            return

        if len(key_name) != 1:
            return

        if key_name in settings.intercept_punctuations:
            self.core.feed_key(key_name, shifted=False)
        else:
            self.core.feed_key(key_name, shifted=shifted, as_english=not self.korean_mode)
        self._sync_output()

    def _sync_output(self, *, write_delay_override: float | None = None) -> None:
        with self._update_screen_lock:
            new_text = self.core.text
            if self.last_text == new_text:
                return

            common_len = 0
            for prev_ch, curr_ch in zip(self.last_text, new_text):
                if prev_ch != curr_ch:
                    break
                common_len += 1

            backs = len(self.last_text) - common_len
            tail = new_text[common_len:]

            if backs > 0 and self._is_target_window():
                send_backspaces(backs, delay_sec=0.0)
                if tail:
                    time.sleep(settings.backspace_settle_sec)

            if tail:
                write_delay = settings.write_delay_sec if write_delay_override is None else write_delay_override
                send_text(tail, delay_per_char=write_delay)

            self.last_text = new_text

    def _deactivate_ime(self, reason: str = "") -> None:
        if not self.ime_enabled:
            return
        if reason:
            log("IME deactivate key pressed:", reason, "-> IME OFF")
        if reason == (settings.ime_activate_key or "").strip().lower():
            self._last_deactivate_by_activate_key = time.time()
        self.core.reset()
        self.last_text = ""
        self.ime_enabled = False

    def run(self) -> None:
        deactivate_key_names, deactivate_mouse_names, activate_key, toggle_key = self._parse_deactivate_config()
        ime_off_block_keys = self._parse_ime_off_block_keys(activate_key)

        def decision_callback() -> tuple[bool, bool]:
            return self._is_target_window(), self.ime_enabled

        self._ll_stop, _ = win32_ll_hook.start_ll_hook(
            settings.intercept_letters,
            settings.intercept_punctuations,
            decision_callback,
            self._handle_hook_event,
            deactivate_key_names,
            deactivate_mouse_names,
            activate_key,
            toggle_key,
            ime_off_block_keys,
        )

        log("LL hook started")
        threading.Event().wait()

