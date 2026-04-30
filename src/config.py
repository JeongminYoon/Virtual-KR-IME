from dataclasses import dataclass


@dataclass
class Settings:
    """프로그램 전역 설정 값."""

    ime_activate_key: str = "enter"
    ime_deactivate_keys: str = "enter, esc, mouse left, mouse right"
    language_toggle_key: str = "right alt"
    # IME가 꺼진 상태에서만, 대상 창 포커스일 때(키워드 비우면 전역) 아래 키를 게임에 넘기지 않음.
    # ime_activate_key에 쓰인 키는 자동 제외(채팅 열기 등). 쉼표 구분, 이름은 ime_deactivate_keys와 동일 규칙(예: escape→esc).
    ime_off_block_keys: str = "right alt"

    intercept_letters: str = "abcdefghijklmnopqrstuvwxyz0123456789"
    intercept_punctuations: str = "!@#$%^&*()_+-=[]{}\\|;:'\",.<>/?`~"
    # 게임 채팅용 지연 추천값.
    # - 30 FPS: backspace_settle_sec=0.045, write_delay_sec=0.03
    # - 60 FPS: backspace_settle_sec=0.03, write_delay_sec=0.015
    # - 100+ FPS: backspace_settle_sec=0.02, write_delay_sec=0.01
    # 중복 글자(예: 과과, 이이)가 보이면 backspace_settle_sec를 먼저 올리고,
    # 입력이 느리거나 씹히면 write_delay_sec를 조금씩 조정한다.
    backspace_settle_sec: float = 0.045
    write_delay_sec: float = 0.03
    paste_chunk_size: int = 8
    target_window_keywords: str = "HELLDIVERS™ 2"
    debug: bool = True


settings = Settings()

