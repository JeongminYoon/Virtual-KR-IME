from .keyboard_hook import KeyboardManager
from .logger import log


def main() -> None:
    log("Virtual Hangul IME starting...")
    log("Open your game chat box, then type in English while the mode is ON.")
    manager = KeyboardManager()
    manager.run()


if __name__ == "__main__":
    main()

