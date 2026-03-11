# Virtual-KR-IME

게임 채팅창 등 **한글 IME 미지원 환경**에서 영문 키를 **두벌식 한글**로 바꿔 넣어 주는 **Windows용 가상 한글 입력기**입니다.

---

## 프로젝트 소개 및 작동 원리

많은 게임은 채팅창에서 Windows IME(한글 입력기)를 지원하지 않아, 영문만 입력되거나 한글 조합이 깨집니다. 이 프로그램은 **전역 Low-Level 키보드 훅**으로 입력을 가로채고, **두벌식 규칙**으로 한글을 조합한 뒤 **유니코드 입력 주입**으로 채팅창에 직접 넣어 줍니다.

### 작동 방식 요약

1. **대상 창에서만 동작**  
   설정한 윈도우 제목 키워드(예: 게임명)에 해당하는 창이 활성일 때만 IME가 켜지고, 그 외에는 키 입력을 그대로 통과시킵니다.

2. **IME 켜기/끄기**  
   - **켜기**: 채팅창을 연 뒤 설정한 **활성 키**(기본: `Enter`)를 누르면 가상 한글 모드 ON.  
   - **끄기**: **끄기 키**(기본: `Enter`, `Esc`, 마우스 좌/우클릭 등)를 누르면 조합을 확정/취소하고 IME OFF, 해당 키는 게임으로 전달됩니다.

3. **한글/영문 서브 모드**  
   IME가 켜진 상태에서 **한/영 전환 키**(기본: `Right Alt`)로 한글 입력 ↔ 영문 직접 입력을 전환할 수 있습니다.

4. **입력 처리 흐름**  
   - IME ON + 대상 창 포커스일 때: 영문자·숫자·일부 특수문자 키를 **가로채서** 두벌식 한글 엔진에 넘깁니다.  
   - 엔진이 초성/중성/종성을 조합해 완성형 한글(또는 영문) 문자열을 만들고,  
   - **백스페이스**로 기존 표시를 지운 뒤 **SendInput(KEYEVENTF_UNICODE)** 로 새 문자열을 한 글자씩 주입합니다.  
   - 따라서 채팅창에는 “한글 조합 결과”만 보이고, 게임은 키보드 입력이 아닌 유니코드 문자 입력으로 인식합니다.

---

## 코드 플로우

```
main.py
  └─ KeyboardManager().run()
       │
       ├─ win32_ll_hook.start_ll_hook()
       │     • WH_KEYBOARD_LL 전역 훅 스레드
       │     • 키 다운 시: 활성/끄기/토글/글자/백스페이스/스페이스 판별
       │     • 활성 키(예: Enter) 직후에도 빠른 타이핑이 누락되지 않도록, 훅 단계에서 "IME ON 예정"을 즉시 반영
       │     • 대상 창 + (IME ON 또는 ON 예정)일 때만 글자류 가로채기 → key_queue에 (key_name, shifted) 넣음
       │     • 우리가 보낸 키(SendInput)는 LLKHF_INJECTED로 통과
       │
       ├─ _run_ll_consumer() 스레드
       │     • key_queue에서 꺼내서 _process_ll_key() 호출
       │     • __activate__ → activate_ime()
       │     • __deactivate__:... → _deactivate_ime(), keyboard.send(reason)
       │     • __toggle__ → toggle_language_mode()
       │     • backspace / space / 한 글자 → HangulIMECore 처리 후 _update_queue.put(RenderRequest)
       │
       ├─ _run_update_worker() 스레드
       │     • _update_queue에서 RenderRequest 수신 (HangulRenderState: committed/current 분리)
       │     • 확정(committed) 글자는 즉시 반영, 조합 중(current) 글자는 composition_update_delay_sec 동안 배치 후 반영
       │     • _update_screen(text): last_text와 diff 계산 → 공통 접두사 이후만 백스페이스 N회 + send_text(꼬리)
       │
       ├─ HangulIMECore (hangul_ime_core.py)
       │     • 두벌식 자모 테이블(KEY_TO_JAMO, 쌍자음/복모음/겹받침)
       │     • feed_key() → 초성/중성/종성 조합, commit 시 완성형 음절 생성
       │     • handle_backspace() / handle_space() → 조합 취소 또는 공백 확정
       │
       └─ injector_windows
             • send_text(문자열): 유니코드 문자별 KEYEVENTF_UNICODE SendInput
             • send_backspaces(n): VK_BACK 키 다운/업 n회
```

