import sys
from datetime import datetime

from .config import settings


def log(*args: object) -> None:
    """간단한 디버그 로깅 함수."""
    if not settings.debug:
        return
    ts = datetime.now().strftime("%H:%M:%S")
    text = " ".join(str(a) for a in args)
    sys.stdout.write(f"[{ts}] {text}\n")
    sys.stdout.flush()

