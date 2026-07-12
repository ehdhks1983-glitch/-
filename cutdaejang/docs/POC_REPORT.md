# Phase 0 PoC 결과 보고서 (1차 — Linux 환경 실행분)

- 실행일: 2026-07-12
- 환경: Ubuntu 24.04 컨테이너 / Python 3.11.15 / FFmpeg 6.1.1 (libass 포함, Ubuntu 배포판 빌드) / GPU 없음
- 대상: 개발기획안 v1.2 §9 Phase 0 및 §11 1주차 액션 아이템 중 **Windows/CapCut 없이 검증 가능한 전부**

## 요약

**출력 B(FFmpeg 직접 렌더) 경로는 전 구간 실증 완료.** 기획안의 핵심 베팅 —
"render_engine은 결정적 로직이라 리스크 낮음"(§9) — 이 사실로 확인됐다.
남은 진짜 관문은 예정대로 캡컷 실물 검증(§11 항목 1·2·5·6, Windows 필요)뿐이다.

| # | 액션 아이템 (§11) | 결과 |
|---|---|---|
| 4 | libass FFmpeg + 배경+ASS 자막(프리텐다드) 렌더 테스트 | ✅ **통과** — 아래 상세 |
| 2(부분) | 4트랙 draft 코드 재현 | ⚙️ pycapcut로 draft_content.json 생성·구조 자가검증 통과. **캡컷 열림 확인은 Windows 필요** |
| 3 | Gemini vs OpenAI TTS 한국어 비교 | ⏳ 미실시 — API 키 필요. 호출 코드는 구현 완료 |
| 1·5·6 | 캡컷 설치 환경 필요 항목 | ⏳ [CAPCUT_CHECKLIST.md](CAPCUT_CHECKLIST.md)로 정리 |

## 상세 결과

### 1. libass 한글 자막 번인 (§11-4) — 통과

- `subtitles=filename=subs.ass:fontsdir=resources/fonts` 방식으로 Pretendard ExtraBold
  한글 자막이 1080×1920 배경 위에 정상 번인됨 (외곽선 3px, 하단 중앙, MarginV 280).
- libass 로그로 폰트 매칭 확인: `Loading font file '.../Pretendard-ExtraBold.ttf'`.
  폰트 내부 패밀리명은 **"Pretendard ExtraBold"** (name ID 1/16+17 확인) — ASS Style의
  Fontname은 이 값을 써야 하며, 코드에서는 `presets.FONT_FAMILY_ALIASES`로 변환한다.
- 참고: fontsdir 안의 비폰트 파일(라이선스 txt)에 무해한 경고 로그가 남는다.

### 2. E2E 렌더 (스텁 TTS 4문장, 한국어)

| 항목 | 값 |
|---|---|
| 스펙 길이 | 17.05초 (문장 실측 누적 + 갭 0.25s + 리드인 0.3s + 테일 0.6s) |
| 렌더 시간 | **12.8초** (libx264 medium CRF19, 1080×1920@30, CPU 전용) |
| 길이 오차 | 실측 = 스펙 (±50ms 자가검증 통과) |
| 해상도/오디오 | 1080×1920 일치, AAC 192k 스테레오 존재 |

- KPI "주제→mp4 5분 이내(60초 쇼츠, GPU)"(§10)는 **GPU 없이도** 여유롭게 달성 전망.
  병목은 렌더가 아니라 TTS API 왕복이 될 것.
- nvenc 자동 감지 → 미감지 시 libx264 폴백 경로가 실제로 동작함을 확인.
- 진행률(-progress pipe:1) 파싱 → 0~100% 단조 증가 콜백 확인 (GUI 진행바 준비 완료).

### 3. audio_assembler 정밀도

- 문장 클립을 **샘플 단위**(adelay=...S, 48kHz)로 배치 — μs당 오차 ±10μs 이내.
- amix(normalize=0) 합산이라 문장 수와 무관하게 레벨 불변. 병합 결과 실측 길이가
  스펙과 정확히 일치 (테스트에서 오차 0 관측, 허용치는 ±50ms 유지).

### 4. draft_builder (출력 A) — 구조 검증까지

- pycapcut(파이썬 3.11, pip 설치 정상)로 4트랙(배경→메인→그라데이션→자막)+오디오
  draft 생성 성공. draft_content.json의 duration이 spec과 **정확히 일치**(17,050,000μs),
  트랙·세그먼트 수 일치. 자가검증 3종(존재/파싱/구성) 통과.
- **미검증(캡컷 실물 필요)**: 열림 여부, ClipSettings.transform_y 부호·스케일,
  TextStyle.size 단위 캘리브레이션(현재 px×0.15 가정), 임의 크기 이미지 fit.
  → 체크리스트 문서에 절차 정리.

### 5. 폰트 수급 관련 결정 사항

- 네트워크 정책상 GitHub 릴리스 zip 대신 **npm 패키지(pretendard@1.3.9)의
  static/alternative TTF**를 동봉했다 (동일 OFL, 일부 글리프 대체형).
  배포 전 공식 릴리스의 표준 static TTF로 교체 권장 — 시각 차이는 미세함.

## 다음 단계 (v1.3 반영 후보)

1. Windows PC에서 [CAPCUT_CHECKLIST.md](CAPCUT_CHECKLIST.md) 수행 → transform/폰트/size 계수 확정
2. `GEMINI_API_KEY`/`OPENAI_API_KEY` 준비 후 한국어 10문장 TTS 비교 (§11-3) —
   `python -m cutdaejang run --topic ... --tts gemini|openai`로 동일 파이프라인 재사용 가능
3. GPU 노트북에서 nvenc 실측 (60초 쇼츠 기준 렌더 시간)
4. GUI(Phase 2) 착수 — 오케스트레이터/진행률 콜백/히스토리 DB는 GUI가 그대로 소비하도록 설계됨