### 주요 파일

| 파일 | 역할 |
|------|------|
| `src/main.py` | 진입점, `KeyboardManager` 생성 및 `run()` |
| `src/keyboard_hook.py` | 훅 이벤트 수신·분기, IME 켜기/끄기/토글, `HangulIMECore` 호출, 화면 갱신 큐 처리 |
| `src/win32_ll_hook.py` | Windows `WH_KEYBOARD_LL` 훅, VK→키이름 변환, 대상 창·IME 상태에 따른 가로채기/통과 |
| `src/hangul_ime_core.py` | 두벌식 자모 매핑 및 초/중/종성 조합, 백스페이스·스페이스 처리 |
| `src/injector_windows.py` | `SendInput`으로 유니코드 문자 입력 및 백스페이스 주입 |
| `src/config.py` | 활성/끄기/토글 키, 대상 창 키워드, 주입 지연 등 설정 |

---

## 빌드 파일 사용법 (릴리즈 ZIP)

GitHub **Releases**에 올려 둔 ZIP 파일을 사용하는 방법입니다.

### 1. 다운로드 및 압축 해제

- Releases 페이지에서 최신 **Virtual_KR_IME_xxx.zip** (또는 동일한 이름의 배포용 ZIP)을 다운로드합니다.
- 원하는 폴더에 압축을 해제합니다.

### 2. 실행

- 압축 해제된 폴더 안에 있는 **`run.bat`** 을 더블클릭하여 실행합니다.
- 콘솔 창이 뜨면 “Virtual Hangul IME starting...” 메시지와 함께 가상 한글 IME가 동작합니다.

### 3. 사용 순서

1. 게임을 켠 뒤 채팅창을 엽니다.
2. **IME 활성 키**(기본: `Enter`)를 눌러 가상 한글 모드를 켭니다.
3. 영문 자판으로 한글을 입력합니다 (두벌식).
4. **IME 끄기 키**(기본: `Enter`, `Esc`, 마우스 클릭 등)를 누르면 한글 모드가 꺼지고, 해당 키는 게임으로 전달됩니다.

### 4. 설정 변경

- 폴더 안의 **`src\config.py`** 를 메모장 등으로 열어 수정할 수 있습니다.
  - **대상 게임 창 제목 키워드**: `target_window_keywords` (쉼표 구분). 비우면 모든 창에서 동작.
  - **IME 켜기 키**: `ime_activate_key` (기본 `enter`)
  - **IME 끄기 키**: `ime_deactivate_keys` (예: `enter, esc, mouse left, mouse right`)
  - **한/영 전환 키**: `language_toggle_key` (기본 `right alt`)
  - 게임에 따라 **`inject_delay_sec`**, **`inject_delay_after_backspaces_sec`** 를 조금 올리면 입력이 더 안정될 수 있습니다.
  - 저FPS/채팅 처리 지연이 큰 게임이라면 **`composition_update_delay_sec`** 를 올려 "조합 중 글자 갱신" 빈도를 줄이면 누락이 줄어들 수 있습니다.

### 5. 주의사항

- **관리자 권한**이 필요할 수 있습니다 (전역 키보드 훅 사용 시).
- 일부 게임/안티치트는 입력 도구 사용을 제한할 수 있으므로, 이용 규정을 확인해 사용하세요.

---

## 개발 환경에서 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 실행
python -m src.main
```
