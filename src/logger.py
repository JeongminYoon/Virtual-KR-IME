import sys
from datetime import datetime

from .config import settings


def _write(prefix: str, *args: object) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    text = " ".join(str(a) for a in args)
    sys.stdout.write(f"[{ts}] {prefix}{text}\n")
    sys.stdout.flush()


def log(*args: object) -> None:
    """간단한 디버그 로깅 함수."""
    if not settings.debug:
        return
    _write("", *args)


def warn(*args: object) -> None:
    """debug 설정과 무관하게 사용자에게 보여야 하는 경고."""
    _write("WARNING: ", *args)

