from dataclasses import dataclass


@dataclass
class Settings:
    """프로그램 전역 설정 값."""

    # 채팅창 열었을 때 IME 켜기 전용 키 (예: enter)
    ime_activate_key: str = "enter"

    # IME 끄기 전용 키. 쉼표로 여러 개 지정 가능. 눌리면 조합 확정/취소 후 IME OFF, 키는 게임으로 전달 (예: enter, esc, mouse left)
    ime_deactivate_keys: str = "enter, esc, mouse left, mouse right"

    # IME 켜진 상태에서 한글↔영어 서브모드 전환 키 (예: 한/영 키 → right alt)
    language_toggle_key: str = "right alt"

    # IME 끄기 후 다시 켤 때 이전 서브모드(한글/영어)를 기억할지 여부
    remember_submode: bool = True
    # IME 켰을 때 시작 서브모드 (remember_submode가 False일 때 사용). "korean" 또는 "english"
    default_submode: str = "english"

    # 한글 입력 시 가로챌 키 범위 (영문자/숫자 등)
    intercept_letters: str = "abcdefghijklmnopqrstuvwxyz0123456789"

    # 한글 모드에서 함께 관리할 특수문자 (예: ! ? . , 등)
    intercept_punctuations: str = "!?.,:;'-\""

    # 디버그 모드: 콘솔에 내부 상태를 출력할지 여부
    debug: bool = True

    # 게임 채팅창 호환: 글자와 글자 사이 지연(초). 0이면 지연 없음. 게임에서 한 글자만 남으면 0.05~0.08 로 올려보기.
    inject_delay_sec: float = 0.025
    # 백스페이스 보낸 뒤, 새 글자 보내기 전 대기(초). 게임이 백스페이스 처리할 시간을 줌.
    inject_delay_after_backspaces_sec: float = 0.025

    # IME가 동작할 대상 윈도우 제목 키워드(쉼표 구분). 비워두면 전체에서 동작.
    # 예: "lost ark,lostark,gameclient"
    target_window_keywords: str = "HELLDIVERS™ 2"


settings = Settings()

