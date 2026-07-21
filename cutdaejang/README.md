# 컷대장 — 유튜브 쇼츠·영상 자동 제작

> 주제만 입력하면 대본·TTS·배경·자막을 자동 조립해 **업로드 준비 완료된 mp4**로 뽑아주는 프로그램. (mp4 전용 — CapCut draft 출력은 v0.41에서 제거)

세 가지 모드:
- **🤖 AI 영상 만들기** — 주제(또는 내 대본) → 대본·목소리·배경·자막 자동 → 세로 쇼츠(9:16) / 가로 롱폼(16:9)
- **✂️ 내 영상 편집** — 직접 찍은 영상을 무음컷 + 자동자막(STT) + AI 내레이션. 무음·시연 영상은 화면을 분석해 대본까지 자동 작성
- **📸 사진으로 영상** — 사진 여러 장 → 슬라이드쇼 영상

**👉 처음이라면: [실행가이드.md](실행가이드.md) — Windows에서 더블클릭 2번이면 브라우저 UI가 뜹니다 (`windows/1_설치.bat` → `windows/2_UI실행.bat`)**

런타임 의존성은 **표준 라이브러리 + FFmpeg 바이너리**뿐이다 (고객 PC 설치 단순화). 배포는 zip(폰트·리소스 동봉) + `windows/*.bat`.

## 빠른 시작

```bash
# 환경 점검 (FFmpeg/libass/GPU/폰트/API 키)
python -m cutdaejang doctor

# 오프라인 데모: API 키 없이 전체 파이프라인 확인 (스텁 대본·TTS)
python -m cutdaejang demo

# 실전: 주제 → 완성 mp4 (자동 모드, Gemini 키 필요)
export GEMINI_API_KEY=...
python -m cutdaejang run --topic "하루 10분 정리 습관" --auto

# 검토 모드(기본): 대본 생성 → 파일 수정 → 재개
python -m cutdaejang run --topic "..."            # → jobs/<id>/script.json 생성 후 대기
python -m cutdaejang run --script-file jobs/<id>/script.json

# 히스토리 재생성: 저장된 spec만으로 재렌더
python -m cutdaejang render --spec jobs/<id>/spec.json

# 브라우저 UI (권장)
python -m cutdaejang ui        # → http://127.0.0.1:7860
```

출력은 **mp4 전용**이다. `--outputs` 에 `mp4` 외의 값(예: `draft`)을 넣으면 조용히 성공하지 않고 즉시 오류를 낸다.

## 보안 안내

- 로컬 웹 UI는 **127.0.0.1**에만 바인딩되며, 다른 웹사이트의 요청을 막기 위해 Origin/Host 검사와 JSON 전용 POST를 적용한다.
- API 키를 [🔑 API 연동]에서 저장하면 이 PC의 `api_keys.json`에 **평문으로** 저장된다. 공용 PC에서는 저장하지 말고, 쓰고 나면 [저장된 키 모두 삭제]로 지운다.

## 테스트

```bash
pip install pytest
python -m pytest tests/            # E2E 렌더 포함 (ffmpeg 필요)
```

## 구조

```
cutdaejang/
├── spec.py                  # Timeline Spec(IR) — μs 정수, 검증, 직렬화
├── presets.py               # 스타일·배치 프리셋
├── core/
│   ├── script_generator.py  # 주제/영상 → 구조화 JSON 대본 (Gemini/Stub)
│   ├── tts_engine.py        # 문장별 TTS + 해시 캐싱 + LUFS 정규화 (Gemini/OpenAI/ElevenLabs/Windows/Stub)
│   ├── timeline_calculator.py # ffprobe 실측 → spec 확정 (동기화 오차 0)
│   ├── background_generator.py # Gemini 이미지 / 사용자 이미지 / 로컬 폴백
│   ├── render_engine/       # 출력: mp4 ★
│   │   ├── ass_writer.py    #   자막 .ass 생성
│   │   ├── audio_assembler.py #  클립+갭 → voice_full.m4a
│   │   └── ffmpeg_composer.py #  필터그래프 + nvenc 자동감지/폴백 + 진행률
│   ├── edit_mode.py         # 내 영상 편집 (무음컷·STT·AI 내레이션·화면분석)
│   ├── orchestrator.py      # 검토/자동 모드 파이프라인 (실패 정책)
│   └── ...
├── db/jobs.py               # 히스토리 (SQLite)
├── gui/webui.py             # 로컬 웹 UI 서버
├── utils/                   # ffmpeg/ffprobe·시간(μs)·PNG 생성
└── tests/
resources/fonts/             # Pretendard-ExtraBold.ttf (OFL — 고지문 동봉)
```

## 폰트 라이선스

동봉된 Pretendard는 SIL Open Font License 1.1로 재배포 가능하며 고지문을
`resources/fonts/OFL-LICENSE.txt`로 포함한다. 추가 무료 글씨체(블랙한산스·주아·도현·구기·나눔손글씨)는 화면의 [⬇ 무료 글씨체 받기]로 Google Fonts(OFL)에서 내려받는다.
