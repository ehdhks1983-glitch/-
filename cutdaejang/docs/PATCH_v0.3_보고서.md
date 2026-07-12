# v0.3 패치 완료 보고서 (작업지시서 "v0.1→v0.2 패치" 이행분)

- 실행일: 2026-07-12 · 기반: v0.2 코드베이스 (지시서의 "v0.1" 명칭과 무관하게 최신 코드 위에 적용, 릴리스 번호는 v0.3)
- 백업: git 이력 (직전 커밋 = v0.2, 원격 푸시됨)

## 1. 변경 파일 목록

| 파일 | 요약 |
|---|---|
| `cutdaejang/config.py` ★신규 | settings.json 로더 (탐색: 인자→환경변수→./settings.json→기본값, 깊은 병합) |
| `settings.json` ★신규 | 신규 설정 기본값 (하단 §2) |
| `core/tts_engine.py` | 전면 개편: retryDelay 준수 재시도·지수 백오프·지터, 슬라이딩 윈도우 레이트리미터(8rpm), SHA256 영구 캐시(cache/tts/*.wav), 작업 단위 폴백 체인, 무음 트림+페이드+LUFS 전처리, 스타일 지시문 3종, OpenAI tts-1 모델 폴백, 오류 한 줄 요약+카운트다운 콜백 |
| `core/orchestrator.py` | settings 주입, tts_chain/voice/tts_style/bgm 옵션, BGM 해석(random/파일), 사용 제공자·폴백 사유 기록, 원본 오류 분리 저장 |
| `core/render_engine/ffmpeg_composer.py` | Ken Burns(zoompan, 2배 업스케일, 줌인/아웃/off), BGM 믹싱(-stream_loop, volume dB, 페이드인 0.5s/아웃 1.5s, amix normalize=0, 옵션 sidechaincompress 덕킹) |
| `core/render_engine/ass_writer.py` | 자막 페이드 `{\fad(100,60)}`, 강조 단어 인라인 컬러(기본색 명시 복원), Shadow 필드 |
| `core/script_generator.py` | 대본 스키마: 문장별 `{"text","highlight"}` (구형 문자열 배열도 호환), 프롬프트에 highlight 규칙·문장 길이 강제 |
| `core/timeline_calculator.py` | highlights·bgm 전달 |
| `core/draft_builder.py` | BGM 별도 오디오 트랙(짧은 음원 이어붙여 루프, dB→선형 volume), 배경 uniform_scale 키프레임(Ken Burns) |
| `spec.py` | IR 확장: Background.motion/motion_amount, Bgm, Subtitle.highlight, Style.shadow/fade/highlight_color |
| `db/jobs.py` | tts_provider 컬럼 + 자동 마이그레이션 |
| `gui/webui.py` | 보이스·말투 드롭다운, 🔊미리듣기(1문장 합성·캐시 재생), BGM 드롭다운(없음/랜덤/파일)+저작권 문구, 진행 노트(대기 카운트다운 표시), 폴백 배지, 오류 [자세히] 접기, 검토 모드 `문장 \| 강조단어` 편집 |
| `__main__.py` | --tts-style/--bgm 플래그, 폴백 체인 연결, 제공자 출력 |
| `resources/bgm/` ★신규 | 사용자 음원 폴더 (음원 미제공, 안내문 포함) |
| `tests/test_patches_v03.py` ★신규 | 25개 테스트 (아래 AC표) — 전체 65개 통과 |

## 2. 신규 설정 키 (settings.json)

지시서 "설정 키 일람"과 동일 + 추가 2키: `tts.model_gemini`, `tts.model_openai`
(모델명 변경/유료 등급 전환 대비. 하드코딩 금지 원칙 적용). `subtitle.shadow`도 명시 키로 노출.

## 3. 결정·폴백 사항 (지시서가 위임한 판단)

1. **캐시 파일 위치** = `<workdir>/cache/tts/{sha256}.wav` — 작업 폴더와 분리된 영구 캐시, 작업 실패해도 보존. 저장 시점은 전처리(트림·LUFS) **후** → 재실행 시 전처리도 생략됨.
2. **폴백 체인의 최종 단계**: 지시서의 "최종 폴백 = 테스트 톤" 앞에 Windows에서는 `windows`(내장 한국어 음성)를 자동 삽입 — 삐 소리보다 항상 낫다고 판단. 체인: `gemini → openai → (windows) → stub`.
3. **캡컷 키프레임**: pycapcut이 `uniform_scale` 키프레임을 지원함을 확인, draft 배경에도 Ken Burns 적용(시작 1.0 → 끝 1.08). draft_content.json에 키프레임 기록 확인. **캡컷 실물 렌더 확인은 Windows 체크리스트 항목**.
4. **캡컷 부분 색상(강조 스팬)**: pycapcut TextSegment는 문장 단위 스타일만 지원 → draft는 문장 전체 단일 스타일 폴백 (지시서 예상대로).
5. **TTS 지시문 언어**: 한국어 유지 (Gemini TTS 공식 문서의 "지시문+콜론" 패턴). **지시문이 음성으로 읽히는지 실키 1문장 테스트 필요** — 읽히면 `tts_engine.STYLE_INSTRUCTIONS`를 영어 1줄로 교체 (주석 표기해둠).
6. **Bold**: 폰트가 이미 ExtraBold라 ASS Bold 플래그(가짜 볼드)는 켜지 않음 — 획 뭉개짐 방지.
7. **BGM dB 변환**: FFmpeg `volume=-20dB` 표기 사용 (선형 변환과 등가). draft 쪽은 선형값(0.1)으로 변환 적용.
8. **429가 아닌 4xx**(400 등)는 재시도하지 않음(무의미) — 5xx·429만 재시도.

## 4. AC 체크표

| AC | 결과 |
|---|---|
| 429 시 retryDelay만큼 대기 후 성공 | ✅ 단위 테스트 (가짜 시계: 18.2s+지터 대기 2회 후 성공, 호출 3회) |
| 문장 15개 무료 키 1회 완주 (레이트리미터 페이싱) | ⏳ **실키 필요 — 사용자 검증** (리미터 8rpm 동작은 단위 테스트로 확인) |
| 동일 대본 재실행 시 API 0회 | ✅ 단위 + 통합 (12문장 재실행: "API 0회, 캐시 12회") |
| Gemini 키 제거 시 OpenAI 전체 폴백 | ✅ 등가 시나리오(비재시도 오류→체인 폴백) 테스트. 실키 폴백은 사용자 검증 |
| 트림 전/후 길이 로그 | ✅ 상태 노트로 출력. 스텁 음성은 패딩이 없어 0.0s — 패딩 입력 단위 테스트에서 0.7s+ 단축 확인. **실 TTS 2초+ 단축은 실키 검증** |
| 자막-발화 ±50ms | ✅ 트림 후 재실측으로 타임라인 계산 (기존 자가검증 유지) |
| 클립 경계 클릭 노이즈 | ✅ 양끝 10ms 페이드 적용 (청감 확인은 사용자) |
| BGM -20dB·페이드아웃·명료도 | ✅ 필터그래프 테스트 + 51초 통합 렌더 (청감 확인은 사용자) |
| 60초 줌 부드러움 / motion=off 시 기존과 동일 | ✅ zoompan 2배 업스케일 적용 / off 경로 기존 명령 동일 (테스트) |
| 강조 단어만 노란색 | ✅ 렌더 프레임 확인 ("노란색"만 #FFD400) |
| 자막이 쇼츠 UI와 안 겹침 | ✅ MarginV 420 적용 프레임 확인 |
| 3개 프리셋 청감 구분·지시문 미발화·미리듣기 3초 | ⏳ **실키 필요 — 사용자 검증** (미리듣기 버튼·캐시 구현 완료) |

## 5. before / after 렌더

같은 12문장 대본(스텁 음성)으로 비교 렌더 — 사용자에게 파일로 전달됨:
- before (v0.1 스타일: 모션 off·BGM 없음·자막 64px/외곽3/여백280·페이드 없음): `v01-before/output.mp4`
- after (v0.3 기본: 줌인·BGM·자막 76px/외곽4/그림자/여백420/페이드·강조색): `v03-after/output.mp4`
- 렌더 시간: after 35.6s / before 26.5s (51초 영상, CPU libx264 — zoompan 비용 +9s 수준)

## 6. 다음 실키 검증 절차 (사용자, 5분)

1. UI에서 Gemini(실전) + 키 → 15문장급 주제로 1회 생성 → 429 없이 완주 확인 (진행줄에 "분당 한도 조절 중 — N초 대기"가 보이면 정상 동작)
2. 같은 주제 즉시 재생성 → TTS 단계가 순식간에 지나가면 캐시 정상
3. 🔊 미리듣기로 3개 말투 비교 + **지시문이 읽히는지** 확인 → 읽히면 보고
