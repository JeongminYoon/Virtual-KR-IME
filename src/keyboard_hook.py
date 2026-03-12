"""
전역 키 후킹 및 가상 한글 모드 제어.

Windows Low-Level 훅(WH_KEYBOARD_LL)으로 대상 창 포커스 시에만:
- IME 켜기/끄기/한·영 토글: Enter, Esc, 한/영 키 등 (동시입력 시에도 누락 없음)
- 글자/스페이스/백스페이스: 가로채서 HangulIMECore로 처리 후 SendInput으로 전송
"""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
import ctypes
from typing import Callable

import keyboard

from .config import settings
from .hangul_ime_core import HangulIMECore, HangulRenderState
from .injector_windows import send_backspaces as _lowlevel_send_backspaces, send_text
from .logger import log
from . import win32_ll_hook


@dataclass(frozen=True)
class RenderRequest:
    epoch: int
    state: HangulRenderState
    force_current: bool = False


class KeyboardManager:
    def __init__(self) -> None:
        self.ime_enabled: bool = False
        self.korean_mode: bool = False  # IME 내 한/영 서브모드. IME 끄기 후에도 유지
        self.core = HangulIMECore()
        self.last_text: str = ""
        self.last_render_state = HangulRenderState()
        self._render_epoch: int = 0
        self._last_deactivate_by_activate_key: float = 0.0  # 같은 키로 끄기 직후 켜기 무시용
        self._update_queue: queue.Queue[RenderRequest] = queue.Queue()
        self._update_worker = threading.Thread(target=self._run_update_worker, daemon=True)
        self._update_worker.start()
        self._ll_key_queue: queue.Queue[tuple[str | None, bool]] = queue.Queue()
        self._ll_stop: Callable[[], None] | None = None
        self._ll_consumer_thread: threading.Thread | None = None
        self._update_screen_lock = threading.Lock()

    def _clear_update_queue(self) -> None:
        try:
            while True:
                self._update_queue.get_nowait()
        except queue.Empty:
            pass

    def _queue_render_update(self, *, force_current: bool = False) -> None:
        self._update_queue.put(
            RenderRequest(self._render_epoch, self.core.render_state, force_current=force_current)
        )

    def _render_state(self, state: HangulRenderState, *, include_current: bool) -> None:
        target_state = state if include_current else HangulRenderState(state.committed_text, "")
        self._update_screen(target_state.text)
        self.last_render_state = target_state

    def _run_update_worker(self) -> None:
        pending: RenderRequest | None = None
        pending_since = 0.0

        while True:
            timeout = 0.25
            if pending is not None and self.ime_enabled:
                elapsed = time.monotonic() - pending_since
                timeout = max(0.0, settings.composition_update_delay_sec - elapsed)

            try:
                request = self._update_queue.get(timeout=timeout)
            except queue.Empty:
                if pending is None or not self.ime_enabled:
                    if not self.ime_enabled:
                        pending = None
                    continue
                if pending.epoch != self._render_epoch:
                    pending = None
                    continue
                self._render_state(pending.state, include_current=True)
                pending = None
                continue

            if not self.ime_enabled or request.epoch != self._render_epoch:
                pending = None
                continue

            pending = request
            pending_since = time.monotonic()

            if request.force_current:
                self._render_state(request.state, include_current=True)
                pending = None
                continue

            if request.state.committed_text != self.last_render_state.committed_text:
                # 확정 글자는 가능한 빨리 반영하고, 조합 중 글자는 잠시 모아 뭉쳐서 보낸다.
                self._render_state(request.state, include_current=False)
                if not request.state.current_text:
                    pending = None

    # ---------- 활성 윈도우 필터링 ----------
    def _is_target_window(self) -> bool:
        """설정된 윈도우 제목 키워드에 해당하는 활성 창에서만 IME 동작."""
        raw = (settings.target_window_keywords or "").strip()
        if not raw:
            return True  # 키워드가 비어 있으면 전체에서 동작

        keywords = [
            k.strip().lower() for k in raw.split(",") if k.strip()
        ]
        if not keywords:
            return True

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        buf = ctypes.create_unicode_buffer(256)
        length = user32.GetWindowTextW(hwnd, buf, 256)
        if length == 0:
            return False
        title = buf.value.lower()
        return any(kw in title for kw in keywords)

    def _parse_deactivate_config(self) -> tuple[list[str], set[str], set[str], str, str]:
        """ime_deactivate_keys와 키보드/마우스 종료 집합, activate_key, toggle_key 반환."""
        raw = (settings.ime_deactivate_keys or "").strip()
        deactivate_keys = [k.strip().lower() for k in raw.split(",") if k.strip()]
        mouse_keys = ("mouse left", "mouse right")
        key_names = {"esc" if k == "escape" else k for k in deactivate_keys if k not in mouse_keys}
        mouse_names = {k for k in deactivate_keys if k in mouse_keys}
        activate = (settings.ime_activate_key or "").strip().lower()
        toggle = (settings.language_toggle_key or "").strip().lower()
        return deactivate_keys, key_names, mouse_names, activate, toggle

    # ---------- IME 켜기/끄기 ----------
    def activate_ime(self) -> None:
        """IME 켜기/끄기 토글.

        - ime_activate_key만으로도 플로우 2(켜기=Enter, 끄기=Enter)를 지원하기 위해,
          활성/비활성 상태와 설정을 보고 동작을 나눈다.
        """
        if not self._is_target_window():
            return

        deactivate_keys, _, _, activate_key, _ = self._parse_deactivate_config()

        if self.ime_enabled:
            # 이미 켜져 있을 때 ime_activate_key가 deactivate 목록에도 있으면 "끄기" 동작으로 처리
            if activate_key in deactivate_keys:
                log("IME activate key pressed while ON -> treated as deactivate")
                self._deactivate_ime(reason=activate_key)
            return

        # 훅에서 같은 키(Enter)로 끈 직후(~150ms) 전역 hotkey가 켜기를 호출하는 경우만 무시
        if self._last_deactivate_by_activate_key > 0:
            if time.time() - self._last_deactivate_by_activate_key < 0.08:
                return
            self._last_deactivate_by_activate_key = 0.0

        # IME가 꺼져 있을 때는 "켜기" 동작
        if not settings.remember_submode:
            self.korean_mode = (
                (settings.default_submode or "").strip().lower() == "korean"
            )
        self.ime_enabled = True
        log("Virtual Hangul IME ON (" + ("Korean" if self.korean_mode else "English") + " mode)")
        self._render_epoch += 1
        self._clear_update_queue()
        self.core.reset()
        self.last_text = ""
        self.last_render_state = HangulRenderState()

    def toggle_language_mode(self) -> None:
        """IME 켜진 상태에서만 한글↔영어 서브 모드 전환."""
        if not self._is_target_window():
            return
        if not self.ime_enabled:
            return
        self.korean_mode = not self.korean_mode
        log("Language mode:", "Korean" if self.korean_mode else "English")

    def _run_ll_consumer(self) -> None:
        while True:
            try:
                item = self._ll_key_queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item[0] is None:
                break
            self._process_ll_key(item[0], item[1])

    def _process_ll_key(self, key_name: str, shifted: bool) -> None:
        """LL 훅에서 넣은 키/제어 이벤트(활성·끄기·토글·글자) 처리."""
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
        if key_name == "backspace":
            if not self.core.text:
                keyboard.send("backspace")
                return
            self.core.handle_backspace()
            self._queue_render_update(force_current=True)
            return
        if key_name == " ":
            self.core.handle_space()
            self._queue_render_update(force_current=True)
            return
        if len(key_name) != 1:
            return
        if key_name in settings.intercept_punctuations:
            self.core.feed_key(key_name, shifted=False)
        else:
            if self.korean_mode:
                self.core.feed_key(key_name, shifted=shifted, as_english=False)
            else:
                self.core.feed_key(key_name, shifted=shifted, as_english=True)
        self._queue_render_update(force_current=False)

    # ---------- 이벤트 핸들러 ----------
    def _send_backspaces_safely(self, n: int) -> None:
        """백스페이스 전송. LL 훅은 LLKHF_INJECTED로 우리가 보낸 키는 통과시킴."""
        if n <= 0:
            return
        if not self._is_target_window():
            return
        _lowlevel_send_backspaces(n, delay_sec=settings.inject_delay_sec)

    def _update_screen(self, new_text: str) -> None:
        with self._update_screen_lock:
            prev = self.last_text
            curr = new_text

            if prev == curr:
                return

            common_len = 0
            for a, b in zip(prev, curr):
                if a != b:
                    break
                common_len += 1

            backs = len(prev) - common_len
            if backs > 0:
                self._send_backspaces_safely(backs)
                if settings.inject_delay_after_backspaces_sec > 0:
                    time.sleep(settings.inject_delay_after_backspaces_sec)

            tail = curr[common_len:]
            if tail:
                send_text(tail, delay_per_char=settings.inject_delay_sec)

            self.last_text = curr
            if backs > 0 or tail:
                time.sleep(0.02)

    def _deactivate_ime(self, reason: str = "") -> None:
        if not self.ime_enabled:
            return
        if reason:
            log("IME deactivate key pressed:", reason, "-> IME OFF")
        activate_key = (settings.ime_activate_key or "").strip().lower()
        if reason == activate_key:
            self._last_deactivate_by_activate_key = time.time()
        # 조합 중 글자가 아직 지연 반영 대기 중일 수 있으므로, IME 종료 전 최종 상태를 먼저 밀어넣는다.
        self._render_state(self.core.render_state, include_current=True)
        self._render_epoch += 1
        self._clear_update_queue()
        self.core.reset()
        self.last_text = ""
        self.last_render_state = HangulRenderState()
        self.ime_enabled = False

    # ---------- 실행 ----------
    def run(self) -> None:
        _, deactivate_key_names, deactivate_mouse_names, activate_key, toggle_key = self._parse_deactivate_config()

        def decision_callback() -> tuple[bool, bool]:
            return (self._is_target_window(), self.ime_enabled)

        self._ll_stop, _ = win32_ll_hook.start_ll_hook(
            settings.intercept_letters,
            settings.intercept_punctuations,
            decision_callback,
            self._ll_key_queue,
            deactivate_key_names,
            deactivate_mouse_names,
            activate_key,
            toggle_key,
        )
        self._ll_consumer_thread = threading.Thread(target=self._run_ll_consumer, daemon=True)
        self._ll_consumer_thread.start()

        log("LL hook started (activate/toggle/deactivate + letters when IME ON)")
        threading.Event().wait()

