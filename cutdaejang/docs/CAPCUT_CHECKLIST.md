# 캡컷 실물 검증 체크리스트 (Windows + CapCut 설치 PC에서)

개발기획안 v1.2 §9 Phase 0 / §11 중 컨테이너에서 수행 불가능했던 항목.
**이 체크리스트가 끝나야 PoC 게이트 통과** — 결과는 POC_REPORT.md에 추기하고 기획안을 v1.3으로 갱신한다.

## 사전 준비

- [ ] 현재 CapCut 버전 기록: `______` (§11-6)
- [ ] CapCut 설치 파일 백업 + **자동 업데이트 끄기** (draft 포맷 변경 리스크 헷지, §8)
- [ ] Drafts 폴더 경로 확인 (보통 `C:\Users\<user>\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft`)
- [ ] `pip install pycapcut` + 이 저장소 체크아웃

## 1. demo draft 열림 확인 (§11-1) ★게이트

```bash
python -m cutdaejang demo --outputs mp4,draft --drafts-dir "<Drafts 경로>"
```

- [ ] CapCut 프로젝트 목록에 `cutdaejang_...` 표시됨
- [ ] 열었을 때 타임라인 정상 (크래시/빈 화면 없음)
- [ ] 총 길이가 mp4 출력과 동일

## 2. 4트랙 배치 검증 (§11-2) ★최중요

열린 draft에서 확인:

- [ ] 배경 이미지가 전체 길이 동안 표시 (이미지 duration 정상)
- [ ] 자막 위치: 하단 중앙 (코드 가정: `transform_y=-0.71`, +y=위) —
      **어긋나면** `draft_builder.py`의 `ty_map` 부호/값 수정
- [ ] 자막 크기: mp4 출력(64px 상당)과 시각적으로 유사 —
      **어긋나면** `_PX_TO_CAPCUT_SIZE`(현재 0.15) 캘리브레이션
- [ ] 그라데이션 오버레이가 자막 아래 레이어에 깔림
- [ ] `--main-video <영상>` 옵션으로 재실행 → 상단 배치·스케일 0.9 확인
- [ ] 오디오 4클립이 자막과 같은 구간에 배치

## 3. 캡컷 커스텀 폰트 (§11-5)

- [ ] CapCut 텍스트에 Pretendard 적용 가능 여부 확인
      (Windows에 `resources/fonts/Pretendard-ExtraBold.ttf` 설치 후)
- [ ] 불가하면: 내장 폰트 중 폴백 선정 → `draft_builder`에 FontType 지정 추가 (§7-3)

## 4. TTS 실측 (§11-3) — 키만 있으면 어느 PC에서든

```bash
set GEMINI_API_KEY=...
python -m cutdaejang run --topic "테스트 주제" --auto --tts gemini
set OPENAI_API_KEY=...
python -m cutdaejang run --topic "테스트 주제" --auto --tts openai
```

- [ ] 한국어 10문장 품질 비교 (발음·억양·숫자 읽기)
- [ ] 60초 쇼츠 1편당 비용·지연 기록 → 비용표 작성
- [ ] 발음 오독 사례 수집 → 대본 프롬프트 발음 규칙 보강 (§7-6)

## 5. GPU 렌더 실측 (센텀하이 GPU 노트북)

- [ ] `python -m cutdaejang doctor`에서 h264_nvenc 감지 확인
- [ ] 60초 쇼츠 렌더 시간 기록 (KPI: 주제→mp4 5분 이내, §10)

## 완료 후

- [ ] 결과를 POC_REPORT.md에 추기 (버전·시그니처·계수 확정값)
- [ ] 기획안 v1.2 → v1.3 갱신 (§11-7)
