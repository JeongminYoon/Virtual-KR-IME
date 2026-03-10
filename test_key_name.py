import keyboard


def on_event(e: keyboard.KeyboardEvent) -> None:
    print(
        f"event: name={e.name!r}, scan_code={e.scan_code}, is_keypad={e.is_keypad}"
    )


def main() -> None:
    print("아무 키나 눌러보세요. (종료: ESC)")
    keyboard.hook(on_event)
    keyboard.wait("esc")


if __name__ == "__main__":
    main()

