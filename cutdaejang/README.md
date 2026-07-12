# 컷대장 — CapCut 쇼츠·영상 조립 자동화

> 주제만 입력하면 대본·TTS·배경·자막을 자동 조립해 **①수정 가능한 CapCut 프로젝트(draft)** 또는 **②업로드 준비 완료된 mp4**로 뽑아주는 프로그램.

**v0.3**: TTS 429 안정화(레이트리미터·retryDelay 재시도·영구 캐시·제공자 폴백), 무음 트림 pacing,
BGM 트랙, 배경 Ken Burns 줌, 자막 강조 컬러·스타일 상향, 보이스 말투 프리셋+미리듣기.
설정은 [settings.json](settings.json), 패치 상세는 [docs/PATCH_v0.3_보고서.md](docs/PATCH_v0.3_보고서.md).

기획 문서: [docs/개발기획안_v1.2.md](docs/개발기획안_v1.2.md) · PoC 결과: [docs/POC_REPORT.md](docs/POC_REPORT.md) · 캡컷 수동 검증: [docs/CAPCUT_CHECKLIST.md](docs/CAPCUT_CHECKLIST.md)

**👉 처음이라면: [실행가이드.md](실행가이드.md) — Windows에서 더블클릭 2번이면 브라우저 UI가 뜹니다 (`windows/1_설치.bat` → `windows/2_UI실행.bat`)**

## 현재 상태 (v0.1)

| 영역 | 상태 |
|---|---|
| Timeline Spec(IR) — 두 출력의 단일 진실 원천 (§3.2) | ✅ 구현 + 테스트 |
| 출력 B: render_engine (FFmpeg 직접 렌더, §5.5) | ✅ 구현 + E2E 렌더 검증 (±50ms 자가검증 통과) |
| 출력 A: draft_builder (pyCapCut 4트랙, §5.4) | ⚙️ 구현 완료, **CapCut 실물 열림 검증은 Windows PoC 필요** |
| 문장별 TTS + 캐싱 + -16 LUFS (§5.2) | ✅ 구조 완성 — Gemini/OpenAI는 API 키로 실검증 필요, Stub은 검증됨 |
| 대본 생성 (부록 A 프롬프트) | ⚙️ Gemini 구현(키 필요) + Stub |
| 배경 생성 (§5.3) | ⚙️ Gemini 이미지(키 필요) + 로컬 그라데이션 폴백 검증됨 |
| 자동 모드 오케스트레이터 (§5.6 실패 정책) | ✅ 구현 |
| 히스토리 (SQLite, spec 보존 → 재생성) | ✅ 구현 |
| GUI (§6) | ✅ 로컬 웹 UI (`python -m cutdaejang ui`) — 새 작업·대본 검토·진행률·재생·히스토리. 데스크톱 창(CustomTkinter/pywebview) 전환은 Phase 2에서 결정 |
| 배치 모드 / 일반(16:9) 모드 | ⏳ v1.5 |

런타임 의존성은 **표준 라이브러리 + FFmpeg 바이너리**뿐이다 (PyInstaller 패키징 단순화).
출력 A만 `pycapcut` 추가 설치가 필요하다.

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

# CapCut draft도 함께 (Windows, CapCut 설치 PC)
python -m cutdaejang run --topic "..." --auto --outputs mp4,draft \
    --drafts-dir "C:/Users/<user>/AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"

# 히스토리 재생성: 저장된 spec만으로 재렌더
python -m cutdaejang render --spec jobs/<id>/spec.json
```

## 테스트

```bash
pip install pytest
python -m pytest tests/            # 36개 — E2E 렌더 포함 (ffmpeg 필요)
```

## 구조 (기획안 §3.4)

```
cutdaejang/
├── spec.py                  # Timeline Spec(IR) — μs 정수, 검증, 직렬화
├── presets.py               # A/B 공통 스타일·배치 프리셋
├── core/
│   ├── script_generator.py  # 주제 → 구조화 JSON 대본 (Gemini/Stub)
│   ├── tts_engine.py        # 문장별 TTS + 해시 캐싱 + LUFS 정규화 (Gemini/OpenAI/Stub)
│   ├── timeline_calculator.py # ffprobe 실측 → spec 확정 (동기화 오차 0)
│   ├── background_generator.py # Gemini 이미지 / 사용자 이미지 / 로컬 폴백
│   ├── draft_builder.py     # 출력 A: pyCapCut 4트랙 + 자가검증
│   ├── render_engine/       # 출력 B ★
│   │   ├── ass_writer.py    #   자막 .ass 생성
│   │   ├── audio_assembler.py #  클립+갭 → voice_full.m4a (샘플 단위 배치)
│   │   └── ffmpeg_composer.py #  필터그래프 + nvenc 자동감지/폴백 + 진행률
│   ├── orchestrator.py      # 검토/자동 모드 파이프라인 (§5.6 실패 정책)
│   └── ...
├── db/jobs.py               # 히스토리 (SQLite)
├── utils/                   # ffmpeg/ffprobe·시간(μs)·PNG 생성
├── resources/fonts/         # Pretendard-ExtraBold.ttf (OFL — 고지문 동봉)
└── tests/
```

## 폰트 라이선스

동봉된 Pretendard는 SIL Open Font License 1.1로 재배포 가능하며 고지문을
`resources/fonts/OFL-LICENSE.txt`로 포함한다 (기획안 §8).
