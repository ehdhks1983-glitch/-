# Instagram Auto Bot

내 인스타그램 **프로페셔널 계정**에, **메타 공식 Graph API**로, 내가 만든 콘텐츠
(이미지/캐러셀/릴스)를 **생성 → 미리보기 승인 → 게시/예약**하는 로컬 데스크톱 봇입니다.
공식 API 합법 노선만 사용하며 자동 인게이지먼트·스텔스·우회 기능은 **포함하지 않습니다.**

> 데스크톱 UI는 **CustomTkinter 다크모드**, 모든 자동화는 별도 스레드에서 실행되어 UI가 멈추지 않습니다.

## 빠른 시작 (개발)

```bash
cd instagram_auto_bot
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python main.py            # 앱 실행 (데스크톱 환경 필요)
pytest -q                 # 테스트 (헤드리스 가능)
```

## 사전 준비 (사용자, 코드 아님)
1. 인스타그램 계정을 **프로페셔널(크리에이터/비즈니스)** 로 전환.
2. 페이스북 페이지 생성 후 인스타 계정 연결.
3. developers.facebook.com 에서 앱 생성(Use case: Other → Business).
4. Instagram 제품 추가 → 본인 계정을 **Instagram Tester** 로 추가/수락.
5. **Access Token** 발급(`instagram_basic`, `instagram_content_publish`).
6. AI 키 발급: 텍스트(Claude/OpenAI/Gemini 중 택1) + 이미지(OpenAI) + **Cloudinary**.

> 키는 앱 실행 후 **계정 탭**에서 입력하며, OS 사용자 폴더(Windows `%LOCALAPPDATA%\InstaAutoBot`)에
> 저장됩니다. **빌드에는 어떤 키도 포함되지 않습니다.**

## 구조
```
main.py            진입점 (로깅/경로 부팅 → UI)
config.py          모든 상수/엔드포인트/비율/한도 (하드코딩 금지)
paths.py           sys.frozen 분기, app-data 경로
core/              비즈니스 로직 (UI와 분리, 전부 단위 테스트됨)
  settings_store · logging_setup · automation_controller · ui_bridge · forms
  content_engine · content_rules · image_engine · uploader
  instagram_api · token_manager · publish_flow · scheduler · app_services · errors
providers/         교체 가능한 외부 연동 (text_*, image_openai, host_*)
ui/                CustomTkinter (app_window + 탭들, 코어의 얇은 셸)
skills/skill.md    에이전트 동작 규칙
build.py           PyInstaller 빌드
tests/             pytest 스위트
```

## 핵심 안전장치
- 컨테이너 `status_code=FINISHED` 폴링 → **에러 9007 방지**
- 게시 전 공개 이미지 URL 접근성 검증 → **에러 9004 방지**
- 토큰 60일 만료 추적 + 자동 갱신, 인증/보안 오류 시 자동 중단 + 재인증 안내
- 예약 발행 **±15분 타이밍 지터** (봇 패턴 회피)
- 24h API 100건 인지 + 자체 보수 일일 상한
- 생성 → **미리보기 → 승인** 후에만 게시 (완전 무인 금지)
- 콘텐츠 규칙 강제: 금지어 필터 / 해시태그 정확히 5개(3~7) / 인스타 비율

## 빌드 (배포 EXE)
대상 OS에서 실행하세요. PyInstaller는 크로스 컴파일을 하지 않습니다.
```bash
python build.py          # → dist/InstaAutoBot(.exe)
```

## 테스트
순수 로직(코어/프로바이더/규칙/게시 플로우)은 헤드리스로 100% 테스트됩니다.
UI는 `xvfb` 환경에서 `scripts/smoke_ui.py` 로 부팅/상호작용을 검증합니다.
