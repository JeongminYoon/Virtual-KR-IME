from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .logger import log


# 한글 자모 테이블 (유니코드 조합 순서)
CHOSUNG_LIST = [
    "ㄱ",
    "ㄲ",
    "ㄴ",
    "ㄷ",
    "ㄸ",
    "ㄹ",
    "ㅁ",
    "ㅂ",
    "ㅃ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅉ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]

JUNGSUNG_LIST = [
    "ㅏ",
    "ㅐ",
    "ㅑ",
    "ㅒ",
    "ㅓ",
    "ㅔ",
    "ㅕ",
    "ㅖ",
    "ㅗ",
    "ㅘ",
    "ㅙ",
    "ㅚ",
    "ㅛ",
    "ㅜ",
    "ㅝ",
    "ㅞ",
    "ㅟ",
    "ㅠ",
    "ㅡ",
    "ㅢ",
    "ㅣ",
]

JONGSUNG_LIST = [
    "",  # 종성 없음
    "ㄱ",
    "ㄲ",
    "ㄳ",
    "ㄴ",
    "ㄵ",
    "ㄶ",
    "ㄷ",
    "ㄹ",
    "ㄺ",
    "ㄻ",
    "ㄼ",
    "ㄽ",
    "ㄾ",
    "ㄿ",
    "ㅀ",
    "ㅁ",
    "ㅂ",
    "ㅄ",
    "ㅅ",
    "ㅆ",
    "ㅇ",
    "ㅈ",
    "ㅊ",
    "ㅋ",
    "ㅌ",
    "ㅍ",
    "ㅎ",
]


# 두벌식 키보드: 알파벳 → 자모 매핑 (기본형만, 복잡한 예외는 이후 확장)
KEY_TO_JAMO = {
    "q": "ㅂ",
    "w": "ㅈ",
    "e": "ㄷ",
    "r": "ㄱ",
    "t": "ㅅ",
    "y": "ㅛ",
    "u": "ㅕ",
    "i": "ㅑ",
    "o": "ㅐ",
    "p": "ㅔ",
    "a": "ㅁ",
    "s": "ㄴ",
    "d": "ㅇ",
    "f": "ㄹ",
    "g": "ㅎ",
    "h": "ㅗ",
    "j": "ㅓ",
    "k": "ㅏ",
    "l": "ㅣ",
    "z": "ㅋ",
    "x": "ㅌ",
    "c": "ㅊ",
    "v": "ㅍ",
    "b": "ㅠ",
    "n": "ㅜ",
    "m": "ㅡ",
}

# Shift가 눌린 상태에서 초성으로 사용할 때의 쌍자음 매핑
DOUBLE_CHOSUNG = {
    "ㄱ": "ㄲ",
    "ㄷ": "ㄸ",
    "ㅂ": "ㅃ",
    "ㅅ": "ㅆ",
    "ㅈ": "ㅉ",
}

# 복모음 조합 규칙: (기존 중성, 새 중성) -> 결합 중성
COMPOSED_VOWELS = {
    ("ㅗ", "ㅏ"): "ㅘ",
    ("ㅗ", "ㅐ"): "ㅙ",
    ("ㅗ", "ㅣ"): "ㅚ",
    ("ㅜ", "ㅓ"): "ㅝ",
    ("ㅜ", "ㅔ"): "ㅞ",
    ("ㅜ", "ㅣ"): "ㅟ",
    ("ㅡ", "ㅣ"): "ㅢ",
}

# 겹받침 조합 규칙: (기존 종성, 새 자음) -> 겹받침 종성
COMPOSED_JONGSUNG = {
    ("ㄱ", "ㅅ"): "ㄳ",
    ("ㄴ", "ㅈ"): "ㄵ",
    ("ㄴ", "ㅎ"): "ㄶ",
    ("ㄹ", "ㄱ"): "ㄺ",
    ("ㄹ", "ㅁ"): "ㄻ",
    ("ㄹ", "ㅂ"): "ㄼ",
    ("ㄹ", "ㅅ"): "ㄽ",
    ("ㄹ", "ㅌ"): "ㄾ",
    ("ㄹ", "ㅍ"): "ㄿ",
    ("ㄹ", "ㅎ"): "ㅀ",
    ("ㅂ", "ㅅ"): "ㅄ",
}

# 겹받침 분해 규칙: 겹받침 종성 -> (앞 종성, 뒤 자음)
DECOMPOSED_JONGSUNG = {
    "ㄳ": ("ㄱ", "ㅅ"),
    "ㄵ": ("ㄴ", "ㅈ"),
    "ㄶ": ("ㄴ", "ㅎ"),
    "ㄺ": ("ㄹ", "ㄱ"),
    "ㄻ": ("ㄹ", "ㅁ"),
    "ㄼ": ("ㄹ", "ㅂ"),
    "ㄽ": ("ㄹ", "ㅅ"),
    "ㄾ": ("ㄹ", "ㅌ"),
    "ㄿ": ("ㄹ", "ㅍ"),
    "ㅀ": ("ㄹ", "ㅎ"),
    "ㅄ": ("ㅂ", "ㅅ"),
}


def _compose_syllable(chosung: str, jungsung: str, jongsung: str = "") -> str:
    """초성/중성/종성으로부터 완성형 한글 음절을 생성."""
    try:
        ci = CHOSUNG_LIST.index(chosung)
        vi = JUNGSUNG_LIST.index(jungsung)
        ti = JONGSUNG_LIST.index(jongsung)
    except ValueError:
        # 조합이 잘못된 경우에는 그대로 자모를 이어붙여 반환하도록 상위에서 처리
        log("Invalid jamo combination:", chosung, jungsung, jongsung)
        return chosung + jungsung + jongsung

    code = 0xAC00 + (ci * 21 * 28) + (vi * 28) + ti
    return chr(code)


@dataclass
class HangulState:
    """현재 조합 중인 한글 음절 상태."""

    chosung: Optional[str] = None
    jungsung: Optional[str] = None
    jongsung: Optional[str] = None

    def to_char(self) -> str:
        if self.chosung and self.jungsung:
            return _compose_syllable(self.chosung, self.jungsung, self.jongsung or "")
        if self.chosung:
            return self.chosung
        if self.jungsung:
            return self.jungsung
        return ""

    def is_empty(self) -> bool:
        return not (self.chosung or self.jungsung or self.jongsung)


@dataclass(frozen=True)
class HangulRenderState:
    """화면 반영용 스냅샷. 확정 글자와 조합 중 글자를 분리해 보관한다."""

    committed_text: str = ""
    current_text: str = ""

    @property
    def text(self) -> str:
        return self.committed_text + self.current_text


@dataclass
class HangulIMECore:
    """간단한 두벌식 한글 IME 핵심 로직.

    - feed_key: 알파벳 키 입력을 받아 내부 상태를 갱신하고 전체 출력 문자열을 반환.
    - handle_backspace: 마지막 자모/음절을 지우고 전체 출력 문자열을 반환.
    """

    committed: List[str] = field(default_factory=list)
    current: HangulState = field(default_factory=HangulState)

    def reset(self) -> None:
        self.committed.clear()
        self.current = HangulState()
        log("HangulIMECore reset")

    @property
    def text(self) -> str:
        return self.render_state.text

    @property
    def render_state(self) -> HangulRenderState:
        return HangulRenderState(
            committed_text="".join(self.committed),
            current_text=self.current.to_char(),
        )

    def feed_text(self, text: str, as_english: bool = False) -> str:
        """여러 글자를 연속으로 입력했을 때의 결과 문자열을 반환."""
        for ch in text:
            self.feed_key(ch, shifted=False, as_english=as_english)
        return self.text

    def feed_key(self, key: str, shifted: bool = False, as_english: bool = False) -> str:
        """알파벳 키 하나를 입력받아 조합 상태를 갱신하고 전체 문자열을 반환."""
        if as_english:
            # 현재 한글 조합이 있다면 먼저 확정하고, 영문자는 그대로 붙인다. Shift면 대문자.
            self._commit_current_if_exists()
            ch = key.upper() if shifted else key
            self.committed.append(ch)
            log("English key appended:", ch, "->", self.text)
            return self.text

        key = key.lower()
        if key not in KEY_TO_JAMO:
            # 지원하지 않는 키는 그대로 커밋된 문자열 뒤에 영문자로 붙인다.
            self._commit_current_if_exists()
            self.committed.append(key)
            log("Non-hangul key, appended as is:", key, "->", self.text)
            return self.text

        jamo = KEY_TO_JAMO[key]

        # Shift가 눌린 상태에서 모음 쌍모음(ㅒ, ㅖ) 처리 (예: Shift+O/P)
        if shifted and key == "o" and jamo == "ㅐ":
            jamo = "ㅒ"
        elif shifted and key == "p" and jamo == "ㅔ":
            jamo = "ㅖ"

        # Shift가 눌린 상태에서는 자음을 쌍자음 자모로 승격
        if shifted and jamo in DOUBLE_CHOSUNG:
            jamo = DOUBLE_CHOSUNG[jamo]

        log("feed_key:", key, "=>", jamo, "(shifted)" if shifted else "")

        # 매우 단순화된 두벌식 로직:
        # - 자음이 먼저 오면 초성, 그다음 모음이 오면 중성, 그 뒤 자음은 종성으로 취급.
        # - 종성이 있는 상태에서 모음이 들어오면, 이전 글자를 커밋하고 새 글자를 시작.
        if jamo in CHOSUNG_LIST or jamo in ["ㄱ", "ㄴ", "ㄷ", "ㄹ", "ㅁ", "ㅂ", "ㅅ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"]:
            self._handle_consonant(jamo)
        else:
            self._handle_vowel(jamo)

        log("current text:", self.text)
        return self.text

    def _handle_consonant(self, jamo: str) -> None:
        st = self.current
        if st.is_empty():
            # 새 초성 시작
            st.chosung = jamo
            return

        if st.chosung and not st.jungsung:
            # 초성만 있는 상태에서 다른 자음이 오면, 이전 초성을 커밋하고 새 초성 시작
            self._commit_current_if_exists()
            self.current.chosung = jamo
            return

        if st.chosung and st.jungsung and not st.jongsung:
            # 초성+중성 상태에서 자음이 올 때 처리
            # 1) 받침용 쌍자음(ㅆ): 그대로 종성으로 사용 (예: 갔)
            if jamo == "ㅆ":
                st.jongsung = jamo
                return
            # 2) 초성용 쌍자음(ㄲ, ㄸ, ㅃ, ㅉ 등): 이전 음절을 확정하고 새 음절의 초성으로 사용 (예: 쪼까)
            if jamo in ("ㄲ", "ㄸ", "ㅃ", "ㅉ"):
                self._commit_current_if_exists()
                self.current.chosung = jamo
                return
            # 3) 그 외 일반 자음은 종성으로 붙인다.
            st.jongsung = jamo
            return

        if st.chosung and st.jungsung and st.jongsung:
            # 이미 종성이 있는 상태에서 또 자음이 오면,
            # 1) 겹받침으로 결합 가능한 경우: 종성을 겹받침으로 교체
            if (st.jongsung, jamo) in COMPOSED_JONGSUNG:
                st.jongsung = COMPOSED_JONGSUNG[(st.jongsung, jamo)]
                return
            # 2) 그렇지 않으면 이전 음절을 확정하고 새 초성으로 시작
            self._commit_current_if_exists()
            self.current.chosung = jamo
            return

        if st.chosung and st.jungsung and st.jongsung:
            # 이미 종성이 있는 상태에서 또 자음이 오면:
            # 이전 음절을 확정(커밋)하고, 새 초성으로 시작
            self._commit_current_if_exists()
            self.current.chosung = jamo
            return

        # 그 외 예외적인 상황은 현재 글자를 커밋하고 새로 시작
        self._commit_current_if_exists()
        self.current.chosung = jamo

    def _handle_vowel(self, jamo: str) -> None:
        st = self.current
        if st.is_empty():
            # 모음만 먼저 온 경우: 중성만 가진 상태로 시작
            st.jungsung = jamo
            return

        if st.chosung and not st.jungsung:
            # 초성만 있는 상태에서 모음이 오면 중성으로 설정
            st.jungsung = jamo
            return

        if st.chosung and st.jungsung and not st.jongsung:
            # 이미 초성+중성이 있고 또 모음이 올 때
            # 1) 복모음으로 결합 가능한 경우: 중성만 교체
            if (st.jungsung, jamo) in COMPOSED_VOWELS:
                st.jungsung = COMPOSED_VOWELS[(st.jungsung, jamo)]
                return
            # 2) 그렇지 않으면 이전 음절을 커밋하고 새 중성으로 시작
            self._commit_current_if_exists()
            self.current.jungsung = jamo
            return

        if st.chosung and st.jungsung and st.jongsung:
            # 종성이 있는 상태에서 모음이 오면,
            # 종성을 다음 음절의 초성으로 넘기는 규칙 적용
            prev_chosung = st.chosung
            prev_jungsung = st.jungsung
            prev_jongsung = st.jongsung

            # 겹받침인 경우: 앞 자모는 이전 음절의 종성으로 남기고,
            # 뒤 자모를 다음 음절의 초성으로 넘긴다.
            if prev_jongsung in DECOMPOSED_JONGSUNG:
                first_jong, next_cho = DECOMPOSED_JONGSUNG[prev_jongsung]
                committed_char = _compose_syllable(prev_chosung, prev_jungsung, first_jong)
                self.committed.append(committed_char)
                self.current = HangulState(chosung=next_cho, jungsung=jamo, jongsung=None)
                return

            # 단일 종성인 경우: 이전 음절은 종성 없이 확정하고,
            # 종성 전체를 다음 음절의 초성으로 넘긴다.
            committed_char = _compose_syllable(prev_chosung, prev_jungsung, "")
            self.committed.append(committed_char)
            self.current = HangulState(chosung=prev_jongsung, jungsung=jamo, jongsung=None)
            return

        # 기타: 모음만 있는 상태 등
        self._commit_current_if_exists()
        self.current.jungsung = jamo

    def _commit_current_if_exists(self) -> None:
        ch = self.current.to_char()
        if ch:
            self.committed.append(ch)
        self.current = HangulState()

    def handle_backspace(self) -> str:
        """마지막 자모/음절을 지운 뒤 전체 문자열을 반환."""
        st = self.current
        if not st.is_empty():
            # 완성된 한 글자(초성+중성, 선택적 종성)가 있는 경우
            # 게임/채팅 UX를 위해 한 번의 백스페이스로 전체 글자를 지운다.
            if st.chosung and st.jungsung:
                st.chosung = None
                st.jungsung = None
                st.jongsung = None
            else:
                # 그 외 (부분 조합 중)에는 자모를 하나씩 제거
                if st.jongsung:
                    st.jongsung = None
                elif st.jungsung:
                    st.jungsung = None
                elif st.chosung:
                    st.chosung = None
            log("Backspace on current syllable ->", self.text)
            return self.text

        # 현재 조합이 없다면, 커밋된 문자열에서 마지막 음절 제거
        if self.committed:
            removed = self.committed.pop()
            log("Backspace removed committed:", removed, "->", self.text)
            return self.text

        log("Backspace on empty buffer")
        return self.text

    def handle_space(self) -> str:
        """현재 조합을 확정하고, 공백을 하나 추가한 뒤 전체 문자열을 반환."""
        # 현재 조합 중인 글자를 확정
        self._commit_current_if_exists()
        # 공백도 버퍼에 포함해, 이후 백스페이스로 함께 지울 수 있게 한다.
        self.committed.append(" ")
        log("Space committed ->", repr(self.text))
        return self.text

